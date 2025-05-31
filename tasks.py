import os
import subprocess
import shutil
import os
import git
from git import Repo
from git.exc import GitCommandError
from fetch_repos import fetch_github_repos




def repos():
    """Fetches the list of repositories from GitHub and saves it to a CSV file."""
    for item in workitems.inputs:
        payload = item.payload
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a dictionary")
        org = payload.get("org")
        if not org:
            raise ValueError("Organization name is required in the payload.")
        print(f"Fetching repositories for organization: {org}")
        break
    return fetch_github_repos(org)

# ---------- PRODUCER ----------
@task
def producer():
    """Split Csv rows into multiple output Work Items for the next step."""
    output = get_output_dir() or Path("output")
    
    # Get the DataFrame from repos() function
    df = repos()
    
    outputs_created = False
    
    if df is not None and not df.empty:
        print(f"Processing {len(df)} repositories from DataFrame")
        rows = df.to_dict(orient="records")
        for row in rows:
            payload = {
                "Name": row.get("Name"),
                "URL": row.get("URL"),
                "Description": row.get("Description"),
                "Created": row.get("Created"),
                "Last Updated": row.get("Last Updated"),
                "Language": row.get("Language"),
                "Stars": row.get("Stars"),
                "Is Fork": row.get("Is Fork")
            }
            workitems.outputs.create(payload)
            outputs_created = True
        print(f"Created {len(rows)} work items from DataFrame")
    else:
        print("No data received from repos() function")
    
    if not outputs_created:
        print("No output work items were created. Check if repos() returned valid data.")


@task
def consumer():
    """Clone repo, zip it, attach as file."""
    workspace = pathlib.Path("/tmp/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    for wi in workitems.inputs:
        url = wi.payload["repo"]
        name = url.rsplit("/", 1)[-1].replace(".git", "")
        repo_dir = workspace / name
        subprocess.run(["git", "clone", "--depth", "1", url, str(repo_dir)],
                       check=True)
        zip_path = workspace / f"{name}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in repo_dir.rglob("*"):
                zf.write(p, p.relative_to(repo_dir))
        wi.files.add_local_file("archive", zip_path)
        wi.done()
        shutil.rmtree(repo_dir)
