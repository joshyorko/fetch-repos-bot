---
title: fetch-repos-bot - Automated GitHub Repo Fetching & RPA Pipeline
author: Joshua Yorko, [@joshyorko](https://github.com/joshyorko), joshua.yorko@gmail.com
---
[![Open in DevPod!](https://devpod.sh/assets/open-in-devpod.svg)](https://devpod.sh/open#https://github.com/joshyorko/fetch-repos-bot)
# fetch-repos-bot



<p align="center">
  <img src="assets/logo.png" alt="Project Logo" width="600"/>
</p>


## Overview

**fetch-repos-bot** is a reference implementation and prototype of a highly scalable, production-grade Robocorp producer-consumer robot pattern—demonstrating advanced orchestration, sharding, and parallelism beyond what is available in official Robocorp examples. This project automates the fetching, processing, and management of GitHub repositories from any organization, using a robust, matrix-sharded producer-consumer architecture. It is designed for true scale: leveraging RCC for environment isolation, Python for orchestration, and GitHub Actions for distributed, parallel execution. The approach here can serve as a blueprint for building large-scale, cloud-native RPA pipelines with Robocorp, and is suitable for both local and CI/CD automation.

Key highlights:
- **True producer-consumer separation** with artifact handoff and sharded work distribution.
- **Matrix sharding** for massive parallelism—each consumer job processes a unique shard, maximizing throughput.
- **RCC-managed environments** ensure reproducibility and isolation, with Docker image rebuilds only when the robot or environment definition changes.
- **Extensible and transparent**: All orchestration logic, environment management, and workflow automation is open and customizable, making this repo a practical foundation for advanced RPA and automation engineering.

---

## Features
- **Producer-Consumer Architecture:** Efficiently splits work between producer (fetches and shards repo data) and consumer (processes shards in parallel).
- **Matrix Sharding:** Dynamically divides work items into shards for parallel processing, maximizing throughput.
- **Robocorp RCC Integration:** Uses RCC for environment management and task execution.
- **GitHub Actions Workflows:** Includes advanced workflows for both single and matrix-based execution, supporting custom runners and scalable automation.
- **Python & Conda Environment:** All dependencies are managed via `conda.yaml` for reproducibility.
- **RCC-Managed Environments:** All environments are fully managed and isolated by [Robocorp RCC](https://robocorp.com/docs/rcc/), ensuring reproducibility and separation from the host system. The robot environment is defined by `robot.yaml` and `conda.yaml`, but RCC handles all environment creation and management for both local and CI runs.
- **Docker Image Rebuilds:** The custom runner Docker image is only rebuilt if `conda.yaml`, `robot.yaml`, or the `Dockerfile` itself changes. For all other code or workflow changes, the environment remains stable and isolated by RCC.

---

## Project Structure

- `assets/logo.png` — Project logo.
- `assets/process.png` — Diagram or process illustration for the project.
- `start.sh` — Local entrypoint to run the full producer-consumer pipeline for local testing and development. This script allows you to execute the entire workflow on your machine, simulating the GitHub Actions process without requiring a remote runner. For more details on Robocorp tasks and local execution, see the [Robocorp Tasks documentation](https://robocorp.com/docs/development-guide/tasks/).
- `robot.yaml` — Robocorp robot configuration, defines tasks, environments, and references to `conda.yaml`.
- `conda.yaml` — Conda environment specification referenced by RCC; actual environment is built and managed by RCC for full isolation.
- `tasks.py` — Main Python file with Robocorp task definitions for producer and consumer.
- `scripts/` — Helper scripts:
  - `generate_shards_and_matrix.py` — Splits work items into shards and generates the matrix for parallel processing.
  - `fetch_repos.py` — Logic for fetching repositories.
  - `extract-secrets-for-ga.sh` — Extracts secrets for GitHub Actions workflows.
  - `install-upgrade-arc.sh` — Installs or upgrades ARC runner and selects values files.
  - `remove_finalizers_arc_runners.sh` — Removes Kubernetes finalizers from ARC runner resources.
  - `shard_loader.py` — Loads and processes shards for matrix jobs.
- `devdata/` — Input/output data, environment files, and work items:
  - `env-for-consumer.json` — Environment variables for the consumer.
  - `env-for-producer.json` — Environment variables for the producer.
- `output/` — Output directory for artifacts and results.
- `.github/workflows/` — Contains GitHub Actions workflows:
  - `build-arc-docker.yaml` — Builds and pushes the Fetch Repos Bot Runner Docker image, updates image tags, and creates PRs for tag bumps.
  - `build-kaniko-docker.yaml` — Builds and pushes Docker images using Kaniko for environments where Docker-in-Docker is not available.
  - `fetch-repos-matrix-hosted.yaml` — Matrix-based workflow for hosted runners.
  - `fetch-repos-matrix-self-hosted.yaml` — Matrix-based workflow for self-hosted runners.
- `repos/` — Contains files for building a custom GitHub Actions Runner image with pre-installed dependencies:
  - `Dockerfile` — Defines the Docker image build process. **Note:** The image is only rebuilt if `Dockerfile`, `conda.yaml`, or `robot.yaml` change. RCC ensures the robot environment is always isolated and reproducible.
  - `conda.yaml` — Conda environment specification for the Docker image, ensuring necessary Python packages are available.
  - `robot.yaml` — Robocorp robot configuration specific to the Docker environment, if needed.
  - `values.yaml` — Configuration values, potentially for deploying the runner in a Kubernetes environment (e.g., defining resources, image name).

---

## How It Works

1. **Producer Step:**
   - Fetches repository data from the specified GitHub organization.
   - Generates work items and shards them for parallel processing (if using matrix workflow).
   - Uploads output artifacts for consumers.

2. **Consumer Step:**
   - Downloads the relevant shard or work items.
   - Processes each repository as defined in the consumer task.
   - Uploads results as artifacts.

3. **Matrix Workflow:**
   - Uses `generate_shards_and_matrix.py` to split work and create a matrix for parallel jobs in GitHub Actions.
   - Each consumer job processes a shard, maximizing efficiency.

---

## Running Locally

1. **Install RCC:**
   - Download and install RCC from [Robocorp](https://robocorp.com/docs/rcc/installation/).

2. **Run the Pipeline:**
   ```bash
   ./start.sh [MAX_WORKERS]
   ```
   - `MAX_WORKERS` (optional) sets how many shards to create. Defaults to `3`.
   - Set `ORG_NAME` before running if you want to override the organization used
     for the producer.

   The script now runs the consumer once for each shard so you can test the
   sharding workflow locally.

3. **Custom Execution:**
   - You can run individual tasks using RCC or Python as defined in `robot.yaml`.

---

## GitHub Actions Workflows

- **fetch-repos-matrix.yaml:**
  - The primary workflow for this project.
  - Supports parallel consumer jobs using matrix strategy.
  - Accepts `org_name` and `max_workers` as inputs.
  - Can be configured to use the custom Docker image built from the `repos` directory for self-hosted runners, ensuring all dependencies are pre-installed for faster and more reliable execution.

---

## Environment & Dependencies

- All environments are managed and isolated by RCC. You do not need to manually manage Python or Conda environments.
- The robot environment is defined by `robot.yaml` and `conda.yaml`, but RCC ensures reproducibility and isolation for both local and CI runs.
- The Docker image is only rebuilt if `conda.yaml`, `robot.yaml`, or the `Dockerfile` changes. For all other changes, the environment remains stable.
- See `conda.yaml` for the base dependencies, but rely on RCC for all environment management.

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

---

## Contributing

Contributions are welcome! Please open issues or submit pull requests for improvements, bug fixes, or new features.

---

### Contributors

![Contributors](https://contrib.nn.ci/api?repo=joshyorko/fetch-repos-bot)

## References
- [Robocorp Documentation](https://robocorp.com/docs/)
- [RCC Documentation](https://github.com/robocorp/rcc)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
