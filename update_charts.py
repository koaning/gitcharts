# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///

"""Read repos.yml and run git_archaeology.py for each repo."""

import subprocess
import sys
from pathlib import Path

import yaml


def main():
    config = yaml.safe_load(Path("repos.yml").read_text())

    for entry in config["repos"]:
        repo = entry["repo"]
        print(f"\n{'='*60}")
        print(f"Updating {repo}...")
        print(f"{'='*60}")

        cmd = [
            "uv", "run", "git_archaeology.py",
            "--repo", repo,
            "--version_source", "pypi",
        ]
        if "pypi_name" in entry:
            cmd.extend(["--pypi_name", entry["pypi_name"]])

        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"WARNING: Failed to update {repo}", file=sys.stderr)


if __name__ == "__main__":
    main()
