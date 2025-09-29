from pathlib import Path
from robocorp import workitems
from robocorp.tasks import get_output_dir, task
import shutil
import os
from git import Repo
from git.exc import GitCommandError
import json
import time
import subprocess
from typing import Dict, List, Optional, Tuple
from types import SimpleNamespace
try:
    # Assistant is optional at runtime; import guarded to avoid breaking existing tasks if dependency missing.
    from RPA.Assistant import Assistant  # Provided by rpaframework-assistant
    from RPA.Assistant.flet_client import TimeoutException
except ImportError:  # pragma: no cover - defensive
    Assistant = None  # type: ignore
    TimeoutException = Exception  # type: ignore

# Import utility functions and fixtures from tools module
from scripts.tools import (
    task_context,
    manage_consumer_directory,
    measure_task_time, 
    handle_task_errors,
    get_org_name,
    repos
)

HEADLESS_FLAGS = {"1", "true", "yes", "on"}


def is_headless_environment() -> bool:
    """Detect whether the assistant should skip launching a UI."""

    forced = os.environ.get("ASSISTANT_HEADLESS") or os.environ.get("RC_ASSISTANT_HEADLESS")
    if forced and forced.strip().lower() in HEADLESS_FLAGS:
        return True

    # CI environments often set CI=1
    if os.environ.get("CI", "").strip().lower() in HEADLESS_FLAGS:
        return True

    # If no display is available on Unix-like systems, assume headless
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        return True

    return False


@task
def producer():
    """Fetches repositories from GitHub org and creates work items."""
    # Process input work items to get organization name
    for item in workitems.inputs:
        try:
            payload = item.payload
            if not isinstance(payload, dict):
                item.fail("APPLICATION", code="INVALID_PAYLOAD", message="Payload must be a dictionary")
                continue
            
            org_name = payload.get("org")
            if not org_name:
                org_name = get_org_name()
            
            if not org_name:
                item.fail("APPLICATION", code="MISSING_ORG_NAME", 
                         message="Organization name is required in work item payload 'org' field or ORG_NAME environment variable.")
                continue
            
            print(f"Processing organization: {org_name}")

            # Get the DataFrame from repos() function with retry logic
            try:
                df = repos(org_name)
            except Exception as e:
                error_msg = f"Failed to fetch repositories for {org_name}: {str(e)}"
                print(error_msg)
                item.fail("BUSINESS", code="FETCH_ERROR", message=error_msg)
                continue

            if df is not None and not df.empty:
                print(f"Processing {len(df)} repositories from DataFrame")
                rows = df.to_dict(orient="records")
                created_count = 0
                
                for row in rows:
                    try:
                        repo_payload = {
                            "org": org_name,
                            "Name": row.get("Name"),
                            "URL": row.get("URL"),
                            "Description": row.get("Description"),
                            "Created": row.get("Created"),
                            "Last Updated": row.get("Last Updated"),
                            "Language": row.get("Language"),
                            "Stars": row.get("Stars"),
                            "Is Fork": row.get("Is Fork")
                        }
                        
                        # Validate required fields
                        if not repo_payload.get("URL") or not repo_payload.get("Name"):
                            print(f"Skipping repository with missing URL or Name: {repo_payload}")
                            continue
                            
                        # Create work item
                        workitems.outputs.create(repo_payload)
                        created_count += 1
                        
                    except Exception as e:
                        print(f"Error creating work item for repository {row.get('Name', 'unknown')}: {str(e)}")
                        # Continue processing other repositories
                        continue
                
                print(f"Created {created_count} work items out of {len(rows)} repositories")
                
                # Mark the input item as done only after all work items are created
                item.done()
            else:
                print("No data received from repos() function")
                item.fail("BUSINESS", code="NO_DATA", message="No repositories found for organization")
                
        except Exception as e:
            error_msg = f"Unexpected error in producer task: {str(e)}"
            print(error_msg)
            item.fail("APPLICATION", code="UNEXPECTED_ERROR", message=error_msg)

