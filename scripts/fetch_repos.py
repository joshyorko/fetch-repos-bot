import requests
from pathlib import Path
from pandas import DataFrame

# Timeout for HTTP requests (in seconds)
REQUEST_TIMEOUT = 10

def fetch_github_repos(entity: str, entity_type: str = None, write_csv: bool = False) -> DataFrame:
    """
    Fetch public repositories from a GitHub organization or user.
    
    Args:
        entity (str): The name of the organization or user
        entity_type (str, optional): Type of entity ('org' or 'user'). If None, will auto-detect.
        write_csv (bool): Whether to write the results to a CSV file. If False, returns DataFrame.
    
    Returns:
        pandas.DataFrame: DataFrame containing repository information
    """
    # Auto-detect entity type if not specified
    if entity_type is None:
        # Try to determine if it's an org or user
        test_url = f"https://api.github.com/orgs/{entity}"
        try:
            test_response = requests.get(test_url, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            print("Request timed out while determining entity type.")
            return DataFrame()
        entity_type = "org" if test_response.status_code == 200 else "user"
    
    # Set the appropriate API endpoint
    base_url = "https://api.github.com"
    url = f"{base_url}/{'orgs' if entity_type == 'org' else 'users'}/{entity}/repos"
    
    per_page = 100
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    repo_list = []
    page = 1

    while True:
        params = {
            "per_page": per_page,
            "page": page,
            "sort": "updated",
            "direction": "desc"
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            print(f"Request timed out while fetching page {page}.")
            break
        
        # Handle rate limiting
        if response.status_code == 403 and "rate limit exceeded" in response.text.lower():
            print("Rate limit exceeded. Please try again later.")
            break
            
        if response.status_code != 200:
            print(f"Failed to fetch repositories on page {page}: {response.status_code}")
            break

        repos = response.json()
        if not repos:  # No more repos to fetch
            break

        for repo in repos:
            if not repo.get("private", True):  # Only include public repos
                repo_list.append({
                    "Name": repo.get("name"),
                    "Description": repo.get("description"),
                    "Language": repo.get("language"),
                    "Stars": repo.get("stargazers_count"),
                    "URL": repo.get("clone_url"),  # Use clone_url for git operations
                    "Created": repo.get("created_at"),
                    "Last Updated": repo.get("updated_at"),
                    "Is Fork": repo.get("fork", False)
                })

        print(f"Fetched page {page} with {len(repos)} repositories. Total fetched so far: {len(repo_list)}")
        
        # If we got fewer repos than per_page, we've reached the end
        if len(repos) < per_page:
            break
        page += 1

    print("\nRepository statistics:")
    print(f"Total public repositories found: {len(repo_list)}")
    
    # Sort by stars for the CSV
    repo_list.sort(key=lambda x: x["Stars"] or 0, reverse=True)
    
    # Create DataFrame
    df = DataFrame(repo_list)
    
    if write_csv:
        base_dir = get_repo_root()
        output_dir = base_dir / "devdata" / "work-items-in" / "input-for-producer"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Failed to create directory '{output_dir}': {e}")
            return DataFrame()  # Return an empty DataFrame to indicate failure
        csv_filename = output_dir / "repos.csv"
        df.to_csv(csv_filename, index=False)
        print(
            f"CSV file '{csv_filename}' created successfully with {len(repo_list)} repositories."
        )
    
    return df

