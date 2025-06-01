#!/bin/bash

# Test script for the sharding functionality
echo "Testing sharding functionality..."

# Check if work items file exists
WORK_ITEMS_FILE="devdata/work-items-out/run-1/work-items.json"
if [ ! -f "$WORK_ITEMS_FILE" ]; then
    echo "Work items file not found: $WORK_ITEMS_FILE"
    echo "Please run the producer first to generate work items."
    exit 1
fi

# Test sharding with different worker counts
echo "Testing with 4 workers..."
python shard_workitems.py "$WORK_ITEMS_FILE" 4 devdata/test-shards-4

echo -e "\nTesting with 2 workers..."
python shard_workitems.py "$WORK_ITEMS_FILE" 2 devdata/test-shards-2

echo -e "\nTesting with 8 workers (more than items)..."
python shard_workitems.py "$WORK_ITEMS_FILE" 8 devdata/test-shards-8

echo -e "\nSharding tests completed!"
echo "Check the devdata/test-shards-* directories for results."
