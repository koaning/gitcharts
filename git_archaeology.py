# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "polars==1.35.2",
#     "altair==6.0.0",
#     "httpx==0.28.1",
#     "anthropic==0.75.0",
#     "diskcache==5.6.3",
#     "typer==0.20.0",
# ]
# ///

import marimo

__generated_with = "0.18.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell(hide_code=True)
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
    from diskcache import Cache

    cache = Cache("git-research")
    return alt, cache, datetime, pl, subprocess


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Configuration
    """)
    return


@app.cell
def _():
    return


@app.cell
def _(mo):
    repo_url_input = mo.ui.text(
        value="https://github.com/marimo-team/marimo",
        label="Repository URL (HTTPS)",
        full_width=True,
    )
    repo_url_input
    return (repo_url_input,)


@app.cell
def _(mo):
    sample_count_slider = mo.ui.slider(
        start=10,
        stop=200,
        value=100,
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
    granularity_select = mo.ui.dropdown(
        options=["Year", "Quarter"],
        value="Quarter",
        label="Time granularity",
    )
    granularity_select
    return (granularity_select,)


@app.cell
def _(mo):
    show_versions = mo.ui.checkbox(label="show versions")
    show_versions
    return (show_versions,)


@app.cell
def _(mo):
    cli_args = mo.cli_args()

    if mo.app_meta().mode == "script": 
        if len(cli_args) == 0:
            print("You need to pass --repo, and maybe --samples, explicitly.")
            exit()
    return (cli_args,)


@app.cell(hide_code=True)
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
    return Path, clone_or_update_repo


@app.cell(hide_code=True)
def _(cache, datetime, subprocess):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import re

    # Pre-compile regex for timestamp extraction (used in get_blame_info)
    # Format: hash (author timestamp tz line_num) content
    TIMESTAMP_PATTERN = re.compile(r"\(.*?\s+(\d{10})\s+[+-]\d{4}\s+\d+\)")


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


    @cache.memoize()
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


    def get_blame_info(repo_path: str, commit_hash: str, file_path: str) -> list[int]:
        """
        Get blame info for a file at a specific commit.
        Returns list of timestamps for each line.

        Uses -t flag for raw timestamp output which is much faster than --line-porcelain.
        Format: <hash> <orig_line> <final_line> <num_lines> (<author> <timestamp> <tz>) <content>
        """
        try:
            output = run_git_command(
                ["git", "blame", "-t", commit_hash, "--", file_path],
                repo_path,
            )
        except (RuntimeError, UnicodeDecodeError):
            # File might be binary or have other issues
            return []

        timestamps = []
        for line in output.split("\n"):
            if not line:
                continue
            match = TIMESTAMP_PATTERN.search(line)
            if match:
                timestamps.append(int(match.group(1)))

        return timestamps


    @cache.memoize()
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

    @cache.memoize()
    def analyze_single_commit(
        repo_path: str,
        commit_hash: str,
        commit_date: datetime,
        extensions: list[str] | None,
        file_workers: int = 4,
    ) -> list[tuple[datetime, int]]:
        """Analyze a single commit - designed for parallel execution.

        Uses nested parallelization: commits in parallel, files within each commit also in parallel.
        """
        files = get_tracked_files(repo_path, commit_hash, extensions)

        def blame_file(file_path: str) -> list[int]:
            return get_blame_info(repo_path, commit_hash, file_path)

        results = []
        # Parallelize file processing within each commit
        with ThreadPoolExecutor(max_workers=file_workers) as file_executor:
            file_futures = {file_executor.submit(blame_file, f): f for f in files}
            for future in as_completed(file_futures):
                timestamps = future.result()
                for ts in timestamps:
                    results.append((commit_date, ts))
        return results


    @cache.memoize(ignore=["progress_bar"])
    def collect_blame_data(
        repo_path: str,
        sampled_commits: list[tuple[str, datetime]],
        extensions: list[str] | None,
        progress_bar=None,
        max_workers: int = 12,
    ) -> list[tuple[datetime, int]]:
        """Collect raw blame data from sampled commits in parallel."""
        raw_data = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(analyze_single_commit, str(repo_path), h, d, extensions): (h, d)
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
def _(
    cli_args,
    clone_or_update_repo,
    file_extensions_input,
    get_commit_list,
    mo,
    repo_url_input,
    sample_commits,
    sample_count_slider,
):
    # Clone or use cached repo
    repo_url = cli_args.get("repo") or repo_url_input.value.strip()
    with mo.status.spinner(f"Cloning/updating repository..."):
        repo_path = clone_or_update_repo(repo_url)

    # Parse configuration
    n_samples = cli_args.get("samples") or sample_count_slider.value
    extensions_str = file_extensions_input.value.strip()
    extensions = [ext.strip() for ext in extensions_str.split(",")] if extensions_str else None

    # Get commits
    with mo.status.spinner("Getting commit history..."):
        all_commits = get_commit_list(str(repo_path))
        sampled = sample_commits(all_commits, n_samples)

    mo.md(f"Found **{len(all_commits)}** commits, sampling **{len(sampled)}** for analysis")
    return extensions, repo_path, sampled


@app.cell
def _(collect_blame_data, extensions, mo, pl, repo_path, sampled):
    with mo.status.progress_bar(
        total=len(sampled),
        title="Analyzing commits",
        show_rate=True,
        show_eta=True,
    ) as bar:
        raw_data = collect_blame_data(repo_path, sampled, extensions, progress_bar=bar)

    # Store raw data as DataFrame with timestamps
    raw_df = pl.DataFrame(raw_data, schema=["commit_date", "line_timestamp"], orient="row")
    return (raw_df,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Visualization
    """)
    return