@task
def consumer():
    """Clones all the repositories from the input Work Items and zips them and saves them to the output directory."""
    output = get_output_dir() or Path("output")
    
    # Get the managed directory from the fixture via context
    repos_dir = task_context.get("repos_dir")
    if not repos_dir:
        raise RuntimeError("Consumer directory not set up by fixture.")

    # Get shard ID for unique naming
    shard_id = os.getenv("SHARD_ID", "0")
    filename = f"repos-shard-{shard_id}.zip"
    output_path = output / filename
    
    processed_repos = []
    git_repos = []  # Track successfully cloned repo paths
    
    # Define report path before use
    report_path = output / f"report-shard-{shard_id}.json"
    
    # Extract org name from first work item or environment variable
    org_name = get_org_name()
    
    for item in workitems.inputs:
        try:
            payload = item.payload
            if not isinstance(payload, dict):
                print(f"Skipping item with non-dict payload: {payload}")
                item.fail("APPLICATION", code="INVALID_PAYLOAD", message="Payload is not a dict.")
                continue
            
            # Extract org name if not already set
            if org_name is None:
                org_name = payload.get("org")
            
            url = payload.get("URL")
            repo_name = payload.get("Name")
            
            if not url:
                print(f"Skipping item with missing URL: {payload}")
                item.fail("APPLICATION", code="MISSING_URL", message="URL is missing in payload.")
                continue
                
            if not repo_name:
                # Fallback: extract repo name from URL
                repo_name = url.split('/')[-1].replace('.git', '')
            
            repo_path = repos_dir / repo_name
            print(f"[Shard {shard_id}] {org_name}/{repo_name} - cloning...")
            
            # Check if repo already exists (idempotency check)
            if repo_path.exists():
                print(f"[Shard {shard_id}] {org_name}/{repo_name} - already exists, skipping")
                processed_repos.append({
                    "name": repo_name,
                    "url": url,
                    "status": "already_exists"
                })
                workitems.outputs.create({
                    "name": repo_name,
                    "url": url,
                    "org": org_name,
                    "status": "already_exists"
                })
                item.done()
                continue
            
            try:
                # Clone with GitPython, with timeout and better error handling
                repo = Repo.clone_from(url, repo_path, depth=1)  # Shallow clone for efficiency
                print(f"[Shard {shard_id}] {org_name}/{repo_name} - ✓")
                processed_repos.append({
                    "name": repo_name,
                    "url": url,
                    "status": "success",
                    "commit_hash": repo.head.commit.hexsha[:8] if repo.head.commit else "unknown"
                })
                git_repos.append(repo_path)  # Add to cleanup list
                
                # Create output work item for success
                workitems.outputs.create({
                    "name": repo_name,
                    "url": url,
                    "org": org_name,
                    "status": "success",
                    "commit_hash": repo.head.commit.hexsha[:8] if repo.head.commit else "unknown"
                })
                item.done()
                
            except GitCommandError as git_err:
                error_msg = f"Git error while cloning {repo_name} from org {org_name}: {str(git_err)}"
                print(f"[Shard {shard_id}] {org_name}/{repo_name} - ✗ {str(git_err)}")
                
                # Clean up partial clone on failure
                if repo_path.exists():
                    try:
                        shutil.rmtree(repo_path)
                    except OSError:
                        pass
                
                if "could not resolve host" in str(git_err).lower() or "network" in str(git_err).lower():
                    print(f"[Shard {shard_id}] {org_name}/{repo_name} - network error, releasing for retry")
                    processed_repos.append({
                        "name": repo_name,
                        "url": url,
                        "status": "released",
                        "error": error_msg
                    })
                    # Create output work item for released
                    workitems.outputs.create({
                        "name": repo_name,
                        "url": url,
                        "org": org_name,
                        "status": "released",
                        "error": error_msg
                    })
                    # Do not mark as done or failed, so it can be retried if supported
                else:
                    processed_repos.append({
                        "name": repo_name,
                        "url": url,
                        "status": "failed",
                        "error": error_msg
                    })
                    # Create output work item for failure
                    workitems.outputs.create({
                        "name": repo_name,
                        "url": url,
                        "org": org_name,
                        "status": "failed",
                        "error": error_msg
                    })
                    item.fail("BUSINESS", code="GIT_ERROR", message=error_msg)
                continue
                
        except Exception as e:
            error_msg = f"Unexpected error processing work item: {str(e)}"
            print(error_msg)
            item.fail("APPLICATION", code="UNEXPECTED_ERROR", message=error_msg)
            continue

    # Create a summary report (idempotent - overwrites existing)
    report = {
        "shard_id": shard_id,
        "org_name": org_name,
        "total_processed": len(processed_repos),
        "successful_clones": len([r for r in processed_repos if r["status"] == "success"]),
        "failed_clones": len([r for r in processed_repos if r["status"] == "failed"]),
        "released_items": len([r for r in processed_repos if r["status"] == "released"]),
        "already_existing": len([r for r in processed_repos if r["status"] == "already_exists"]),
        "repositories": processed_repos,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }
    
    try:
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=4)
        print(f"[Shard {shard_id}] Consumer task finished. Report at: {report_path}")
    except Exception as e:
        print(f"Warning: Could not write report to {report_path}: {e}")

    # Only create zip if we have successfully cloned repos
    if git_repos:
        try:
            # Remove existing zip file for idempotency
            if output_path.exists():
                output_path.unlink()
                
            # Zip the cloned repositories directory
            print(f"[Shard {shard_id}] Zipping {len(git_repos)} cloned repositories...")
            shutil.make_archive(str(output_path.with_suffix('')), 'zip', root_dir=repos_dir)
            print(f"[Shard {shard_id}] Zipped repositories to: {output_path}")
        except Exception as e:
            print(f"Error creating zip archive: {e}")
    else:
        print(f"[Shard {shard_id}] No repositories to zip")

    # Cleanup is now handled by the manage_consumer_directory fixture.


