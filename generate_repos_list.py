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
    # Exclude develop branch files (e.g. repo-develop-clean.json)
    clean_files = list(charts_dir.glob("*-clean.json"))

    repos = {}
    for file in clean_files:
        name = file.stem.replace("-clean", "")
        # Skip develop/dev/development branch files
        if name.endswith(("-develop", "-development", "-dev")):
            continue

        variants = ["clean"]

        versioned_file = charts_dir / f"{name}-versioned.json"
        if versioned_file.exists():
            variants.append("versioned")

        repos[name] = variants

    # Sort by name for consistency
    repos = dict(sorted(repos.items()))

    # Write to charts/repos.json
    output_path = charts_dir / "repos.json"
    output_path.write_text(json.dumps(repos, indent=2))

    print(f"Generated {output_path} with {len(repos)} repositories")
    for repo, variants in repos.items():
        print(f"  - {repo} ({', '.join(variants)})")


if __name__ == "__main__":
    main()
