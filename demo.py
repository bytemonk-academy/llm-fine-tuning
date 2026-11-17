"""LLM fine-tuning lab: validate data, explore saved results, and run a Crusoe experiment."""
import argparse
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from build_dataset import POLICY, ROOT, ROUTING

def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")

def valid_schema(obj):
    return (isinstance(obj, dict) and set(obj) == {"category", "severity", "team"}
            and isinstance(obj.get("category"), str) and obj["category"] in ROUTING
            and isinstance(obj.get("severity"), str) and obj["severity"] in {"SEV1", "SEV2", "SEV3"}
            and isinstance(obj.get("team"), str) and obj["team"] in set(ROUTING.values()))

def validate():
    seen = set()
    counts = {}
    for split in ("train", "validation", "test"):
        rows = read_rows(ROOT / "data" / f"{split}.jsonl")
        assert rows, f"Empty split: {split}"
        for row in rows:
            messages = row["messages"]
            assert [m["role"] for m in messages] == ["system", "user", "assistant"]
            assert messages[0]["content"] == POLICY
            incident = messages[1]["content"].strip().casefold()
            assert incident not in seen, "Duplicate incident within/across splits"
            seen.add(incident)
            obj = json.loads(messages[2]["content"])
            assert valid_schema(obj), obj
            assert obj["team"] == ROUTING[obj["category"]], obj
        counts[split] = len(rows)
    print(json.dumps({"valid": True, "records": counts, "exact_duplicates": 0}, indent=2))

def client(base_url=None):
    from openai import OpenAI
    key = os.environ.get("CRUSOE_API_KEY")
    if not key:
        raise SystemExit("Set CRUSOE_API_KEY in your terminal; do not put it in source code.")
    return OpenAI(api_key=key, base_url=base_url or "https://api.intelligence.crusoecloud.com/v1",
                  timeout=120, max_retries=0)

def score(rows):
    n = len(rows)
    assert n, "No evaluation records"
    successes = [r for r in rows if not r.get("error")]
    latencies = sorted(r["latency_seconds"] for r in successes if "latency_seconds" in r)
    result = {"test_size": n, "request_errors": n-len(successes)}
    for key in ("category", "severity", "team"):
        result[key + "_accuracy"] = sum(r.get("prediction", {}).get(key) == r["expected"][key] for r in rows) / n
    result["valid_json_rate"] = sum(r["valid_json"] for r in rows) / n
    result["valid_schema_rate"] = sum(r["valid_schema"] for r in rows) / n
    result["exact_match_rate"] = sum(r.get("prediction") == r["expected"] for r in rows) / n
    sev1 = [r for r in rows if r["expected"]["severity"] == "SEV1"]
    result["sev1_miss_rate"] = (sum(r.get("prediction", {}).get("severity") != "SEV1" for r in sev1) / len(sev1)) if sev1 else None
    result["p95_successful_request_seconds"] = latencies[math.ceil(.95*len(latencies))-1] if latencies else None
    result["total_tokens"] = sum((r.get("usage") or {}).get("total_tokens", 0) for r in rows)
    result["cost_usd"] = None  # Fill only from actual billing; dedicated GPU cost is time-based.
    return result