@task
def reporter():
    """Generate comprehensive reports on work item processing status."""
    summary_stats = {
        "total_items_processed": 0,
        "successful_items": 0,
        "failed_items": 0,
        "released_items": 0,
        "organizations": set(),
        "repositories": []
    }
    
    for item in workitems.inputs:
        try:
            payload = item.payload
            if not isinstance(payload, dict):
                print(f"Skipping item with non-dict payload: {payload}")
                item.fail("APPLICATION", code="INVALID_PAYLOAD", message="Payload is not a dict.")
                continue
            
            org_name = payload.get("org")
            if not org_name:
                org_name = get_org_name()
            
            if not org_name:
                print("Organization name is required in work item payload 'org' field or ORG_NAME environment variable.")
                item.fail("APPLICATION", code="MISSING_ORG_NAME", message="Organization name is missing.")
                continue
            
            print(f"Processing report for organization: {org_name}")
            
            # Collect statistics from work item
            status = payload.get("status", "unknown")
            repo_name = payload.get("name") or payload.get("Name", "unknown")
            
            summary_stats["total_items_processed"] += 1
            summary_stats["organizations"].add(org_name)
            
            # Count by status
            if status == "success":
                summary_stats["successful_items"] += 1
            elif status == "failed":
                summary_stats["failed_items"] += 1
            elif status == "released":
                summary_stats["released_items"] += 1
            
            # Add repository details
            summary_stats["repositories"].append({
                "name": repo_name,
                "org": org_name,
                "status": status,
                "url": payload.get("url") or payload.get("URL"),
                "error": payload.get("error")
            })
            
            item.done()
            
        except Exception as e:
            error_msg = f"Error processing report item: {str(e)}"
            print(error_msg)
            item.fail("APPLICATION", code="UNEXPECTED_ERROR", message=error_msg)
    
    # Generate final summary
    summary_stats["organizations"] = list(summary_stats["organizations"])
    success_rate = (summary_stats["successful_items"] / summary_stats["total_items_processed"] * 100) if summary_stats["total_items_processed"] > 0 else 0
    
    print("\n" + "="*50)
    print("FINAL PROCESSING REPORT")
    print("="*50)
    print(f"Organizations processed: {len(summary_stats['organizations'])}")
    print(f"Total repositories: {summary_stats['total_items_processed']}")
    print(f"✅ Successful: {summary_stats['successful_items']}")
    print(f"❌ Failed: {summary_stats['failed_items']}")
    print(f"🔄 Released (for retry): {summary_stats['released_items']}")
    print(f"📊 Success rate: {success_rate:.1f}%")
    print("="*50)
    
    # Save detailed report
    output_dir = get_output_dir() or Path("output")
    report_file = output_dir / f"final_report_{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.json"
    
    try:
        with open(report_file, 'w') as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "summary": summary_stats,
                "success_rate_percent": success_rate
            }, f, indent=4)
        print(f"📄 Detailed report saved to: {report_file}")
    except Exception as e:
        print(f"Warning: Could not save detailed report: {e}")

 
