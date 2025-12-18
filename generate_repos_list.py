#!/usr/bin/env python3
"""Generate repos.json from available chart files."""

import json
from pathlib import Path


def main():
    charts_dir = Path("charts")

    if not charts_dir.exists():
        print("charts/ directory not found")
        return

    # Find all -clean.json files to get unique repo names
    clean_files = list(charts_dir.glob("*-clean.json"))

    repos = []
    for file in clean_files:
        # Extract repo name (everything before -clean.json)
        repo_name = file.stem.replace("-clean", "")

        # Check that versioned variant also exists
        versioned_file = charts_dir / f"{repo_name}-versioned.json"
        if versioned_file.exists():
            repos.append(repo_name)

    # Sort by name for consistency
    repos.sort()

    # Write to charts/repos.json
    output_path = charts_dir / "repos.json"
    output_path.write_text(json.dumps(repos, indent=2))

    print(f"Generated {output_path} with {len(repos)} repositories")
    for repo in repos:
        print(f"  - {repo}")


if __name__ == "__main__":
    main()
