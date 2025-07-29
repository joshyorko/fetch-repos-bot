# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Local Development:**
- `./start.sh [MAX_WORKERS]` - Run the complete producer-consumer pipeline locally
  - MAX_WORKERS defaults to 3 if not provided
  - Set `ORG_NAME` environment variable to override target organization
  - Uses RCC for environment isolation and task execution

**Individual Task Execution:**
- `rcc run -t "Producer" -e devdata/env-for-producer.json` - Run producer task only
- `rcc run -t "Consumer" -e devdata/env-for-consumer.json` - Run consumer task only  
- `rcc run -t "Reporter" -e devdata/env-for-reporter.json` - Run reporter task only

**Testing:**
- `python -m pytest tests/` - Run test suite
- `python -m pytest tests/test_generate_shards_and_matrix.py` - Run specific test

**Matrix Generation:**
- `python scripts/generate_shards_and_matrix.py <MAX_WORKERS>` - Generate shards and GitHub Actions matrix

## Architecture Overview

This is a **Robocorp RPA bot** implementing a producer-consumer pattern with matrix sharding for GitHub repository processing at scale. The architecture follows a three-stage pipeline:

### Core Components

**1. Producer (`tasks.py:producer()`):**
- Fetches repository metadata from GitHub organizations using `scripts/fetch_repos.py`
- Creates work items for each repository
- Outputs to `output/producer-to-consumer/work-items.json`

**2. Consumer (`tasks.py:consumer()`):**
- Processes repository work items by cloning repos
- Uses GitPython for shallow clones with error handling
- Creates ZIP archives of cloned repositories
- Supports sharding for parallel execution
- Outputs processing reports and ZIP files

**3. Reporter (`tasks.py:reporter()`):**
- Aggregates results from all consumer shards
- Generates comprehensive processing statistics
- Creates final reports with success rates and error details

### Key Architectural Patterns

**Matrix Sharding:**
- `scripts/generate_shards_and_matrix.py` splits work items across parallel workers
- Each shard gets processed by independent consumer instances
- Enables massive parallelism in GitHub Actions workflows

**Environment Isolation:**
- All tasks run in RCC-managed environments defined by `robot.yaml` and `conda.yaml`
- Environment is automatically rebuilt only when dependencies change
- Supports local development and CI/CD execution

**Work Item Flow:**
```
Producer → work-items.json → Sharding → [work-items-shard-0.json, work-items-shard-1.json, ...] → Consumer instances → Reporter
```

**Error Handling:**
- Network errors result in "released" status for retry
- Git errors are categorized and handled appropriately  
- Comprehensive error logging and status tracking

## Project Structure Notes

- `robot.yaml` - Robocorp task definitions and RCC configuration
- `conda.yaml` - Python environment specification managed by RCC
- `pyproject.toml` - Robocorp logging configuration only
- `devdata/` - Environment configurations for each task (producer, consumer, reporter)
- `scripts/` - Utility scripts for repo fetching, sharding, and GitHub Actions integration
- `output/` - Task outputs, ZIP archives, and processing reports
- `.github/workflows/` - GitHub Actions workflows for matrix-based parallel execution

## Development Notes

- **RCC Dependency:** All task execution requires RCC (Robocorp Control Room) for environment management
- **Sharding Logic:** The system automatically adjusts shard count based on available work items
- **Repository Cleanup:** Consumer tasks automatically clean up cloned repositories after ZIP creation
- **Idempotency:** Tasks are designed to be rerunnable without side effects
- **GitHub Rate Limits:** Uses authenticated GitHub API calls (configure with appropriate tokens)

## GitHub Actions Integration

The project includes workflows for:
- Building custom runner Docker images with pre-installed dependencies
- Matrix-based parallel execution across multiple GitHub Actions runners
- Both hosted and self-hosted runner support
- Automatic Docker image rebuilds when environment files change