@task
def assistant_org():
    """Interactive pipeline launcher using RPA.Assistant.

    Presents a single dialog that collects configuration, runs the pipeline,
    and streams progress updates without closing the window.
    """
    if Assistant is None:
        print("Assistant library not available (rpaframework-assistant missing). Aborting.")
        return

    assistant = Assistant()
    stage_order = ["Producer", "Consumer", "Reporter", "Dashboard"]
    stage_dependencies = {
        "Producer": [],
        "Consumer": ["Producer"],
        "Reporter": ["Consumer"],
        "Dashboard": ["Reporter"],
    }
    last_form_data = {"org": "", "max_workers": "1"}

    def render_progress(
        completed: int,
        stage_status: Dict[str, object],
        stage_messages: Dict[str, str],
        org_name: str,
        max_workers_display: str,
        running_stage: Optional[str] = None,
        final: bool = False,
    ) -> None:
        assistant.clear_dialog()
        assistant.add_heading("Fetch Repos Bot Pipeline", size="large")
        assistant.add_text(f"Organization: {org_name}")
        assistant.add_text(f"Max Workers: {max_workers_display}")

        progress_value = 0.0
        if stage_order:
            progress_value = min(max(completed / len(stage_order), 0.0), 1.0)

        assistant.add_loading_bar(
            "progress",
            value=progress_value,
            width=420,
            bar_height=18,
            tooltip=f"{int(progress_value * 100)}% complete",
        )

        if running_stage:
            assistant.add_text(f"⏳ Running {running_stage}…", size="medium")

        assistant.add_text("")
        for stage in stage_order:
            status = stage_status.get(stage)
            message = stage_messages.get(stage, "")

            if status is None:
                assistant.add_text(f"⏳ {stage}: Pending")
            elif status == "skipped":
                assistant.add_text(f"⏭️ {stage}: {message or 'Skipped'}")
            elif status is True:
                assistant.add_text(f"✅ {stage}: {message or 'Success'}")
            else:
                assistant.add_text(f"❌ {stage}: {message or 'Failed'}")

        if final:
            assistant.add_text("")
            assistant.add_button("Run Again", lambda: reset_form())
            assistant.add_submit_buttons(buttons="Close", default="Close")

        assistant.refresh_dialog()

    def run_rcc_task(command: List[str]) -> Tuple[bool, str]:
        try:
            result = subprocess.run(command, capture_output=False, text=True)
            success = result.returncode == 0
            return success, ("Success" if success else f"Exit code {result.returncode}")
        except FileNotFoundError:
            return False, "rcc command not found. Install RCC CLI and ensure it is on PATH."
        except Exception as exc:  # pragma: no cover - defensive
            return False, str(exc)

    def run_pipeline(form_result) -> None:
        nonlocal last_form_data

        org_name = getattr(form_result, "org", "").strip()
        max_workers_raw = getattr(form_result, "max_workers", "").strip() or "1"
        last_form_data = {"org": org_name, "max_workers": max_workers_raw}

        if not org_name:
            reset_form("Organization name is required.")
            return

        try:
            max_workers_int = max(1, int(max_workers_raw))
        except ValueError:
            reset_form("Max Workers must be a positive integer.")
            return

        max_workers_display = str(max_workers_int)
        print(f"Starting pipeline for organization: {org_name} (max workers: {max_workers_display})")

        # Prepare environment and input artifacts
        os.environ["ORG_NAME"] = org_name
        os.environ["SHARD_ID"] = "0"
        os.environ["MAX_WORKERS"] = max_workers_display

        work_items_dir = Path("devdata/work-items-in/input-for-producer")
        work_items_dir.mkdir(parents=True, exist_ok=True)
        work_items_path = work_items_dir / "work-items.json"
        with open(work_items_path, "w") as handle:
            json.dump([{"payload": {"org": org_name}}], handle, indent=4)

        producer_env = {
            "RC_WORKITEM_ADAPTER": "FileAdapter",
            "RC_WORKITEM_INPUT_PATH": str(work_items_path),
            "RC_WORKITEM_OUTPUT_PATH": "output/producer-to-consumer/work-items.json",
        }
        consumer_env = {
            "RC_WORKITEM_ADAPTER": "FileAdapter",
            "RC_WORKITEM_INPUT_PATH": "output/producer-to-consumer/work-items.json",
            "RC_WORKITEM_OUTPUT_PATH": "output/consumer-to-reporter/work-items.json",
        }
        reporter_env = {
            "RC_WORKITEM_ADAPTER": "FileAdapter",
            "RC_WORKITEM_INPUT_PATH": "output/consumer-to-reporter/work-items.json",
            "RC_WORKITEM_OUTPUT_PATH": "output/reporter-final/work-items.json",
        }

        stage_status: Dict[str, object] = {stage: None for stage in stage_order}
        stage_messages: Dict[str, str] = {}

        Path("devdata").mkdir(exist_ok=True)
        Path("output/reporter-final").mkdir(parents=True, exist_ok=True)

        def write_env(path: Path, data: dict) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as env_handle:
                json.dump(data, env_handle, indent=4)

        render_progress(0, stage_status, stage_messages, org_name, max_workers_display)

        for index, stage in enumerate(stage_order):
            dependencies = stage_dependencies.get(stage, [])
            if any(stage_status.get(dep) is not True for dep in dependencies):
                missing = ", ".join(dep for dep in dependencies if stage_status.get(dep) is not True)
                stage_status[stage] = "skipped"
                stage_messages[stage] = f"Skipped because {missing} did not succeed."
                render_progress(index + 1, stage_status, stage_messages, org_name, max_workers_display)
                continue

            render_progress(index, stage_status, stage_messages, org_name, max_workers_display, running_stage=stage)
            print(f"Running {stage} ({index + 1}/{len(stage_order)})…")

            if stage == "Producer":
                env_path = Path("devdata/env-for-producer.json")
                write_env(env_path, producer_env)
                success, message = run_rcc_task(["rcc", "run", "-t", "Producer", "-e", str(env_path)])
            elif stage == "Consumer":
                env_path = Path("devdata/env-for-consumer.json")
                write_env(env_path, consumer_env)
                success, message = run_rcc_task(["rcc", "run", "-t", "Consumer", "-e", str(env_path)])
            elif stage == "Reporter":
                env_path = Path("devdata/env-for-reporter.json")
                write_env(env_path, reporter_env)
                success, message = run_rcc_task(["rcc", "run", "-t", "Reporter", "-e", str(env_path)])
            else:  # Dashboard
                success, message = run_rcc_task(["rcc", "run", "-t", "GenerateConsolidatedDashboard"])

            stage_status[stage] = success
            stage_messages[stage] = message

            render_progress(index + 1, stage_status, stage_messages, org_name, max_workers_display)

        render_progress(
            len(stage_order),
            stage_status,
            stage_messages,
            org_name,
            max_workers_display,
            final=True,
        )

        if stage_status.get("Dashboard") is True:
            print("Dashboard generated at output/consolidated_dashboard_jinja2.html")
        if stage_status.get("Reporter") is True:
            print("Reporter outputs stored under output/ directory.")

        print("Pipeline execution finished. You can close the assistant or run again.")

    def reset_form(error_message: Optional[str] = None, *, refresh: bool = True) -> None:
        assistant.clear_dialog()
        assistant.add_heading("Fetch Repos Bot Pipeline", size="large")
        assistant.add_text("Configure and run the complete repository fetching pipeline.")

        if error_message:
            assistant.add_text(f"⚠️ {error_message}", size="small")

        assistant.add_text_input(
            "org",
            label="GitHub Organization",
            placeholder="e.g. robocorp, microsoft, etc.",
            required=True,
            default=last_form_data.get("org", ""),
        )
        assistant.add_text_input(
            "max_workers",
            label="Max Workers (for sharding)",
            placeholder="4",
            default=last_form_data.get("max_workers", "1"),
        )

        assistant.add_next_ui_button("Run Pipeline", run_pipeline)
        assistant.add_submit_buttons(buttons="Close", default="Close")

        if refresh:
            assistant.refresh_dialog()

    reset_form(refresh=False)
    assistant.run_dialog(title="Fetch Repos Bot Assistant", width=640, height=520)

