# Optional CLI workflow

Use this after the README's local quickstart. The recorded experiment used the Crusoe console; the API workflow below has been checked locally but **has not been authenticated and tested end to end against Crusoe**.

## Set up

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python demo.py validate
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.

Create an Intelligence API key for your Crusoe project. Set it in your terminal environment as `CRUSOE_API_KEY`; the script reads it there. It does not load `.env` files. Keep keys out of source code and recordings.

For macOS/Linux, run the following, paste your key at the hidden input, and press Enter:

```bash
read -r -s CRUSOE_API_KEY
export CRUSOE_API_KEY
```

## Upload and train (optional alternative to the console)

```bash
python demo.py upload
python demo.py train --model YOUR_TRAINING_MODEL_ID
```

The second command prints a request without submitting it. Get the training model ID from Crusoe, not from a serving endpoint. This example requests three epochs and leaves other hyperparameters at service defaults. Review settings and pricing in the console before launching:

```bash
python demo.py train --model YOUR_TRAINING_MODEL_ID --launch
python demo.py status YOUR_JOB_ID
```

Upload and job records are saved under ignored `results/`. If a network response is lost, check the console before retrying a create operation. The script refuses another launch when a local job record exists.

## Evaluate ready deployments

Deploy the checkpoint and matching base model using the console. Copy each **serving model ID** and API base URL from its deployment. A serving ID differs from a training model ID.

```bash
python demo.py evaluate --model YOUR_BASE_SERVING_ID --base-url https://api.inference.crusoecloud.com/v1 --out results/base.jsonl
python demo.py evaluate --model YOUR_TUNED_SERVING_ID --base-url https://api.inference.crusoecloud.com/v1 --out results/tuned.jsonl
python demo.py compare results/base.summary.json results/tuned.summary.json
```

These make billable inference requests. Both use the same policy, temperature 0, and maximum 256 output tokens. Expected answers are used only by the scorer, not sent to the model. Use a new output filename for each run.

Errors count against accuracy. JSON validity and schema validity are separate. CLI latency is full non-streaming request time, including network overhead, at concurrency one; it is not time to first token or a load test. The comparison checks the test-file hash and generation settings. Keep hardware/settings comparable too.

Delete temporary deployments in the console after the experiment. The CLI does not automatically remove them.
