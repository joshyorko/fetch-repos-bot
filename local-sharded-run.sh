#!/bin/bash

# Local Sharded Run Script - Emulates GitHub Actions workflow
# This script mimics the producer-consumer matrix workflow locally

set -e  # Exit on any error

echo "🚀 Starting Local Sharded Workflow"
echo "=================================="

# Configuration
MAX_WORKERS=${1:-3}  # Default to 3 workers if not specified
echo "📊 Max Workers: $MAX_WORKERS"

# Clean up previous runs
echo "🧹 Cleaning up previous runs..."
rm -rf output/
mkdir -p output/producer-to-consumer
mkdir -p output/consumer-to-reporter
mkdir -p output/screenshots

# Step 1: Producer Task
echo ""
echo "🏭 Step 1: Running Producer Task"
echo "================================"
rcc run -t "producer" -e "./devdata/env-for-producer.json"

# Capture producer logs
if [ -f "output/log.html" ]; then
    mv output/log.html output/producer-to-consumer/producer-logs.html
    echo "✅ Producer logs captured"
else
    echo "⚠️ No producer logs found"
fi

# Step 2: Generate shards and matrix from producer output
echo ""
echo "🔀 Step 2: Generating Shards from Producer Output"
echo "================================================="
python3 scripts/generate_shards_and_matrix.py $MAX_WORKERS

# Check if shards were created
if [ ! -f "output/matrix-output.json" ]; then
    echo "❌ No matrix output found - exiting"
    exit 1
fi

# Get shard count
SHARD_COUNT=$(cat output/matrix-output.json | jq '.matrix.include | length')
echo "📊 Shards created: $SHARD_COUNT"

# Clean output directory except shards and producer logs (like in workflow)
find output -mindepth 1 -maxdepth 1 ! -name 'shards' ! -name 'producer-to-consumer' -exec rm -rf {} +
echo "✅ Cleaned output directory, kept shards and producer logs"

if [ "$SHARD_COUNT" -eq 0 ]; then
    echo "⚠️ No shards to process - running reporter only"
    # Jump to reporter
    mkdir -p output/consumer-to-reporter
    echo "[]" > output/consumer-to-reporter/work-items.json
else
    # Step 3: Consumer Tasks (parallel simulation)
    echo ""
    echo "🔧 Step 3: Running Consumer Tasks"
    echo "=================================="
    
    # Create consumer-to-reporter directory for shard outputs
    mkdir -p output/consumer-to-reporter
    
    # Process each shard
    for ((shard_id=0; shard_id<$SHARD_COUNT; shard_id++)); do
        echo "  🔍 Processing Shard $shard_id..."
        
        # Create shard-specific environment
        SHARD_PATH="output/shards/work-items-shard-${shard_id}.json"
        OUTPUT_PATH="output/consumer-to-reporter/work-items-${shard_id}.json"
        
        # Update consumer env file for this shard
        jq -n \
            --arg adapter "FileAdapter" \
            --arg input_path "$SHARD_PATH" \
            --arg output_path "$OUTPUT_PATH" \
            '{
                "RC_WORKITEM_ADAPTER": $adapter,
                "RC_WORKITEM_INPUT_PATH": $input_path,
                "RC_WORKITEM_OUTPUT_PATH": $output_path
            }' > devdata/env-for-consumer-shard-${shard_id}.json
        
        # Run consumer for this shard
        echo "    🏃 Running consumer for shard $shard_id..."
        SHARD_ID=$shard_id rcc run -t "consumer" -e "devdata/env-for-consumer-shard-${shard_id}.json"
        
        # Capture consumer shard logs
        if [ -f "output/log.html" ]; then
            mv output/log.html "output/consumer-to-reporter/consumer-shard-${shard_id}-logs.html"
            echo "    ✅ Shard $shard_id logs captured"
        else
            echo "    ⚠️ No logs found for shard $shard_id - creating placeholder"
            echo "<html><body><h1>No log generated for shard $shard_id</h1></body></html>" > "output/consumer-to-reporter/consumer-shard-${shard_id}-logs.html"
        fi
        
        # Clean up shard-specific env file
        rm -f "devdata/env-for-consumer-shard-${shard_id}.json"
        
        echo "    ✅ Shard $shard_id completed"
    done
    
    # Step 4: Combine shard outputs
    echo ""
    echo "🔗 Step 4: Combining Shard Outputs"
    echo "=================================="
    
    # Combine all work-items JSON files
    work_items_files=$(find output/consumer-to-reporter -name "work-items-*.json" 2>/dev/null | sort)
    if [ -n "$work_items_files" ]; then
        echo "  📄 Combining work items from shards..."
        find output/consumer-to-reporter -name "work-items-*.json" -print0 | xargs -0 jq -s 'flatten' > output/consumer-to-reporter/work-items.json
        echo "  ✅ Work items combined successfully"
    else
        echo "  ⚠️ No work items found - creating empty array"
        echo "[]" > output/consumer-to-reporter/work-items.json
    fi
