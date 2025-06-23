from pathlib import Path
from robocorp import workitems
from robocorp.tasks import get_output_dir, task
import shutil
import os
from git import Repo
from git.exc import GitCommandError
from scripts.fetch_repos import fetch_github_repos
import json


def repos(org_name):
    """Fetch the list of repositories from GitHub and return a DataFrame."""
    if not org_name:
        raise ValueError("Organization name is required.")
    print(f"Fetching repositories for organization: {org_name}")
    return fetch_github_repos(org_name)

@task
def producer():
    """Fetches repositories from GitHub org and creates work items."""
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
                # Create normal work items
                workitems.outputs.create(repo_payload)
            print(f"Created {len(rows)} work items")
        else:
            print("No data received from repos() function")
        
        # Mark the input item as done
        item.done()

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
    git_repos = []  # Track successfully cloned repo paths
    
    # Define report path before use
    report_path = output / f"report-shard-{shard_id}.json"
    
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
                git_repos.append(repo_path)  # Add to cleanup list
                item.done()
            except GitCommandError as git_err:
                error_msg = f"Git error while cloning {repo_name}: {str(git_err)}"
                print(f"[Shard {shard_id}] {error_msg}")
                # We'll check for a common transient Git error.
                if "could not resolve host" in str(git_err).lower():
                    print(f"[Shard {shard_id}] Transient network error for {repo_name}. Skipping for retry.")
                    processed_repos.append({
                        "name": repo_name,
                        "url": url,
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
                    item.fail("BUSINESS", code="GIT_ERROR", message=error_msg)
                continue
                
        except AssertionError as err:
            item.fail("BUSINESS", code="INVALID_ORDER", message=str(err))
            continue

    # Create a summary report
    report = {
        "shard_id": shard_id,
        "total_processed": len(processed_repos),
        "successful_clones": len(git_repos),
        "failed_clones": len([r for r in processed_repos if r["status"] == "failed"]),
        "released_items": len([r for r in processed_repos if r["status"] == "released"]),
        "repositories": processed_repos
    }
    
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=4)

    print(f"[Shard {shard_id}] Consumer task finished. Report at: {report_path}")

    # Zip the cloned repositories directory before cleanup
    print(f"[Shard {shard_id}] Zipping cloned repositories...")
    shutil.make_archive(str(output_path.with_suffix('')), 'zip', root_dir=repos_dir)
    print(f"[Shard {shard_id}] Zipped repositories to: {output_path}")

    # Clean up the cloned repos directory (but not the zip file)
    print(f"[Shard {shard_id}] Cleaning up cloned repositories directory...")
    try:
        shutil.rmtree(repos_dir)
    except OSError as e:
        print(f"Error removing directory {repos_dir}: {e}")
    print(f"[Shard {shard_id}] Cleanup complete")
