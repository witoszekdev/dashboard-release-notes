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


def get_pull_request_info(commit_hash, repository="saleor/saleor-dashboard"):
    """
    Retrieves information about pull requests associated with a given commit hash
    from a GitHub repository, including PR body, number, author and co-authors.

    This function tries multiple approaches to find the ORIGINAL PR where the change
    was introduced, not just release PRs that bundle multiple changes.

    Args:
        commit_hash (str): The Git commit hash to search for.
        repository (str): The GitHub repository in format "owner/repo".

    Returns:
        dict: A dictionary containing PR info, or None if not found.
    """
    token = get_github_token()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        # First, get commit information to extract author and co-authors
        commit_url = f"https://api.github.com/repos/{repository}/commits/{commit_hash}"
        commit_response = requests.get(commit_url, headers=headers)

        if commit_response.status_code == 404:
            print(f"Commit {commit_hash} not found in repository {repository}")
            return None

        commit_response.raise_for_status()
        commit_data = commit_response.json()

        # Extract commit author - prefer GitHub username if available
        commit_author_login = commit_data.get("author", {}).get("login")
        commit_author_name = (
            commit_data.get("commit", {}).get("author", {}).get("name", "Unknown")
        )
        commit_author = (
            f"@{commit_author_login}" if commit_author_login else commit_author_name
        )

        commit_message = commit_data.get("commit", {}).get("message", "")

        # Find Co-authored-by lines in commit message and extract GitHub usernames if possible
        co_authors = []
        co_author_pattern = re.compile(r"Co-authored-by:\s*([^<]*)<([^>]+)>")

        for line in commit_message.splitlines():
            co_author_match = co_author_pattern.search(line)
            if co_author_match:
                co_author_name = co_author_match.group(1).strip()
                co_author_email = co_author_match.group(2).strip()

                # Try to find GitHub username from email or use name with @ if it looks like a username
                if "@github.com" in co_author_email:
                    username = co_author_email.split("@")[0]
                    co_authors.append(f"@{username}")
                elif co_author_name and not any(c in co_author_name for c in " .,"):
                    # If name doesn't contain spaces or punctuation, it might be a username
                    co_authors.append(f"@{co_author_name}")
                else:
                    co_authors.append(co_author_name)

        # Strategy 1: Look for PR reference in commit message first (most reliable for original PRs)
        pr_match = re.search(r"#(\d+)", commit_message)
        if pr_match:
            pr_number = pr_match.group(1)
            print(f"Found PR reference #{pr_number} in commit message")

            detailed_pr_url = (
                f"https://api.github.com/repos/{repository}/pulls/{pr_number}"
            )
            detailed_pr_response = requests.get(detailed_pr_url, headers=headers)

            if detailed_pr_response.status_code == 200:
                detailed_pr_data = detailed_pr_response.json()
                pr_body = detailed_pr_data.get("body", "")

                # Get PR author's GitHub username with @ prefix
                pr_author_login = detailed_pr_data.get("user", {}).get("login")
                pr_author = f"@{pr_author_login}" if pr_author_login else "Unknown"

                return {
                    "pr_number": pr_number,
                    "pr_body": pr_body,
                    "pr_author": pr_author,
                    "commit_author": commit_author,
                    "co_authors": co_authors,
                }

        # Strategy 2: Use GitHub search API to find PRs that mention this commit
        print(f"Searching for PRs that mention commit {commit_hash}...")
        search_url = f"https://api.github.com/search/issues"
        search_params = {
            "q": f"repo:{repository} type:pr {commit_hash}",
            "sort": "created",
            "order": "asc",  # Get the earliest PR (likely the original)
        }

        search_response = requests.get(
            search_url, headers=headers, params=search_params
        )

        # Handle rate limiting
        if (
            search_response.status_code == 403
            and "rate limit" in search_response.text.lower()
        ):
            reset_time = int(search_response.headers.get("X-RateLimit-Reset", 0))
            wait_time = max(0, reset_time - int(time.time()))
            if wait_time > 0:
                print(f"Rate limit exceeded. Waiting for {wait_time} seconds...")
                time.sleep(wait_time)
                # Retry the request
                return get_pull_request_info(commit_hash, repository)

        if search_response.status_code == 200:
            search_data = search_response.json()

            if search_data.get("items"):
                # Filter out release PRs (they typically have "release" or "changeset" in title)
                original_prs = []
                for item in search_data["items"]:
                    title = item.get("title", "").lower()
                    # Skip PRs that look like release PRs
                    if not any(
                        keyword in title
                        for keyword in [
                            "release",
                            "changeset",
                            "version bump",
                            "bump version",
                        ]
                    ):
                        original_prs.append(item)

                if original_prs:
                    # Take the first non-release PR (earliest created)
                    pr_item = original_prs[0]
                    pr_number = str(pr_item["number"])

                    # Get full PR details
                    detailed_pr_url = (
                        f"https://api.github.com/repos/{repository}/pulls/{pr_number}"
                    )
                    detailed_pr_response = requests.get(
                        detailed_pr_url, headers=headers
                    )

                    if detailed_pr_response.status_code == 200:
                        detailed_pr_data = detailed_pr_response.json()
                        pr_body = detailed_pr_data.get("body", "")

                        # Get PR author's GitHub username with @ prefix
                        pr_author_login = detailed_pr_data.get("user", {}).get("login")
                        pr_author = (
                            f"@{pr_author_login}" if pr_author_login else "Unknown"
                        )

                        print(
                            f"Found original PR #{pr_number} via search: {detailed_pr_data.get('title', '')}"
                        )

                        return {
                            "pr_number": pr_number,
                            "pr_body": pr_body,
                            "pr_author": pr_author,
                            "commit_author": commit_author,
                            "co_authors": co_authors,
                        }

        # Strategy 3: Fallback to the original approach (commits/SHA/pulls endpoint)
        print(f"Falling back to commits/pulls endpoint for {commit_hash}...")
        pr_url = (
            f"https://api.github.com/repos/{repository}/commits/{commit_hash}/pulls"
        )
        response = requests.get(pr_url, headers=headers)

        # Handle rate limiting
        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait_time = max(0, reset_time - int(time.time()))
            if wait_time > 0:
                print(f"Rate limit exceeded. Waiting for {wait_time} seconds...")
                time.sleep(wait_time)
                # Retry the request
                return get_pull_request_info(commit_hash, repository)

        response.raise_for_status()
        pulls_data = response.json()

        if pulls_data and len(pulls_data) > 0:
            # Filter out release PRs here too
            original_prs = []
            for pr_data in pulls_data:
                title = pr_data.get("title", "").lower()
                # Skip PRs that look like release PRs
                if not any(
                    keyword in title
                    for keyword in [
                        "release",
                        "changeset",
                        "version bump",
                        "bump version",
                    ]
                ):
                    original_prs.append(pr_data)

            if original_prs:
                # Get the first non-release PR
                pr_data = original_prs[0]
            else:
                # If all PRs are release PRs, take the first one as fallback
                pr_data = pulls_data[0]

            pr_number = pr_data["number"]
            pr_body = pr_data["body"] or ""

            # Get PR author's GitHub username with @ prefix
            pr_author_login = pr_data.get("user", {}).get("login")
            pr_author = f"@{pr_author_login}" if pr_author_login else "Unknown"

            return {
                "pr_number": pr_number,
                "pr_body": pr_body,
                "pr_author": pr_author,
                "commit_author": commit_author,
                "co_authors": co_authors,
            }

        # If no PR found, return just commit information
        return {
            "pr_number": None,
            "pr_body": None,
            "pr_author": None,
            "commit_author": commit_author,
            "co_authors": co_authors,
        }

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from GitHub: {e}")
        return None


