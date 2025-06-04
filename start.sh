#!/bin/bash
set -euo pipefail

# Number of parallel workers (shards) can be supplied as the first argument.
# Defaults to 3 if not provided.
MAX_WORKERS="${1:-3}"

# Optional organization name can be provided via the ORG_NAME environment
# variable. It falls back to the value defined in the producer environment file.

mkdir -p devdata/work-items-in/input-for-producer
if [ -n "${ORG_NAME:-}" ]; then
  echo "[{\"payload\": {\"org\": \"${ORG_NAME}\"}}]" > \
    devdata/work-items-in/input-for-producer/work-items.json
fi

# Run producer step
rcc run -t producer -e devdata/env-for-producer.json

# Generate shards based on the desired worker count
python3 scripts/generate_shards_and_matrix.py "$MAX_WORKERS"

# Iterate over generated shard files and run the consumer for each shard.
for SHARD_PATH in output/shards/work-items-shard-*.json; do
  [ -e "$SHARD_PATH" ] || continue
  SHARD_ID="$(basename "$SHARD_PATH" | grep -oE '[0-9]+')"

  cat > devdata/env-for-consumer.json <<EOF
{
  "RC_WORKITEM_ADAPTER": "FileAdapter",
  "RC_WORKITEM_INPUT_PATH": "$SHARD_PATH",
  "RC_WORKITEM_OUTPUT_PATH": "output/consumer-to-reporter/work-items-${SHARD_ID}.json"
}
EOF

  echo "Running consumer for shard ${SHARD_ID} using ${SHARD_PATH}"
  SHARD_ID="$SHARD_ID" rcc run -t consumer -e devdata/env-for-consumer.json
done

