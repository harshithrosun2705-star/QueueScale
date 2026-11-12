#!/usr/bin/env bash
set -euo pipefail

# Start the Compose worker with DEMO_ACK_DELAY_SECONDS=30 before running this.
output=$(python3 scripts/smoke.py)
printf '%s\n' "$output"
job_id=$(sed -n 's/.*first job=\([^ ]*\).*/\1/p' <<< "$output")
test -n "$job_id"
docker compose kill -s SIGKILL worker
docker compose up -d worker

for ((i = 0; i < 40; i++)); do
    logs=$(docker compose logs --no-color worker)
    if grep -Fq "job=$job_id attempt=1 outcome=skipped redelivered=True" <<< "$logs"; then
        python3 - "$job_id" <<'PY'
import json
import sys
from urllib.request import urlopen

with urlopen(f"http://localhost:8000/jobs/{sys.argv[1]}", timeout=10) as response:
    job = json.load(response)
assert job["status"] == "completed" and job["attempts"] == 1 and job["result"]
print("Verified committed result survived worker termination and redelivery.")
PY
        exit 0
    fi
    sleep 1
done

echo "Worker did not log the expected redelivery for $job_id" >&2
exit 1
