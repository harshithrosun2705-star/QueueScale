#!/usr/bin/env python3
"""Upload sample scans and check job outcomes using the public API."""
import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "sample-form.png"


def request(base_url, path, **kwargs):
    with urlopen(Request(base_url.rstrip("/") + path, **kwargs), timeout=10) as response:
        return json.load(response)


def upload(base_url, data):
    boundary = uuid4().hex
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="sample.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    return request(
        base_url,
        "/jobs",
        data=prefix + data + f"\r\n--{boundary}--\r\n".encode(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )["id"]


def wait_for_jobs(base_url, ids, timeout, expected):
    waiting = set(ids)
    deadline = time.monotonic() + timeout
    while waiting and time.monotonic() < deadline:
        for job_id in list(waiting):
            job = request(base_url, f"/jobs/{job_id}")
            if job["status"] not in ("completed", "failed"):
                continue
            if job["status"] != expected:
                raise RuntimeError(f"Unexpected outcome for {job_id}: {job}")
            if expected == "completed" and "QUEUESCALE" not in job["result"].upper():
                raise RuntimeError(f"Expected OCR text for {job_id}: {job}")
            if expected == "failed" and job["attempts"] != 3:
                raise RuntimeError(f"Expected three attempts for {job_id}: {job}")
            waiting.remove(job_id)
        if waiting:
            time.sleep(1)
    if waiting:
        raise TimeoutError(f"{len(waiting)} of {len(ids)} jobs still unfinished")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--negative-tests", action="store_true")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")

    start = time.monotonic()
    data = SAMPLE.read_bytes()
    ids = [upload(args.url, data) for _ in range(args.jobs)]
    print(f"Submitted {len(ids)} jobs; first job={ids[0]}", flush=True)
    wait_for_jobs(args.url, ids, args.timeout, "completed")
    print(f"Completed {len(ids)} jobs in {time.monotonic() - start:.1f}s")

    if args.negative_tests:
        try:
            upload(args.url, b"not an image")
        except HTTPError as exc:
            if exc.code != 415:
                raise
        else:
            raise AssertionError("An unsupported file was accepted")
        bad_id = upload(args.url, b"\x89PNG\r\n\x1a\n" + b"corrupt PNG")
        wait_for_jobs(args.url, [bad_id], args.timeout, "failed")
        print("Verified unsupported upload and bounded OCR retries")


if __name__ == "__main__":
    main()