fi

# Clean output directory (keep only necessary files)
find output -mindepth 1 -maxdepth 1 ! -name 'shards' ! -name 'producer-to-consumer' ! -name 'consumer-to-reporter' ! -name 'screenshots' -exec rm -rf {} +

# Step 5a: Backup consumer outputs before reporter runs
echo ""
echo "🗄️ Step 5a: Backing up Consumer Outputs"
echo "========================================"

# Create backup directory structure
mkdir -p output/backup-consumer-to-reporter

# Backup consumer-to-reporter data (including work items with S3 bucket info)
if [ -d "output/consumer-to-reporter" ]; then
    cp -r output/consumer-to-reporter/* output/backup-consumer-to-reporter/
    echo "✅ Consumer outputs backed up"
else
    echo "⚠️ No consumer outputs to backup"
fi

# Step 5: Reporter Task
echo ""
echo "📊 Step 5: Running Reporter Task"
echo "================================"
rcc run -t "reporter" -e "./devdata/env-for-reporter.json"

# Capture reporter logs
if [ -f "output/log.html" ]; then
    cp output/log.html output/reporter-logs.html
    echo "✅ Reporter logs captured"
else
    echo "⚠️ No reporter logs found"
fi

# Step 6: Organize directory structure for dashboard (emulate workflow)
echo ""
echo "🏗️ Step 6: Organizing Dashboard Structure"
echo "========================================="

# Create consolidated dashboard directory structure
mkdir -p output/all-artifacts/producer-output/producer-to-consumer
mkdir -p output/all-artifacts/reporter-output/consumer-to-reporter
mkdir -p output/all-artifacts/reporter-output

# Copy producer artifacts
if [ -f "output/producer-to-consumer/producer-logs.html" ]; then
    cp output/producer-to-consumer/producer-logs.html output/all-artifacts/producer-output/producer-to-consumer/producer-logs.html
    echo "✅ Producer artifacts organized"
fi

# Copy reporter artifacts
if [ -f "output/reporter-logs.html" ]; then
    cp output/reporter-logs.html output/all-artifacts/reporter-output/reporter-logs.html
fi
if [ -f "output/reporter_summary.json" ]; then
    cp output/reporter_summary.json output/all-artifacts/reporter-output/reporter_summary.json
fi
if [ -d "output/consumer-to-reporter" ]; then
    cp -r output/consumer-to-reporter/* output/all-artifacts/reporter-output/consumer-to-reporter/
fi

# Create shard artifacts for each shard
if [ "$SHARD_COUNT" -gt 0 ]; then
    for ((shard_id=0; shard_id<$SHARD_COUNT; shard_id++)); do
        shard_artifact_dir="output/all-artifacts/shard-output-${shard_id}"
        mkdir -p "$shard_artifact_dir/consumer-to-reporter"
        
        # Copy shard-specific logs
        if [ -f "output/consumer-to-reporter/consumer-shard-${shard_id}-logs.html" ]; then
            cp "output/consumer-to-reporter/consumer-shard-${shard_id}-logs.html" "$shard_artifact_dir/consumer-to-reporter/"
            echo "✅ Shard $shard_id artifacts organized"
        fi
        
        # Copy any screenshots for this shard (if they exist)
        if [ -d "output/screenshots" ]; then
            mkdir -p "$shard_artifact_dir/screenshots"
            cp -r output/screenshots/* "$shard_artifact_dir/screenshots/" 2>/dev/null || true
        fi
    done
fi

# Now reorganize for dashboard generation (emulate the workflow step)
echo "  🏗️ Reorganizing for dashboard generation..."
rm -rf output/producer-to-consumer output/consumer-to-reporter output/screenshots
mkdir -p output/producer-to-consumer output/consumer-to-reporter output/screenshots

# Copy producer logs
if [ -f "output/all-artifacts/producer-output/producer-to-consumer/producer-logs.html" ]; then
    cp output/all-artifacts/producer-output/producer-to-consumer/producer-logs.html output/producer-to-consumer/producer-logs.html
    echo "  ✅ Producer logs copied"
else
    echo "  ⚠️ Producer logs not found"
fi

# Copy reporter logs (preserved with specific name)
if [ -f "output/all-artifacts/reporter-output/reporter-logs.html" ]; then
    cp output/all-artifacts/reporter-output/reporter-logs.html output/reporter-logs.html
    echo "  ✅ Reporter logs copied"
else
    echo "  ⚠️ Reporter logs not found"
fi

# Copy reporter summary
if [ -f "output/all-artifacts/reporter-output/reporter_summary.json" ]; then
    cp output/all-artifacts/reporter-output/reporter_summary.json output/reporter_summary.json
    echo "  ✅ Reporter summary copied"
fi

# Copy consumer-to-reporter data from backup (preserves S3 bucket info)
if [ -d "output/backup-consumer-to-reporter" ]; then
    cp -r output/backup-consumer-to-reporter/* output/consumer-to-reporter/
    echo "  ✅ Consumer-to-reporter data copied from backup (preserves S3 bucket info)"
else
    echo "  ⚠️ No backup consumer-to-reporter data found"
    # Fallback to reporter artifact if backup doesn't exist
    if [ -d "output/all-artifacts/reporter-output/consumer-to-reporter" ]; then
        cp -r output/all-artifacts/reporter-output/consumer-to-reporter/* output/consumer-to-reporter/
        echo "  ✅ Consumer-to-reporter data copied from reporter artifact (fallback)"
    fi
fi

# Process consumer shard logs from all shard artifacts
echo "  📝 Processing shard artifacts..."
shard_logs_found=0
for shard_dir in output/all-artifacts/shard-output-*; do
    if [ -d "$shard_dir" ]; then
        shard_id=$(basename "$shard_dir" | sed 's/shard-output-//')
        echo "  🔍 Processing shard: $shard_id"
        
        # Copy individual shard log if it exists
        expected_log_path="$shard_dir/consumer-to-reporter/consumer-shard-${shard_id}-logs.html"
        if [ -f "$expected_log_path" ]; then
            cp "$expected_log_path" "output/consumer-to-reporter/consumer-shard-${shard_id}-logs.html"
            echo "    ✅ Shard $shard_id logs copied successfully"
            shard_logs_found=$((shard_logs_found + 1))
        else
            echo "    ⚠️ Expected log not found: $expected_log_path"
        fi
        
        # Copy screenshots from this shard
        if [ -d "$shard_dir/screenshots" ]; then
            cp -r "$shard_dir/screenshots/"* "output/screenshots/" 2>/dev/null || true
            echo "    ✅ Shard $shard_id screenshots merged"
        fi
    fi
done

echo "  📊 Shard processing summary: Found and copied $shard_logs_found consumer shard log files"

# No consolidation: keep each consumer-shard-*-logs.html file for dashboard to enumerate individually
if [ "$shard_logs_found" -eq 0 ]; then
    echo "  ⚠️ No consumer shard logs found - creating placeholder file"
    printf '<!DOCTYPE html>\n<html>\n<head>\n    <title>Consumer Logs - No Shards</title>\n</head>\n<body>\n    <h1>No Consumer Logs Available</h1>\n    <p>No consumer shard logs were found.</p>\n</body>\n</html>\n' > "output/consumer-to-reporter/consumer-logs.html"
fi

echo "  📊 Final directory structure:"
find output -type f -name "*.html" -o -name "*.json" | grep -v all-artifacts | sort

# Step 7: Generate Consolidated Dashboard
echo ""
echo "📊 Step 7: Generating Consolidated Dashboard"
echo "============================================"
rcc run -t "GenerateConsolidatedDashboard"

# Verify dashboard was created
if [ -f "output/consolidated_dashboard_jinja2.html" ]; then
    echo "✅ Dashboard generated successfully"
    echo "📊 Dashboard size: $(du -h output/consolidated_dashboard_jinja2.html | cut -f1)"
else
    echo "❌ Dashboard generation failed"
    exit 1
fi

# Step 8: Archive Outputs
echo ""
echo "📦 Step 8: Archiving Outputs"
echo "============================"
rcc run -t "ArchiveOutputs"

echo ""
echo "🎉 Local Sharded Workflow Completed Successfully!"
echo "================================================="
echo "📁 Generated files:"
ls -lh output/consolidated_dashboard_jinja2.html output/consolidated_data.json output/reporter-logs.html 2>/dev/null || echo "Some files not found"
echo ""
echo "🌐 Open output/consolidated_dashboard_jinja2.html in your browser to view the dashboard"
echo "📊 Individual shard logs available in output/consumer-to-reporter/consumer-shard-*-logs.html"
echo "📋 Reporter logs available in output/reporter-logs.html"
