#!/bin/bash
set -euo pipefail

# Number of parallel workers (shards) can be supplied as the first argument.
# Defaults to 3 if not provided.
MAX_WORKERS="${1:-3}"

# Optional organization name can be provided via the ORG_NAME environment
# variable. It falls back to the value defined in the producer environment file.

mkdir -p devdata/work-items-in/input-for-producer

# Only create/overwrite work-items.json if ORG_NAME is provided OR if the file doesn't exist
WORK_ITEMS_FILE="devdata/work-items-in/input-for-producer/work-items.json"
if [ -n "${ORG_NAME:-}" ]; then
  echo "[{\"payload\": {\"org\": \"${ORG_NAME}\"}}]" > "$WORK_ITEMS_FILE"
elif [ ! -f "$WORK_ITEMS_FILE" ]; then
  # Create a default work item only when the file doesn't exist and ORG_NAME isn't provided.
  # The organization will then be read from env-for-producer.json
  # by the producer task.
  echo "[{\"payload\": {}}]" > "$WORK_ITEMS_FILE"
fi

# Run producer step
rcc run -t "Producer" -e devdata/env-for-producer.json

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
  SHARD_ID="$SHARD_ID" rcc run -t "Consumer" -e devdata/env-for-consumer.json
done

# Combine all consumer outputs into a single file for the reporter
mkdir -p output/reporter-input
COMBINED_FILE="output/reporter-input/work-items.json"
echo "[" > "$COMBINED_FILE"

# Combine all consumer output files
FIRST_FILE=true
for CONSUMER_FILE in output/consumer-to-reporter/work-items-*.json; do
  [ -e "$CONSUMER_FILE" ] || continue
  if [ "$FIRST_FILE" = true ]; then
    FIRST_FILE=false
  else
    echo "," >> "$COMBINED_FILE"
  fi
  # Extract the payload from each consumer file and add it to the combined file
  cat "$CONSUMER_FILE" | jq -r '.[]' >> "$COMBINED_FILE"
done

echo "]" >> "$COMBINED_FILE"

# Create environment configuration for reporter
cat > devdata/env-for-reporter.json <<EOF
{
  "RC_WORKITEM_ADAPTER": "FileAdapter",
  "RC_WORKITEM_INPUT_PATH": "$COMBINED_FILE",
  "RC_WORKITEM_OUTPUT_PATH": "output/reporter-final/work-items.json"
}
EOF

# Run reporter step to process all consumer outputs
echo "Running reporter step"
rcc run -t "Reporter" -e devdata/env-for-reporter.json
