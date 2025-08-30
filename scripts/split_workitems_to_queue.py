#!/usr/bin/env python3
import json
import os
from pathlib import Path
import uuid


def main():
    src = Path("output/producer-to-consumer/work-items.json")
    if not src.exists():
        raise SystemExit(f"Source work items not found: {src}")

    with src.open("r") as f:
        items = json.load(f)

    # Normalize to list of objects with 'payload'
    if isinstance(items, dict):
        items = [items]

    if not isinstance(items, list):
        raise SystemExit("Expected a JSON array of work items")

    # Support shared queue base via env var
    queue_base = os.environ.get("QUEUE_BASE", "output/queue")
    base = Path(queue_base)
    todo = base / "todo"
    processing = base / "processing"
    done = base / "done"
    failed = base / "failed"
    for d in (todo, processing, done, failed):
        d.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in items:
        # Ensure item is a proper work item format
        if not isinstance(item, dict) or "payload" not in item:
            item = {"payload": item}

        # Create a single-item file for FileAdapter compatibility
        work = [item]
        file_id = uuid.uuid4().hex
        dest = todo / f"wi-{file_id}.json"
        with dest.open("w") as f:
            json.dump(work, f)
        count += 1

    print(f"Enqueued {count} work items into {todo}")


if __name__ == "__main__":
    main()
