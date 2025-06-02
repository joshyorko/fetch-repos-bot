from pathlib import Path
from robocorp import workitems
from robocorp.tasks import get_output_dir, task
import shutil
import os
import git
from git import Repo
from git.exc import GitCommandError
from fetch_repos import fetch_github_repos
import json
import math
from typing import List, Dict, Any

def _shard_work_items(work_items: List[Dict[str, Any]], max_workers: int = 4) -> List[List[Dict[str, Any]]]:
    """Shard work items into batches for parallel processing."""
    if not work_items:
        return []
    
    # Filter out empty work items
    valid_work_items = [item for item in work_items if item.get('payload')]
    
    if not valid_work_items:
        return []
    
    total_items = len(valid_work_items)
    actual_workers = min(max_workers, total_items)
    items_per_shard = math.ceil(total_items / actual_workers)
    
    print(f"Sharding {total_items} work items into {actual_workers} batches")
    print(f"Approximately {items_per_shard} items per batch")
    
    # Create shards
    shards = []
    for i in range(0, total_items, items_per_shard):
        shard = valid_work_items[i:i + items_per_shard]
        shards.append(shard)
    
    return shards

def _save_sharded_work_items(shards: List[List[Dict[str, Any]]], output_dir: str) -> Dict[str, Any]:
    """Save sharded work items and generate matrix configuration."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Clear existing shard files
    for existing_file in output_path.glob("work-items-shard-*.json"):
        existing_file.unlink()
    
    shard_info = []
    
    for i, shard in enumerate(shards):
        shard_file = output_path / f"work-items-shard-{i}.json"
        with open(shard_file, 'w') as f:
            json.dump(shard, f)
        print(f"Created shard {i}: {shard_file} with {len(shard)} items")
        shard_info.append({"shard_id": i})
    
    # Save matrix configuration
    matrix_config = {"include": shard_info}
    matrix_file = output_path / "matrix-config.json"
    with open(matrix_file, 'w') as f:
        json.dump(matrix_config, f)
    
    return matrix_config

def repos(org_name):
    """Fetches the list of repositories from GitHub and saves it to a CSV file."""
    if not org_name:
        raise ValueError("Organization name is required.")
    print(f"Fetching repositories for organization: {org_name}")
    return fetch_github_repos(org_name)

@task
def producer():
    """Fetches repositories from GitHub org, creates work items, saves to artifacts, and generates matrix config."""
    output = get_output_dir() or Path("output")
    
    work_items_data = []
    
    # Process input work items to get organization name
    for item in workitems.inputs:
        payload = item.payload
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a dictionary")
        
        org_name = payload.get("org")
        if not org_name:
            org_name = os.getenv("ORG_NAME")
        
        if not org_name:
            raise ValueError("Organization name is required in work item payload 'org' field or ORG_NAME environment variable.")
        
        print(f"Processing organization: {org_name}")

        # Get the DataFrame from repos() function
        df = repos(org_name)

        if df is not None and not df.empty:
            print(f"Processing {len(df)} repositories from DataFrame")
            rows = df.to_dict(orient="records")
            for row in rows:
                repo_payload = {
                    "Name": row.get("Name"),
                    "URL": row.get("URL"),
                    "Description": row.get("Description"),
                    "Created": row.get("Created"),
                    "Last Updated": row.get("Last Updated"),
                    "Language": row.get("Language"),
                    "Stars": row.get("Stars"),
                    "Is Fork": row.get("Is Fork")
                }
                work_items_data.append({"payload": repo_payload})
            print(f"Collected {len(rows)} work items")
        else:
            print("No data received from repos() function")
        
        # Mark the input item as done
        item.done()
        break
    
    # Save work items to artifacts for matrix processing
    if work_items_data:
        work_items_file = output / "work-items.json"
        with open(work_items_file, 'w') as f:
            json.dump(work_items_data, f)
        print(f"Saved {len(work_items_data)} work items to {work_items_file}")
        
        # Generate shards and matrix config
        max_workers = int(os.getenv("MAX_WORKERS", "4"))
        shards = _shard_work_items(work_items_data, max_workers)
        
        # Save shards
        shards_dir = output / "shards"
        matrix_config = _save_sharded_work_items(shards, str(shards_dir))
        
        # Save matrix output for GitHub Actions
        matrix_output_file = output / "matrix-output.json"
        matrix_output = {"matrix": matrix_config}
        with open(matrix_output_file, 'w') as f:
            json.dump(matrix_output, f)
        
        print(f"Generated matrix config with {len(shards)} shards")
        print(f"Matrix output saved to: {matrix_output_file}")
    else:
        # Create empty matrix if no work items
        matrix_output_file = output / "matrix-output.json"
        with open(matrix_output_file, 'w') as f:
            json.dump({"matrix": {"include": []}}, f)
        print("No work items found - created empty matrix")

@task
def consumer():
    """Clones all the repositories from the input Work Items and zips them and saves them to the output directory."""
    output = get_output_dir() or Path("output")
    
    # Get shard ID for unique naming
    shard_id = os.getenv("SHARD_ID", "0")
    filename = f"repos-shard-{shard_id}.zip"
    repos_dir = output / f"repos-shard-{shard_id}"
    output_path = output / filename

    # Create output directories if they don't exist
    repos_dir.mkdir(parents=True, exist_ok=True)
    
    processed_repos = []
    
    for item in workitems.inputs:
        try:
            payload = item.payload
            if not isinstance(payload, dict):
                print(f"Skipping item with non-dict payload: {payload}")
                item.fail("APPLICATION", code="INVALID_PAYLOAD", message="Payload is not a dict.")
                continue
            url = payload.get("URL")
            if not url:
                print(f"Skipping item with missing URL: {payload}")
                item.fail("APPLICATION", code="MISSING_URL", message="URL is missing in payload.")
                continue
            repo_name = url.split('/')[-1].replace('.git', '')
            repo_path = repos_dir / repo_name
            print(f"[Shard {shard_id}] Cloning repository: {repo_name}")
            
            try:
                # Clone with GitPython, showing progress (if supported)
                Repo.clone_from(url, repo_path)
                print(f"[Shard {shard_id}] Successfully cloned: {repo_name}")
                processed_repos.append({
                    "name": repo_name,
                    "url": url,
                    "status": "success"
                })
                item.done()
            except GitCommandError as git_err:
                error_msg = f"Git error while cloning {repo_name}: {str(git_err)}"
                print(f"[Shard {shard_id}] {error_msg}")
                processed_repos.append({
                    "name": repo_name,
                    "url": url,
                    "status": "failed",
                    "error": error_msg
                })
                item.fail("BUSINESS", code="GIT_ERROR", message=error_msg)
                continue
                
        except AssertionError as err:
            item.fail("BUSINESS", code="INVALID_ORDER", message=str(err))
        except KeyError as err:
            item.fail("APPLICATION", code="MISSING_FIELD", message=str(err))
    
    # Get all directories that are git repositories in the repos directory
    git_repos = [d for d in os.listdir(repos_dir) if os.path.isdir(os.path.join(repos_dir, d)) 
                 and os.path.exists(os.path.join(repos_dir, d, '.git'))]
    
    # Save processing report
    report_path = output / f"shard-{shard_id}-report.json"
    report = {
        "shard_id": shard_id,
        "total_processed": len(processed_repos),
        "successful_clones": len(git_repos),
        "failed_clones": len([r for r in processed_repos if r["status"] == "failed"]),
        "repositories": processed_repos
    }
    
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[Shard {shard_id}] Processing report saved to: {report_path}")
    
    if git_repos:
        print(f"[Shard {shard_id}] Creating zip archive of {len(git_repos)} repositories...")
        try:
            # Create the zip file containing all repositories
            shutil.make_archive(str(output_path.with_suffix('')), 'zip', 
                              root_dir=str(repos_dir), base_dir=None)
            print(f"[Shard {shard_id}] Successfully created archive at: {output_path}")
            
            # Clean up: remove the cloned repositories after zipping
            print(f"[Shard {shard_id}] Cleaning up cloned repositories...")
            shutil.rmtree(repos_dir)
            print(f"[Shard {shard_id}] Cleanup complete")
        except Exception as e:
            print(f"[Shard {shard_id}] Error during archive creation or cleanup: {str(e)}")
            raise
    else:
        print(f"[Shard {shard_id}] No repositories to archive")

@task 
def sharded_consumer():
    """Clones repositories from a specific shard of work items for parallel processing."""
    output = get_output_dir() or Path("output")
    
    # Get shard ID from environment variable (set by GitHub Actions matrix)
    shard_id = os.getenv("SHARD_ID", "0")
    
    filename = f"repos-shard-{shard_id}.zip"
    repos_dir = output / f"repos-shard-{shard_id}"
    output_path = output / filename

    # Create output directories if they don't exist
    repos_dir.mkdir(parents=True, exist_ok=True)
    
    processed_repos = []
    
    for item in workitems.inputs:
        try:
            payload = item.payload
            if not isinstance(payload, dict):
                print(f"Skipping item with non-dict payload: {payload}")
                item.fail("APPLICATION", code="INVALID_PAYLOAD", message="Payload is not a dict.")
                continue
            url = payload.get("URL")
            if not url:
                print(f"Skipping item with missing URL: {payload}")
                item.fail("APPLICATION", code="MISSING_URL", message="URL is missing in payload.")
                continue
            repo_name = url.split('/')[-1].replace('.git', '')
            repo_path = repos_dir / repo_name
            print(f"[Shard {shard_id}] Cloning repository: {repo_name}")
            
            try:
                # Clone with GitPython, showing progress (if supported)
                Repo.clone_from(url, repo_path)
                print(f"[Shard {shard_id}] Successfully cloned: {repo_name}")
                processed_repos.append({
                    "name": repo_name,
                    "url": url,
                    "status": "success"
                })
                item.done()
            except GitCommandError as git_err:
                error_msg = f"Git error while cloning {repo_name}: {str(git_err)}"
                print(f"[Shard {shard_id}] {error_msg}")
                processed_repos.append({
                    "name": repo_name,
                    "url": url,
                    "status": "failed",
                    "error": error_msg
                })
                item.fail("BUSINESS", code="GIT_ERROR", message=error_msg)
                continue
                
        except AssertionError as err:
            item.fail("BUSINESS", code="INVALID_ORDER", message=str(err))
        except KeyError as err:
            item.fail("APPLICATION", code="MISSING_FIELD", message=str(err))
    
    # Get all directories that are git repositories in the repos directory
    git_repos = [d for d in os.listdir(repos_dir) if os.path.isdir(os.path.join(repos_dir, d)) 
                 and os.path.exists(os.path.join(repos_dir, d, '.git'))]
    
    # Save processing report
    report_path = output / f"shard-{shard_id}-report.json"
    report = {
        "shard_id": shard_id,
        "total_processed": len(processed_repos),
        "successful_clones": len(git_repos),
        "failed_clones": len([r for r in processed_repos if r["status"] == "failed"]),
        "repositories": processed_repos
    }
    
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[Shard {shard_id}] Processing report saved to: {report_path}")
    
    if git_repos:
        print(f"[Shard {shard_id}] Creating zip archive of {len(git_repos)} repositories...")
        try:
            # Create the zip file containing all repositories
            shutil.make_archive(str(output_path.with_suffix('')), 'zip', 
                              root_dir=str(repos_dir), base_dir=None)
            print(f"[Shard {shard_id}] Successfully created archive at: {output_path}")
            
            # Clean up: remove the cloned repositories after zipping
            print(f"[Shard {shard_id}] Cleaning up cloned repositories...")
            shutil.rmtree(repos_dir)
            print(f"[Shard {shard_id}] Cleanup complete")
        except Exception as e:
            print(f"[Shard {shard_id}] Error during archive creation or cleanup: {str(e)}")
            raise
    else:
        print(f"[Shard {shard_id}] No repositories to archive")

@task
def shard_work_items():
    """Reads work items from artifacts and creates sharded work items for parallel processing."""
    output = get_output_dir() or Path("output")
    
    # Load work items from artifacts (uploaded by producer)
    work_items_file = output / "work-items.json"
    if not work_items_file.exists():
        raise FileNotFoundError(f"Work items file not found: {work_items_file}")
    
    with open(work_items_file, 'r') as f:
        work_items = json.load(f)
    
    print(f"Loaded {len(work_items)} work items from artifacts")
    
    # Get max_workers from environment variable or use default
    max_workers = int(os.getenv("MAX_WORKERS", "4"))
    
    # Shard the work items
    shards = _shard_work_items(work_items, max_workers)
    
    # Save shards to output directory
    shards_dir = output / "shards"
    matrix_config = _save_sharded_work_items(shards, str(shards_dir))
    
    # Save matrix configuration for GitHub Actions
    matrix_output = output / "matrix-config.json"
    with open(matrix_output, "w") as f:
        json.dump(matrix_config, f)
    
    print(f"Created {len(shards)} shards")
    print(f"Matrix configuration saved to: {matrix_output}")

@task
def load_shard_consumer():
    """Loads a specific shard and processes it through the consumer."""
    output = get_output_dir() or Path("output")
    shard_id = os.getenv("SHARD_ID", "0")
    
    # Load shard file
    shard_file = output / "shards" / f"work-items-shard-{shard_id}.json"
    if not shard_file.exists():
        raise FileNotFoundError(f"Shard file not found: {shard_file}")
    
    with open(shard_file, 'r') as f:
        shard_items = json.load(f)
    
    print(f"[Shard {shard_id}] Loaded {len(shard_items)} items")
    
    # Create work items for this shard
    for item_data in shard_items:
        workitems.outputs.create(item_data["payload"])
    
    print(f"[Shard {shard_id}] Created {len(shard_items)} work items for processing")

