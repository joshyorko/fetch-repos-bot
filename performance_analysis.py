#!/usr/bin/env python3
"""
Performance comparison script for sequential vs matrix processing.
This script analyzes work items and provides estimates of performance improvements.
"""

import json
import sys
from pathlib import Path


def analyze_work_items(work_items_file: str, max_workers: int = 4):
    """Analyze work items and provide performance estimates."""
    
    try:
        with open(work_items_file, 'r') as f:
            work_items = json.load(f)
    except FileNotFoundError:
        print(f"Error: Work items file not found: {work_items_file}")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in work items file: {e}")
        return
    
    # Filter valid work items
    valid_items = [item for item in work_items if item.get('payload')]
    total_repos = len(valid_items)
    
    if total_repos == 0:
        print("No valid repositories found in work items")
        return
    
    print("=" * 60)
    print("PERFORMANCE ANALYSIS")
    print("=" * 60)
    
    print(f"Total Repositories: {total_repos}")
    print(f"Max Workers: {max_workers}")
    
    # Calculate sharding distribution
    actual_workers = min(max_workers, total_repos)
    items_per_shard = (total_repos + actual_workers - 1) // actual_workers
    
    print(f"Actual Workers: {actual_workers}")
    print(f"Items per Shard: {items_per_shard}")
    
    print("\n" + "=" * 60)
    print("EXECUTION TIME ESTIMATES")
    print("=" * 60)
    
    # Assumptions for timing estimates
    avg_clone_time = 30  # seconds per repository
    setup_overhead = 60  # seconds for job setup
    
    # Sequential processing
    sequential_time = total_repos * avg_clone_time + setup_overhead
    
    # Parallel processing
    parallel_time = items_per_shard * avg_clone_time + setup_overhead
    
    print(f"Sequential Processing:")
    print(f"  Estimated Time: {sequential_time / 60:.1f} minutes")
    print(f"  ({total_repos} repos × {avg_clone_time}s + {setup_overhead}s setup)")
    
    print(f"\nParallel Processing ({actual_workers} workers):")
    print(f"  Estimated Time: {parallel_time / 60:.1f} minutes")
    print(f"  ({items_per_shard} repos × {avg_clone_time}s + {setup_overhead}s setup)")
    
    speedup = sequential_time / parallel_time
    time_saved = sequential_time - parallel_time
    
    print(f"\nPerformance Improvement:")
    print(f"  Speedup: {speedup:.1f}x faster")
    print(f"  Time Saved: {time_saved / 60:.1f} minutes")
    print(f"  Efficiency: {(1 - 1/speedup) * 100:.1f}% reduction in execution time")
    
    print("\n" + "=" * 60)
    print("REPOSITORY BREAKDOWN BY LANGUAGE")
    print("=" * 60)
    
    # Analyze repository languages
    languages = {}
    for item in valid_items:
        lang = item.get('payload', {}).get('Language') or 'Unknown'
        languages[lang] = languages.get(lang, 0) + 1
    
    for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_repos) * 100
        print(f"  {lang}: {count} repos ({percentage:.1f}%)")
    
    print("\n" + "=" * 60)
    print("SHARD DISTRIBUTION")
    print("=" * 60)
    
    for i in range(actual_workers):
        start_idx = i * items_per_shard
        end_idx = min(start_idx + items_per_shard, total_repos)
        shard_size = end_idx - start_idx
        print(f"  Shard {i}: {shard_size} repositories")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if total_repos <= 5:
        print("  • Consider sequential processing for small datasets")
    elif total_repos <= 20:
        print("  • Use 2-4 workers for optimal performance")
    else:
        print("  • Use 4-8 workers for large datasets")
        print("  • Monitor runner capacity to avoid resource contention")
    
    if speedup < 2:
        print("  • Limited speedup expected due to setup overhead")
    elif speedup >= 3:
        print("  • Significant performance improvement expected")
    
    print("  • Test with smaller datasets first")
    print("  • Monitor GitHub Actions runner availability")


def main():
    """Main function for command line execution."""
    if len(sys.argv) < 2:
        print("Usage: python3 performance_analysis.py <work_items_file> [max_workers]")
        print("Example: python3 performance_analysis.py devdata/work-items-out/run-1/work-items.json 4")
        sys.exit(1)
    
    work_items_file = sys.argv[1]
    max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    analyze_work_items(work_items_file, max_workers)


if __name__ == "__main__":
    main()
