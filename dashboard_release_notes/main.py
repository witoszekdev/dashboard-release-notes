import re
import requests
import os
import argparse
import time
import sys
from dotenv import load_dotenv


def setup():
    """Initialize the environment variables and settings."""
    # Load environment variables from .env file if it exists
    load_dotenv()


def get_github_token():
    """
    Gets the GitHub token from environment variable or user input.

    Returns:
        str: The GitHub token.
    """
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        github_token = input("Please enter your GitHub token: ")
        if not github_token:
            print("Error: GitHub token is required to access the GitHub API.")
            sys.exit(1)
    return github_token


def get_pull_request_body(commit_hash, repository="saleor/saleor-dashboard"):
    """
    Retrieves the pull request body associated with a given commit hash
    from a GitHub repository.

    Args:
        commit_hash (str): The Git commit hash to search for.
        repository (str): The GitHub repository in format "owner/repo".

    Returns:
        str: The body of the pull request, or None if not found.
    """
    token = get_github_token()

    # Use the commits/SHA/pulls endpoint to find PRs associated with this commit
    pr_url = f"https://api.github.com/repos/{repository}/commits/{commit_hash}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        response = requests.get(pr_url, headers=headers)

        # Handle rate limiting
        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            wait_time = max(0, reset_time - int(time.time()))
            if wait_time > 0:
                print(f"Rate limit exceeded. Waiting for {wait_time} seconds...")
                time.sleep(wait_time)
                # Retry the request
                return get_pull_request_body(commit_hash, repository)

        if response.status_code == 404:
            print(f"Commit {commit_hash} not found in repository {repository}")
            return None

        response.raise_for_status()  # Raise HTTPError for other bad responses (4xx or 5xx)
        pulls_data = response.json()

        if pulls_data and len(pulls_data) > 0:
            # Get the first PR associated with this commit
            pr_data = pulls_data[0]
            return pr_data["body"]
        else:
            # Try an alternate approach: get commit details and look for PR in the commit message
            commit_url = f"https://api.github.com/repos/{repository}/commits/{commit_hash}"
            commit_response = requests.get(commit_url, headers=headers)
            commit_response.raise_for_status()
            commit_data = commit_response.json()

            # Check if commit message contains PR reference like "Merge pull request #1234"
            commit_message = commit_data.get("commit", {}).get("message", "")
            pr_match = re.search(r"#(\d+)", commit_message)

            if pr_match:
                pr_number = pr_match.group(1)
                detailed_pr_url = f"https://api.github.com/repos/{repository}/pulls/{pr_number}"
                detailed_pr_response = requests.get(detailed_pr_url, headers=headers)

                if detailed_pr_response.status_code == 200:
                    detailed_pr_data = detailed_pr_response.json()
                    return detailed_pr_data["body"]

            return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from GitHub: {e}")
        return None


def generate_release_notes(changeset_text, repository="saleor/saleor-dashboard"):
    """
    Generates release notes by extracting commit hashes, finding associated
    pull request descriptions, and combining them with the original changeset text.

    Args:
        changeset_text (str): The input text containing changeset information.
        repository (str): The GitHub repository in format "owner/repo".

    Returns:
        str: The generated release notes including pull request descriptions.
    """
    release_notes = changeset_text + "\n\n"
    commit_hash_pattern = re.compile(r"([0-9a-f]{7,40}):")  # Matches commit hashes
    for line in changeset_text.splitlines():
        match = commit_hash_pattern.search(line)
        if match:
            commit_hash = match.group(1)
            print(f"Processing commit {commit_hash}...")
            pr_body = get_pull_request_body(commit_hash, repository)
            if pr_body:
                release_notes += f"Commit {commit_hash}:\n{pr_body}\n\n"
            else:
                release_notes += (
                    f"Commit {commit_hash}: Pull request description not found.\n\n"
                )
    return release_notes


def main():
    # Initialize environment
    setup()

    parser = argparse.ArgumentParser(description='Generate release notes based on changeset.')
    parser.add_argument('-i', '--input', type=str, help='Input file containing changeset text')
    parser.add_argument('-o', '--output', type=str, help='Output file for the release notes')
    parser.add_argument('-r', '--repo', type=str, default='saleor/saleor-dashboard',
                      help='GitHub repository in format "owner/repo"')
    args = parser.parse_args()

    # Get changeset text from input file or stdin
    if args.input:
        try:
            with open(args.input, 'r') as f:
                changeset_text = f.read()
        except IOError as e:
            print(f"Error reading input file: {e}")
            sys.exit(1)
    else:
        print("Please paste your changeset text (press Ctrl+D on Unix/Mac or Ctrl+Z then Enter on Windows when done):")
        changeset_text = sys.stdin.read()

    if not changeset_text.strip():
        print("Error: No changeset text provided.")
        sys.exit(1)

    # Generate release notes
    release_notes = generate_release_notes(changeset_text, args.repo)

    # Output release notes to file or stdout
    if args.output:
        try:
            with open(args.output, 'w') as f:
                f.write(release_notes)
            print(f"Release notes written to {args.output}")
        except IOError as e:
            print(f"Error writing to output file: {e}")
            sys.exit(1)
    else:
        print("\nGenerated Release Notes:\n")
        print(release_notes)


if __name__ == "__main__":
    main()