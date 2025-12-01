# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "polars",
#     "altair",
# ]
# ///

import marimo

__generated_with = "0.18.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    # Git Code Archaeology

    This notebook analyzes a git repository to visualize how code ages over time.
    It creates a stacked area chart showing lines of code broken down by the year
    each line was originally added, revealing how quickly code gets replaced.
    """)
    return


@app.cell
def _():
    import subprocess
    from datetime import datetime
    from collections import defaultdict
    import polars as pl
    import altair as alt
    return alt, datetime, pl, subprocess


@app.cell
def _(mo):
    mo.md("""
    ## Configuration
    """)
    return


@app.cell
def _(mo):
    repo_url_input = mo.ui.text(
        value="https://github.com/koaning/scikit-lego",
        label="Repository URL (HTTPS)",
        full_width=True,
    )
    repo_url_input
    return (repo_url_input,)


@app.cell
def _(mo):
    sample_count_slider = mo.ui.slider(
        start=10,
        stop=100,
        value=30,
        step=5,
        label="Number of commits to sample",
    )
    sample_count_slider
    return (sample_count_slider,)


@app.cell
def _(mo):
    file_extensions_input = mo.ui.text(
        value=".py,.js,.ts,.java,.c,.cpp,.h,.go,.rs,.rb,.md",
        label="File extensions to analyze (comma-separated, leave empty for all)",
        full_width=True,
    )
    file_extensions_input
    return (file_extensions_input,)


@app.cell
def _(mo):
    mo.md("""
    ## Git Analysis Functions
    """)
    return


@app.cell
def _(subprocess):
    from pathlib import Path
    import hashlib

    DOWNLOADS_DIR = Path(".downloads")

    def get_cached_repo_path(repo_url: str) -> Path:
        """Get the cached path for a repo URL, using a hash for uniqueness."""
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        url_hash = hashlib.md5(repo_url.encode()).hexdigest()[:8]
        return DOWNLOADS_DIR / f"{repo_name}-{url_hash}"

    def clone_or_update_repo(repo_url: str) -> Path:
        """Clone repo if not cached, otherwise return cached path."""
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        repo_path = get_cached_repo_path(repo_url)

        if repo_path.exists():
            # Repo already cached, fetch latest
            subprocess.run(
                ["git", "fetch", "--all"],
                cwd=repo_path,
                capture_output=True,
            )
        else:
            # Clone fresh
            subprocess.run(
                ["git", "clone", repo_url, str(repo_path)],
                capture_output=True,
                check=True,
            )
        return repo_path
    return (clone_or_update_repo,)


@app.cell
def _(datetime, subprocess):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def run_git_command(cmd: list[str], repo_path: str) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: {result.stderr}")
        return result.stdout


    def get_commit_list(repo_path: str) -> list[tuple[str, datetime]]:
        """Get list of all commits with their dates."""
        output = run_git_command(
            ["git", "log", "--format=%H %at", "--reverse"],
            repo_path,
        )
        commits = []
        for line in output.strip().split("\n"):
            if line:
                parts = line.split()
                commit_hash = parts[0]
                timestamp = int(parts[1])
                commit_date = datetime.fromtimestamp(timestamp)
                commits.append((commit_hash, commit_date))
        return commits


    def get_tracked_files(
        repo_path: str, commit_hash: str, extensions: list[str] | None = None
    ) -> list[str]:
        """Get list of tracked files at a specific commit."""
        output = run_git_command(
            ["git", "ls-tree", "-r", "--name-only", commit_hash],
            repo_path,
        )
        files = output.strip().split("\n")
        if extensions:
            files = [f for f in files if any(f.endswith(ext) for ext in extensions)]
        return [f for f in files if f]


    def get_blame_info(
        repo_path: str, commit_hash: str, file_path: str
    ) -> list[int]:
        """
        Get blame info for a file at a specific commit.
        Returns list of timestamps for each line.
        """
        try:
            output = run_git_command(
                ["git", "blame", "--line-porcelain", commit_hash, "--", file_path],
                repo_path,
            )
        except (RuntimeError, UnicodeDecodeError):
            # File might be binary or have other issues
            return []

        timestamps = []
        for line in output.split("\n"):
            if line.startswith("author-time "):
                timestamp = int(line.split()[1])
                timestamps.append(timestamp)

        return timestamps


    def sample_commits(
        commits: list[tuple[str, datetime]], n_samples: int
    ) -> list[tuple[str, datetime]]:
        """Sample n commits evenly distributed across history."""
        if len(commits) <= n_samples:
            return commits
        step = len(commits) / n_samples
        indices = [int(i * step) for i in range(n_samples)]
        # Always include the last commit
        if indices[-1] != len(commits) - 1:
            indices[-1] = len(commits) - 1
        return [commits[i] for i in indices]


    def analyze_single_commit(
        repo_path: str,
        commit_hash: str,
        commit_date: datetime,
        extensions: list[str] | None,
    ) -> list[tuple[datetime, int]]:
        """Analyze a single commit - designed for parallel execution."""
        results = []
        for file_path in get_tracked_files(repo_path, commit_hash, extensions):
            timestamps = get_blame_info(repo_path, commit_hash, file_path)
            for ts in timestamps:
                results.append((commit_date, ts))
        return results


    def collect_blame_data(
        repo_path: str,
        sampled_commits: list[tuple[str, datetime]],
        extensions: list[str] | None,
        progress_bar=None,
        max_workers: int = 8,
    ) -> list[tuple[datetime, int]]:
        """Collect raw blame data from sampled commits in parallel."""
        raw_data = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    analyze_single_commit, str(repo_path), h, d, extensions
                ): (h, d)
                for h, d in sampled_commits
            }
            for future in as_completed(futures):
                commit_hash, _ = futures[future]
                if progress_bar:
                    progress_bar.update(title=f"Analyzed {commit_hash[:8]}...")
                raw_data.extend(future.result())

        return raw_data
    return collect_blame_data, get_commit_list, sample_commits


@app.cell
def _(mo):
    mo.md("""
    ## Run Analysis
    """)
    return


@app.cell
def _(mo):
    run_button = mo.ui.run_button(label="Analyze Repository")
    run_button
    return (run_button,)


@app.cell
def _(
    clone_or_update_repo,
    file_extensions_input,
    get_commit_list,
    mo,
    repo_url_input,
    run_button,
    sample_commits,
    sample_count_slider,
):
    mo.stop(
        not run_button.value,
        mo.md("*Click 'Analyze Repository' to start the analysis*"),
    )

    # Clone or use cached repo
    repo_url = repo_url_input.value.strip()
    with mo.status.spinner(f"Cloning/updating repository..."):
        repo_path = clone_or_update_repo(repo_url)

    # Parse configuration
    n_samples = sample_count_slider.value
    extensions_str = file_extensions_input.value.strip()
    extensions = (
        [ext.strip() for ext in extensions_str.split(",")] if extensions_str else None
    )

    # Get commits
    with mo.status.spinner("Getting commit history..."):
        all_commits = get_commit_list(str(repo_path))
        sampled = sample_commits(all_commits, n_samples)

    mo.md(f"Found **{len(all_commits)}** commits, sampling **{len(sampled)}** for analysis")
    return extensions, repo_path, sampled


@app.cell
def _(collect_blame_data, extensions, mo, pl, repo_path, run_button, sampled):
    mo.stop(not run_button.value, None)

    # Collect and process data with progress bar
    with mo.status.progress_bar(
        total=len(sampled),
        title="Analyzing commits",
        show_rate=True,
        show_eta=True,
    ) as bar:
        raw_data = collect_blame_data(repo_path, sampled, extensions, progress_bar=bar)

    # Store raw data as DataFrame with timestamps
    raw_df = pl.DataFrame(raw_data, schema=["commit_date", "line_timestamp"])
    return (raw_df,)


@app.cell
def _(mo):
    mo.md("""
    ## Visualization
    """)
    return


@app.cell
def _(mo):
    granularity_select = mo.ui.dropdown(
        options=["Year", "Quarter"],
        value="Year",
        label="Time granularity",
    )
    granularity_select
    return (granularity_select,)


@app.cell
def _(datetime, granularity_select, mo, pl, raw_df, run_button):
    mo.stop(not run_button.value or raw_df.is_empty(), None)

    granularity = granularity_select.value

    def get_period(ts: int, granularity: str) -> str:
        dt = datetime.fromtimestamp(ts)
        if granularity == "Year":
            return str(dt.year)
        else:  # Quarter
            q = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{q}"

    # Apply granularity and aggregate
    df = (
        raw_df
        .with_columns(
            pl.col("line_timestamp")
            .map_elements(lambda ts: get_period(ts, granularity), return_dtype=pl.Utf8)
            .alias("period")
        )
        .group_by(["commit_date", "period"])
        .len()
        .rename({"len": "line_count"})
        .sort(["commit_date", "period"])
    )
    return (df,)


@app.cell
def _(alt, df, granularity_select, mo, run_button):
    mo.stop(not run_button.value or df.is_empty(), mo.md("*No data to visualize*"))

    _granularity = granularity_select.value
    color_title = "Year Added" if _granularity == "Year" else "Quarter Added"

    chart = (
        alt.Chart(df)
        .mark_area()
        .encode(
            x=alt.X("commit_date:T", title="Date"),
            y=alt.Y("line_count:Q", title="Lines of Code"),
            color=alt.Color(
                "period:O",
                scale=alt.Scale(scheme="viridis"),
                title=color_title,
            ),
            order=alt.Order("period:O"),
            tooltip=["commit_date:T", "period:O", "line_count:Q"],
        )
        .properties(
            title="Code Archaeology: Lines of Code by Period Added",
            width=800,
            height=500,
        )
    )

    chart
    return


if __name__ == "__main__":
    app.run()
