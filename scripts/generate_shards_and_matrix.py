import json
import math
from pathlib import Path
import sys

def main(max_workers):
    # Read work items from producer output
    with open('output/producer-to-consumer/work-items.json', 'r') as f:
        work_items = json.load(f)
    max_workers = int(max_workers)
    total = len(work_items)
    per_shard = math.ceil(total / max_workers) if total > 0 else 0
    # Create shards
    shards_dir = Path('output/shards')
    shards_dir.mkdir(exist_ok=True)
    matrix_include = []
    for i in range(max_workers):
        start_idx = i * per_shard
        end_idx = min(start_idx + per_shard, total)
        if start_idx < total:
            shard_items = work_items[start_idx:end_idx]
            shard_file = shards_dir / f'work-items-shard-{i}.json'
            with open(shard_file, 'w') as f:
                json.dump(shard_items, f)
            matrix_include.append({'shard_id': i})
            print(f'Created shard {i} with {len(shard_items)} items')
    # Save matrix config
    matrix_config = {'matrix': {'include': matrix_include}}
    with open('output/matrix-output.json', 'w') as f:
        json.dump(matrix_config, f)
    print(f'Generated matrix with {len(matrix_include)} shards')

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 generate_shards_and_matrix.py <max_workers>")
        sys.exit(1)
    main(sys.argv[1])