@app.cell
def _(datetime, granularity_select, pl, raw_df):
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
        raw_df.with_columns(
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
def _(cli_args, repo_url_input):
    import httpx

    _repo = cli_args.get("repo") or repo_url_input.value
    parts = _repo.split("/")
    repo_name = parts[-2] if _repo.endswith("/") else parts[-1]

    res = httpx.get(f"https://pypi.org/pypi/{repo_name}/json").json()
    return repo_name, res


@app.cell
def _(alt, pl, res):
    df_versions = pl.DataFrame(
        [
            {"version": key, "datetime": value[0]["upload_time"]}
            for key, value in res["releases"].items()
            if key.endswith(".0") and key != "0.0.0"
        ]
    ).with_columns(datetime=pl.col("datetime").str.to_datetime())

    base_chart = alt.Chart(df_versions)

    date_lines = base_chart.mark_rule(strokeDash=[5, 5]).encode(
        x=alt.X("datetime:T", title="Date"), tooltip=["version:N", "datetime:T"]
    )

    date_text = base_chart.mark_text(angle=270, align="left", dx=15, dy=0).encode(
        x="datetime:T", y=alt.value(10), text="version:N"
    )
    return date_lines, date_text


@app.cell
def _(alt, date_lines, date_text, df, granularity_select, show_versions):
    color_title = "Year Added" if granularity_select.value == "Year" else "Quarter Added"

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
    )

    out = chart
    if show_versions.value:
        out += date_lines + date_text
    
    out = out.properties(
        title="Code Archaeology: Lines of Code by Period Added",
        width=800,
        height=500,
    )

    out
    return chart, out


@app.cell
def _(Path, alt, chart, date_lines, date_text, out, repo_name):
    Path("charts").mkdir(exist_ok=True)

    clean_path = Path("charts") / (repo_name + "-clean.json")
    clean_path.write_text(out.to_json())

    versioned_path = Path("charts") / (repo_name + "-versioned.json")
    versioned_chart = (chart + date_lines + date_text).properties(
        title="Code Archaeology: Lines of Code by Period Added",
        width=800,
        height=500,
    ).to_dict()
    versioned_path.write_text(alt.Chart.from_dict(versioned_chart).to_json())
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