def evaluate(args):
    c = client(args.base_url)
    path = ROOT / "data/test.jsonl"
    data = read_rows(path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise SystemExit(f"Refusing to overwrite {out}; choose a new result filename.")
    results = []
    started = datetime.now(timezone.utc).isoformat()
    for i, example in enumerate(data):
        messages = example["messages"]
        row = {"index": i, "incident": messages[1]["content"],
               "expected": json.loads(messages[2]["content"]),
               "valid_json": False, "valid_schema": False, "prediction": {}}
        start = time.perf_counter()
        try:
            response = c.chat.completions.create(model=args.model, messages=messages[:2],
                                                  temperature=0, max_tokens=256)
            row["latency_seconds"] = time.perf_counter()-start
            row["raw"] = response.choices[0].message.content or ""
            row["finish_reason"] = response.choices[0].finish_reason
            row["usage"] = response.usage.model_dump() if response.usage else None
            try:
                obj = json.loads(row["raw"])
                row["valid_json"] = True
                row["valid_schema"] = valid_schema(obj)
                # Preserve invalid JSON types as raw output, not a dict for scoring.
                if isinstance(obj, dict):
                    row["prediction"] = obj
            except (ValueError, TypeError):
                pass
        except Exception as exc:
            row["latency_seconds"] = time.perf_counter()-start
            row["error"] = type(exc).__name__
        results.append(row)
        with out.open("a") as f:
            f.write(json.dumps(row)+"\n")
        print(f"{i+1}/{len(data)} schema_valid={row['valid_schema']} error={row.get('error', '')}")
        if row.get("error") and i == 0:
            raise SystemExit("First inference request failed; stopped to avoid 35 repeated failures. Check endpoint, model ID, key and deployment readiness.")
    summary = {"model": args.model, "base_url": args.base_url,
               "started_at": started, "temperature": 0, "max_tokens": 256,
               "test_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "metrics": score(results), "note": "36 synthetic cases; end-to-end non-streaming latency, not TTFT. No production benchmark claim."}
    save(out.with_suffix(".summary.json"), summary)
    print(json.dumps(summary, indent=2))

def sample_results():
    """Rescore recorded console outputs; never present them as live inference."""
    print("Saved Qwen3.5 2B responses from October 30, 2026; no API calls.\n")
    summaries = []
    for name in ("base", "tuned"):
        rows = []
        for record in read_saved_examples(name):
            row = dict(record, valid_json=False, valid_schema=False, prediction={})
            try:
                obj = json.loads(record["raw"])
                row.update(valid_json=True, valid_schema=valid_schema(obj))
                if isinstance(obj, dict):
                    row["prediction"] = obj
            except (ValueError, TypeError):
                pass
            rows.append(row)
        summaries.append(score(rows))
    print("| Metric | Base | Fine-tuned |\n|---|---:|---:|")
    for key in ("category_accuracy", "severity_accuracy", "team_accuracy", "valid_json_rate", "exact_match_rate", "sev1_miss_rate"):
        print(f"| {key} | {summaries[0][key]:.1%} | {summaries[1][key]:.1%} |")
    print("\nLower SEV1 miss rate is better. These are 36 synthetic cases, not a production benchmark.")


def read_saved_examples(name):
    return json.loads((ROOT / "examples" / f"{name}.json").read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("sample-results", help="Score saved example responses locally; no API calls")
    sub.add_parser("upload")
    t = sub.add_parser("train")
    t.add_argument("--model", required=True, help="Exact fine-tuning model ID shown in Crusoe")
    t.add_argument("--launch", action="store_true", help="Submit a billable training job; otherwise print payload only")
    s = sub.add_parser("status")
    s.add_argument("job_id")
    e = sub.add_parser("evaluate")
    e.add_argument("--model", required=True)
    e.add_argument("--base-url", default="https://api.inference.crusoecloud.com/v1")
    e.add_argument("--out", required=True)
    cp = sub.add_parser("compare")
    cp.add_argument("base_summary")
    cp.add_argument("tuned_summary")
    a = p.parse_args()
    if a.command == "validate":
        validate()
    elif a.command == "sample-results":
        sample_results()
    elif a.command == "upload":
        validate()
        state_path = ROOT / "results/upload.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        c = client()
        for split in ("train", "validation"):
            path = ROOT / "data" / f"{split}.jsonl"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if split in state:
                assert state[split]["sha256"] == digest, "Local data changed; review previous uploads first."
                continue
            with path.open("rb") as f:
                uploaded = c.files.create(file=f, purpose="fine-tune")
            state[split] = {"id": uploaded.id, "sha256": digest}
            save(state_path, state)
        print(json.dumps(state, indent=2))
    elif a.command == "train":
        state_path = ROOT / "results/upload.json"
        if not state_path.exists():
            raise SystemExit("Run python demo.py upload first, or use the console training workflow.")
        state = json.loads(state_path.read_text())
        payload = {"model": a.model, "training_file": state["train"]["id"],
                   "validation_file": state["validation"]["id"],
                   "suffix": "bytemonk-incident-triage", "seed": 42,
                   "method": {"type": "supervised", "supervised": {"hyperparameters": {
                       "n_epochs": 3}}}}
        print(json.dumps(payload, indent=2))
        if a.launch:
            jobpath = ROOT / "results/job.json"
            if jobpath.exists():
                raise SystemExit("A job record already exists. Inspect its status before launching another.")
            job = client().fine_tuning.jobs.create(**payload)
            save(jobpath, job.model_dump())
            print(f"Created {job.id}. Training incurs Crusoe usage charges.")
    elif a.command == "status":
        c = client()
        job = c.fine_tuning.jobs.retrieve(a.job_id)
        print(job.model_dump_json(indent=2))
        if job.status == "succeeded":
            print(c.fine_tuning.jobs.checkpoints.list(a.job_id).model_dump_json(indent=2))
    elif a.command == "evaluate":
        evaluate(a)
    elif a.command == "compare":
        left = json.loads(Path(a.base_summary).read_text())
        right = json.loads(Path(a.tuned_summary).read_text())
        for field in ("test_sha256", "temperature", "max_tokens"):
            assert left[field] == right[field], f"Comparison mismatch: {field}"
        print("| Metric | Base | Fine-tuned |\n|---|---:|---:|")
        for key, value in left["metrics"].items():
            print(f"| {key} | {value} | {right['metrics'][key]} |")

if __name__ == "__main__":
    main()
