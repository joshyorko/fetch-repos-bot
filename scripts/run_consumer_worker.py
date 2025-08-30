#!/usr/bin/env python3
import json
import os
import subprocess
import time
from pathlib import Path


def atomic_claim(todo_dir: Path, processing_dir: Path) -> Path | None:
    # List candidate files
    for p in sorted(todo_dir.glob("*.json")):
        target = processing_dir / p.name
        try:
            p.rename(target)  # atomic on same filesystem
            return target
        except FileNotFoundError:
            # Lost race, try next
            continue
        except OSError:
            continue
    return None


def run_consumer_for_file(claimed: Path, worker_id: str, seq: int, org_name: str | None) -> bool:
    out_dir = Path("output/consumer-to-reporter")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Unique output file per run to avoid collisions
    output_file = out_dir / f"work-items-{worker_id}-{seq}.json"

    # Create a temp env file for FileAdapter
    env = {
        "RC_WORKITEM_ADAPTER": "FileAdapter",
        "RC_WORKITEM_INPUT_PATH": str(claimed),
        "RC_WORKITEM_OUTPUT_PATH": str(output_file),
    }
    env_file = Path(f"devdata/env-consumer-{worker_id}-{seq}.json")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    with env_file.open("w") as f:
        json.dump(env, f)

    # Use SHARD_ID only for output naming in tasks.py (zip/report)
    shard_id = f"{worker_id}-{seq}"
    run_env = os.environ.copy()
    run_env["SHARD_ID"] = shard_id
    if org_name:
        run_env["ORG_NAME"] = org_name

    print(f"Worker {worker_id} processing {claimed.name} -> {output_file.name}")
    res = subprocess.run(
        ["rcc", "run", "-t", "consumer", "-e", str(env_file)],
        env=run_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(res.stdout)
    return res.returncode == 0


def main():
    # Allow shared queue directory via env var
    queue_base = os.environ.get("QUEUE_BASE", "output/queue")
    base = Path(queue_base)
    todo = base / "todo"
    processing = base / "processing"
    done = base / "done"
    failed = base / "failed"
    for d in (todo, processing, done, failed):
        d.mkdir(parents=True, exist_ok=True)

    worker_id = os.environ.get("WORKER_ID", "0")
    org_name = os.environ.get("ORG_NAME")
    max_items = int(os.environ.get("MAX_ITEMS_PER_WORKER", "0") or 0)  # 0 = unlimited
    max_seconds = int(os.environ.get("MAX_DURATION_SEC", "0") or 0)

    start = time.time()
    processed = 0
    seq = 0

    while True:
        # Time budget check
        if max_seconds and time.time() - start > max_seconds:
            print(f"Worker {worker_id} reached time budget; exiting.")
            break
        # Throughput cap check
        if max_items and processed >= max_items:
            print(f"Worker {worker_id} reached item limit; exiting.")
            break

        claim = atomic_claim(todo, processing)
        if not claim:
            print(f"Worker {worker_id} found no items; exiting.")
            break

        ok = False
        try:
            ok = run_consumer_for_file(claim, worker_id, seq, org_name)
        except Exception as e:
            print(f"Worker {worker_id} error: {e}")
            ok = False

        # Move to terminal state
        target = done / claim.name if ok else failed / claim.name
        try:
            claim.rename(target)
        except OSError:
            # Best-effort; leave in processing if move fails
            pass

        processed += 1
        seq += 1

    print(f"Worker {worker_id} processed {processed} items.")


if __name__ == "__main__":
    main()
