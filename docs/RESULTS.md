# A small fine-tuning experiment

**Question:** Can LoRA improve consistent incident classification under an explicit policy?

On October 30, 2026, we uploaded 288 synthetic training examples and 72 validation examples to Crusoe Intelligence Foundry, fine-tuned Qwen3.5 2B with automatic console settings, deployed the checkpoint, and compared it with the matching base model. Training completed in five steps. Both temporary inference deployments were deleted afterward.

The 36 test incidents were authored separately. Training/validation split scenario families before varying impact, but examples are still correlated. Both models received the same system policy, temperature 0, maximum 256 output tokens, top-p 1, and zero frequency/presence penalties. Each case started a new conversation. Both deployments used BF16, the Throughput profile, and one H100, sequentially.

| Correct outputs | Base | Fine-tuned |
|---|---:|---:|
| Category | 34/36 | 36/36 |
| Severity | 21/36 | 27/36 |
| Team label | 23/36 | 36/36 |
| Parseable JSON | 36/36 | 36/36 |
| All fields (exact match) | 11/36 | 27/36 |
| SEV1 misses (lower is better) | 10/12 | 6/12 |

Labels are scored exactly, including case. For example, `Identity` does not match the required `IDENTITY` enum.

## What the failures teach

The tuned model labeled confirmed database data loss affecting 0.1% of customers as **SEV3**. The policy requires **SEV1** for confirmed data loss, regardless of the percentage. It also made mistakes on percentages written in words and an instruction embedded in an incident.

Fine-tuning improved task performance in this sample, but did not guarantee policy compliance. Inspect failures, improve training coverage, and test on fresh independently labeled cases before drawing broader conclusions. Validation loss is not classification accuracy.

## Reproduce the comparison without cloud access

```bash
python3 demo.py sample-results
```

[`examples/base.json`](../examples/base.json) and [`examples/tuned.json`](../examples/tuned.json) contain the saved inputs, labels, and complete raw outputs captured from the console playground. These are historical results, not simulated or freshly generated predictions. Incomplete exploratory captures and extra smoke tests are excluded. This report makes no latency or dollar-cost improvement claim.
