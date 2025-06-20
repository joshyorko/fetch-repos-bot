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

    if total == 0:
        print("No work items to process, creating empty matrix.")
        matrix_config = {'matrix': {'include': []}}
        with open('output/matrix-output.json', 'w') as f:
            json.dump(matrix_config, f)
        print("Generated empty matrix.")
        return

    # Adjust number of workers based on item count
    num_workers = min(max_workers, total)
    per_shard = math.ceil(total / num_workers)

    # Create shards
    shards_dir = Path('output/shards')
    shards_dir.mkdir(exist_ok=True)
    matrix_include = []
    for i in range(num_workers):
        start_idx = i * per_shard
        end_idx = min(start_idx + per_shard, total)
        if start_idx >= total:
            break  # No more items to process
        shard_items = work_items[start_idx:end_idx]
        if not shard_items:
            continue  # Should not happen with the break, but as a safeguard
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
