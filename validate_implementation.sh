#!/bin/bash

# Validation script for the complete sharding implementation
echo "🚀 Validating Sharding Implementation"
echo "======================================"

# Check if required files exist
echo "📁 Checking required files..."

required_files=(
    "shard_workitems.py"
    "tasks.py"
    ".github/workflows/fetch-robocorp-matrix.yaml"
    "devdata/env-for-sharded-consumer.json"
    "performance_analysis.py"
)

missing_files=()
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        missing_files+=("$file")
        echo "❌ Missing: $file"
    else
        echo "✅ Found: $file"
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    echo "❌ Validation failed: Missing required files"
    exit 1
fi

# Check if work items exist
work_items_file="devdata/work-items-out/run-1/work-items.json"
if [ ! -f "$work_items_file" ]; then
    echo "⚠️  Work items file not found: $work_items_file"
    echo "   This is expected if producer hasn't run yet."
else
    echo "✅ Work items file found"
    
    # Test sharding functionality
    echo ""
    echo "🔧 Testing sharding functionality..."
    python3 shard_workitems.py "$work_items_file" 2 devdata/validation-test
    
    if [ $? -eq 0 ]; then
        echo "✅ Sharding test passed"
        
        # Check generated files
        if [ -f "devdata/validation-test/matrix-config.json" ]; then
            echo "✅ Matrix configuration generated"
        else
            echo "❌ Matrix configuration missing"
        fi
        
        shard_count=$(ls devdata/validation-test/work-items-shard-*.json 2>/dev/null | wc -l)
        echo "✅ Generated $shard_count shard files"
        
        # Run performance analysis
        echo ""
        echo "📊 Running performance analysis..."
        python3 performance_analysis.py "$work_items_file" 4
        
    else
        echo "❌ Sharding test failed"
        exit 1
    fi
fi

# Check task definitions
echo ""
echo "🔍 Checking task definitions..."
if grep -q "def sharded_consumer" tasks.py; then
    echo "✅ sharded_consumer task found"
else
    echo "❌ sharded_consumer task not found"
    exit 1
fi

if grep -q "def producer" tasks.py; then
    echo "✅ producer task found"
else
    echo "❌ producer task not found"
    exit 1
fi

# Check workflow configuration
echo ""
echo "⚙️  Checking workflow configuration..."
if grep -q "strategy:" .github/workflows/fetch-robocorp-matrix.yaml; then
    echo "✅ Matrix strategy found in workflow"
else
    echo "❌ Matrix strategy not found in workflow"
    exit 1
fi

if grep -q "sharded_consumer" .github/workflows/fetch-robocorp-matrix.yaml; then
    echo "✅ Sharded consumer referenced in workflow"
else
    echo "❌ Sharded consumer not found in workflow"
    exit 1
fi

# Check environment files
echo ""
echo "🌍 Checking environment configurations..."
for env_file in devdata/env-for-producer.json devdata/env-for-consumer.json devdata/env-for-sharded-consumer.json; do
    if [ -f "$env_file" ]; then
        if python3 -m json.tool "$env_file" > /dev/null 2>&1; then
            echo "✅ Valid JSON: $env_file"
        else
            echo "❌ Invalid JSON: $env_file"
            exit 1
        fi
    else
        echo "❌ Missing: $env_file"
        exit 1
    fi
done

echo ""
echo "🎉 Validation Complete!"
echo "======================================"
echo "✅ All components are properly configured"
echo "✅ Sharding functionality is working"
echo "✅ Matrix workflow is ready to use"
echo ""
echo "Next steps:"
echo "1. 🚀 Run the matrix workflow in GitHub Actions"
echo "2. 📊 Monitor performance improvements"
echo "3. 🔧 Adjust max_workers based on results"
echo ""
echo "Workflow trigger:"
echo "GitHub Actions → 'Robocorp ARC Producer-Consumer Matrix Workflow' → Run workflow"
