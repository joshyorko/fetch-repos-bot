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
    repos,
)

HEADLESS_FLAGS = {"1", "true", "yes", "on"}


def is_headless_environment() -> bool:
    """Detect whether the assistant should skip launching a UI."""

    forced = os.environ.get("ASSISTANT_HEADLESS") or os.environ.get(
        "RC_ASSISTANT_HEADLESS"
    )
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
def assistant_org():
    """Interactive pipeline launcher using RPA.Assistant.

    Presents a single dialog that collects configuration, runs the pipeline,
    and streams progress updates without closing the window.
    """
    if Assistant is None:
        print(
            "Assistant library not available (rpaframework-assistant missing). Aborting."
        )
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
        assistant.add_heading("Producer-Consumer-Pipeline", size="large")
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
            return (
                False,
                "rcc command not found. Install RCC CLI and ensure it is on PATH.",
            )
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
        print(
            f"Starting pipeline for organization: {org_name} (max workers: {max_workers_display})"
        )

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
                missing = ", ".join(
                    dep for dep in dependencies if stage_status.get(dep) is not True
                )
                stage_status[stage] = "skipped"
                stage_messages[stage] = f"Skipped because {missing} did not succeed."
                render_progress(
                    index + 1,
                    stage_status,
                    stage_messages,
                    org_name,
                    max_workers_display,
                )
                continue

            render_progress(
                index,
                stage_status,
                stage_messages,
                org_name,
                max_workers_display,
                running_stage=stage,
            )
            print(f"Running {stage} ({index + 1}/{len(stage_order)})…")

            if stage == "Producer":
                env_path = Path("devdata/env-for-producer.json")
                write_env(env_path, producer_env)
                success, message = run_rcc_task(
                    ["rcc", "run", "-t", "Producer", "-e", str(env_path)]
                )
            elif stage == "Consumer":
                env_path = Path("devdata/env-for-consumer.json")
                write_env(env_path, consumer_env)
                success, message = run_rcc_task(
                    ["rcc", "run", "-t", "Consumer", "-e", str(env_path)]
                )
            elif stage == "Reporter":
                env_path = Path("devdata/env-for-reporter.json")
                write_env(env_path, reporter_env)
                success, message = run_rcc_task(
                    ["rcc", "run", "-t", "Reporter", "-e", str(env_path)]
                )
            else:  # Dashboard
                success, message = run_rcc_task(
                    ["rcc", "run", "-t", "GenerateConsolidatedDashboard"]
                )

            stage_status[stage] = success
            stage_messages[stage] = message

            render_progress(
                index + 1, stage_status, stage_messages, org_name, max_workers_display
            )

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

    def reset_form(
        error_message: Optional[str] = None, *, refresh: bool = True
    ) -> None:
        assistant.clear_dialog()
        assistant.add_heading("Fetch Repos Bot Pipeline", size="large")
        assistant.add_text(
            "Configure and run the complete repository fetching pipeline."
        )

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
