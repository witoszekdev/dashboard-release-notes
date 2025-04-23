# Dashboard Release Notes Generator

A tool for generating comprehensive release notes by extracting GitHub PR descriptions for each commit hash in a changeset.

## Installation

```bash
# Install with Poetry
poetry install
```

## Usage

You can use this tool in several ways:

```bash
# Run with Poetry
poetry run release-notes

# Specify input/output files
poetry run release-notes -i changeset.txt -o release-notes.txt

# Specify a different GitHub repository
poetry run release-notes -r owner/repository
```

## Environment Variables

To avoid entering your GitHub token each time, set the `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN="your_github_token_here"
```

Or create a `.env` file in the project root with:

```
GITHUB_TOKEN=your_github_token_here
```

## Input Format

The tool expects a changeset text with commit hashes in the following format:

```
saleor-dashboard@3.20.36

Patch Changes

1862202: Now you can see an updated label for gift card list in customer details
ed41cc6: Now navigating to the installed extension, shows the list instantly
f1d40cd: Added "Not found" page when navigating to non-existing route
```

Where each line with a commit hash followed by a colon will be processed to find the associated PR description.