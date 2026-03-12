# gitcharts

> A repository with some cool charts that tell us about the history of a git repo.

<img width="1380" height="865" alt="CleanShot 2025-12-18 at 14 02 56" src="https://github.com/user-attachments/assets/93f5c5ff-3a79-4215-9c2c-7c31f71b21d8" />

With charts like this you get an idea of how quickly code is rewritten in a repo. You can explore the GitHub pages link or the marimo notebook to learn more.

## Notebook usage 

[![Open in molab](https://marimo.io/molab-shield.svg)](https://molab.marimo.io/github/koaning/gitcharts/blob/main/git_archaeology.py)

You can download `git_archaeology.py` locally to run it, but you can also run it in molab without downloading anything. The marimo notebook contains all dependencies so can just run `marimo edit` to edit the notebook locally: 

```
uvx marimo edit git_archaeology.py
```

## CLI Usage

You can also run `git_archaeology.py` as a command-line script:

```bash
uv run git_archaeology.py --repo https://github.com/marimo-team/marimo --samples 50
```

**Arguments:**

- `--repo` (required) — Repository URL (HTTPS)
- `--samples` (optional, default: 100) — Number of commits to sample
- `--file-extensions` (optional, default: `.py,.js,.ts,.java,.c,.cpp,.h,.go,.rs,.rb,.md`) — Comma-separated file extensions to analyze
- `--version-source` (optional, default: `git tags`) — Version source: `none`, `git tags`, or `pypi`

After generating charts, run `make build` to update the repository index:

```bash
make build
```

This runs `generate_repos_list.py` to create `charts/repos.json` from the available chart files.

## Viewing Charts Locally

Due to browser security restrictions, you cannot open `index.html` directly from the filesystem. Instead, start a local HTTP server:

```bash
uv run python -m http.server
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.