def get_pull_request_body(commit_hash, repository="saleor/saleor-dashboard"):
    """
    Legacy method maintained for backward compatibility.
    Use get_pull_request_info instead which returns more information.
    """
    info = get_pull_request_info(commit_hash, repository)
    return info["pr_body"] if info and info["pr_body"] else None


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
            pr_info = get_pull_request_info(commit_hash, repository)

            if pr_info:
                # Start with commit info header
                release_notes += f"Commit {commit_hash}"

                # Add PR number if available
                if pr_info["pr_number"]:
                    release_notes += f" (PR #{pr_info['pr_number']})"

                release_notes += ":\n"

                # Collect all contributors
                contributors = []

                # Add commit author
                if pr_info["commit_author"] and pr_info["commit_author"] != "Unknown":
                    contributors.append(pr_info["commit_author"])

                # Add PR author if different from commit author
                if (
                    pr_info["pr_author"]
                    and pr_info["pr_author"] != "Unknown"
                    and pr_info["pr_author"] != pr_info["commit_author"]
                ):
                    contributors.append(pr_info["pr_author"])

                # Add co-authors
                contributors.extend(pr_info["co_authors"])

                # Remove duplicates while preserving order
                unique_contributors = []
                for contributor in contributors:
                    if contributor not in unique_contributors:
                        unique_contributors.append(contributor)

                if unique_contributors:
                    release_notes += (
                        "Contributors: " + ", ".join(unique_contributors) + "\n"
                    )

                # Add PR body if available
                if pr_info["pr_body"]:
                    release_notes += "\n" + pr_info["pr_body"] + "\n\n"
                else:
                    release_notes += "\nNo pull request description found.\n\n"
            else:
                release_notes += (
                    f"Commit {commit_hash}: Could not retrieve commit information.\n\n"
                )
    return release_notes


def main():
    # Initialize environment
    setup()

    parser = argparse.ArgumentParser(
        description="Generate release notes based on changeset."
    )
    parser.add_argument(
        "-i", "--input", type=str, help="Input file containing changeset text"
    )
    parser.add_argument(
        "-o", "--output", type=str, help="Output file for the release notes"
    )
    parser.add_argument(
        "-r",
        "--repo",
        type=str,
        default="saleor/saleor-dashboard",
        help='GitHub repository in format "owner/repo"',
    )
    args = parser.parse_args()

    # Get changeset text from input file or stdin
    if args.input:
        try:
            with open(args.input, "r") as f:
                changeset_text = f.read()
        except IOError as e:
            print(f"Error reading input file: {e}")
            sys.exit(1)
    else:
        print(
            "Please paste your changeset text (press Ctrl+D on Unix/Mac or Ctrl+Z then Enter on Windows when done):"
        )
        changeset_text = sys.stdin.read()

    if not changeset_text.strip():
        print("Error: No changeset text provided.")
        sys.exit(1)

    # Generate release notes
    release_notes = generate_release_notes(changeset_text, args.repo)

    # Output release notes to file or stdout
    if args.output:
        try:
            with open(args.output, "w") as f:
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
