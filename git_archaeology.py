# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "polars==1.35.2",
#     "altair==6.0.0",
#     "httpx==0.28.1",
#     "pydantic>=2.0.0",
#     "diskcache==5.6.3",
#     "pygit2>=1.13.0",
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
        value=".py,.js,.ts,.java,.c,.cpp,.h,.go,.rs,.rb,.md,.cs,.scss,.html",
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
def _():
    from pydantic import BaseModel, Field
    from pydantic_core import PydanticUndefined

    class RepoParams(BaseModel):
        repo: str = Field(description="Repository URL (HTTPS)")
        samples: int = Field(default=100, description="Number of commits to sample")

    return (RepoParams,)


@app.cell
def _(RepoParams, mo):
    cli_args = mo.cli_args()

    if mo.app_meta().mode == "script":
        if "help" in cli_args or len(cli_args) == 0:
            print("Usage: uv run git_archaeology.py --repo <url> [--samples <n>]")
            print()
            for name, field in RepoParams.model_fields.items():
                default = " (required)" if field.default is PydanticUndefined else f" (default: {field.default})"
                print(f"  --{name:12s} {field.description}{default}")
            exit()
        repo_params = RepoParams(
            **{k.replace("-", "_"): v for k, v in cli_args.items()}
        )
    return cli_args, repo_params


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
                ["git", "fetch", "--all", "--progress"],
                cwd=repo_path,
            )
        else:
            # Clone fresh
            subprocess.run(
                ["git", "clone", "--progress", repo_url, str(repo_path)],
                check=True,
            )
        return repo_path
    return Path, clone_or_update_repo


@app.cell(hide_code=True)
def _(cache, datetime, subprocess):
    import threading
    import pygit2
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

    _thread_local = threading.local()


    def _get_thread_repo(repo_path: str) -> pygit2.Repository:
        """Return a per-thread pygit2.Repository (not safe to share across threads)."""
        if not hasattr(_thread_local, "repos"):
            _thread_local.repos = {}
        if repo_path not in _thread_local.repos:
            _thread_local.repos[repo_path] = pygit2.Repository(repo_path)
        return _thread_local.repos[repo_path]


    def run_git_command(cmd: list[str], repo_path: str) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: {result.stderr}")
        return result.stdout if result.stdout is not None else ""


    @cache.memoize()
    def get_commit_list(repo_path: str) -> list[tuple[str, datetime]]:
        """Get list of all commits with their dates."""
        output = run_git_command(
            ["git", "log", "--format=%H %at", "--reverse"],
            repo_path,
        )
        commits = []
        for line in (output or "").strip().split("\n"):
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
        files = (output or "").strip().split("\n")
        if extensions:
            files = [f for f in files if any(f.endswith(ext) for ext in extensions)]
        return [f for f in files if f]


    def _blame_uncached(repo_path: str, commit_hash: str, file_path: str) -> list[int]:
        """Raw pygit2 blame — no caching. Called from worker threads."""
        try:
            repo = _get_thread_repo(repo_path)
            commit_oid = pygit2.Oid(hex=commit_hash)
            blame = repo.blame(file_path, newest_commit=commit_oid)
            timestamps = []
            for hunk in blame:
                orig_commit = repo.get(hunk.orig_commit_id)
                if orig_commit is not None:
                    timestamps.extend([orig_commit.commit_time] * hunk.lines_in_hunk)
            return timestamps
        except Exception:
            return []


    def _blame_key(repo_path: str, commit_hash: str, file_path: str) -> str:
        return f"blame\x00{repo_path}\x00{commit_hash}\x00{file_path}"


    def get_blame_info(repo_path: str, commit_hash: str, file_path: str) -> list[int]:
        """Cached blame lookup — checks cache first, falls back to pygit2."""
        key = _blame_key(repo_path, commit_hash, file_path)
        result = cache.get(key)
        if result is None:
            result = _blame_uncached(repo_path, commit_hash, file_path)
            cache.set(key, result)
        return result


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


    def collect_blame_data(
        repo_path: str,
        sampled_commits: list[tuple[str, datetime]],
        extensions: list[str] | None,
        progress_bar=None,
        is_script: bool = False,
        workers: int = 32,
    ) -> list[tuple[datetime, int]]:
        """Collect raw blame data from sampled commits.

        Splits work into cache hits (resolved instantly in main thread) and cache
        misses (processed in parallel). Cache writes happen serially in the main
        thread after each batch completes, eliminating SQLite write contention
        which caused exponential slowdown under concurrent access.
        """
        repo_path_str = str(repo_path)

        # Phase 1: gather all (commit_hash, commit_date, file_path) work items
        if is_script:
            print("  Gathering file lists...")
        work_items: list[tuple[str, datetime, str]] = []
        for commit_hash, commit_date in sampled_commits:
            for f in get_tracked_files(repo_path_str, commit_hash, extensions):
                work_items.append((commit_hash, commit_date, f))
        total_files = len(work_items)
        total_commits = len(sampled_commits)

        # Phase 2: split into cached vs uncached — cache checks are fast serial reads
        cached_items: list[tuple[str, datetime, str, list[int]]] = []
        uncached_items: list[tuple[str, datetime, str]] = []

        for h, d, f in work_items:
            result = cache.get(_blame_key(repo_path_str, h, f))
            if result is not None:
                cached_items.append((h, d, f, result))
            else:
                uncached_items.append((h, d, f))

        n_cached = len(cached_items)
        n_uncached = len(uncached_items)
        if is_script:
            print(f"  {n_cached} files cached, {n_uncached} need blaming across {total_commits} commits...")

        raw_data: list[tuple[datetime, int]] = []
        done_files = 0
        done_commits: set[str] = set()

        def _record(commit_hash: str, commit_date: datetime, timestamps: list[int]) -> None:
            nonlocal done_files
            for ts in timestamps:
                raw_data.append((commit_date, ts))
            done_files += 1
            prev = len(done_commits)
            done_commits.add(commit_hash)
            new_commit = len(done_commits) > prev
            if progress_bar:
                pct = int(done_files / total_files * 100) if total_files else 100
                progress_bar.update(
                    title=f"Blamed {done_files}/{total_files} files "
                          f"({len(done_commits)}/{total_commits} commits, {pct}%)"
                )
            if is_script and new_commit:
                pct = int(done_files / total_files * 100) if total_files else 100
                print(f"  [{len(done_commits)}/{total_commits} commits, {done_files}/{total_files} files] {pct}%", flush=True)

        # Phase 3: drain cached hits instantly
        for h, d, f, result in cached_items:
            _record(h, d, result)

        # Phase 4: parallel blame for cache misses; write cache serially in main thread
        if uncached_items:
            executor = ThreadPoolExecutor(max_workers=workers)
            futures = {
                executor.submit(_blame_uncached, repo_path_str, h, f): (h, d, f)
                for h, d, f in uncached_items
            }
            pending = set(futures)
            try:
                while pending:
                    done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                    for future in done:
                        h, d, f = futures[future]
                        result = future.result()
                        # Write to cache in main thread — no contention
                        cache.set(_blame_key(repo_path_str, h, f), result)
                        _record(h, d, result)
            except KeyboardInterrupt:
                if is_script:
                    print("\n  Interrupted.", flush=True)
                import os
                os._exit(1)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return raw_data
    return collect_blame_data, get_commit_list, sample_commits


@app.cell
def _(
    clone_or_update_repo,
    file_extensions_input,
    get_commit_list,
    mo,
    repo_params,
    repo_url_input,
    sample_commits,
    sample_count_slider,
):
    # Clone or use cached repo
    repo_url = repo_params.repo if mo.app_meta().mode == "script" else repo_url_input.value.strip()
    with mo.status.spinner(f"Cloning/updating repository..."):
        repo_path = clone_or_update_repo(repo_url)

    # Parse configuration
    n_samples = repo_params.samples if mo.app_meta().mode == "script" else sample_count_slider.value
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
    with mo.status.spinner(title="Gathering file lists...") as spinner:
        raw_data = collect_blame_data(repo_path, sampled, extensions, progress_bar=spinner, is_script=mo.app_meta().mode == "script")

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
def _(granularity_select, pl, raw_df):
    granularity = granularity_select.value

    # Convert unix timestamps to datetime natively in Polars (much faster than map_elements)
    line_dt = pl.from_epoch(pl.col("line_timestamp"), time_unit="s")

    if granularity == "Year":
        period_expr = line_dt.dt.year().cast(pl.Utf8).alias("period")
    else:  # Quarter
        period_expr = (
            pl.concat_str(
                [
                    line_dt.dt.year().cast(pl.Utf8),
                    pl.lit("-Q"),
                    ((line_dt.dt.month() - 1) // 3 + 1).cast(pl.Utf8),
                ]
            ).alias("period")
        )

    # Apply granularity and aggregate
    df = (
        raw_df.with_columns(period_expr)
        .group_by(["commit_date", "period"])
        .len()
        .rename({"len": "line_count"})
        .sort(["commit_date", "period"])
    )
    return (df,)


@app.cell
def _(mo, repo_params, repo_url_input):
    import httpx

    _repo = repo_params.repo if mo.app_meta().mode == "script" else repo_url_input.value
    parts = _repo.split("/")
    repo_name = parts[-2] if _repo.endswith("/") else parts[-1]

    res = httpx.get(f"https://pypi.org/pypi/{repo_name}/json").json()
    return repo_name, res


@app.cell
def _(alt, pl, res):
    _version_data = [
        {"version": key, "datetime": value[0]["upload_time"]}
        for key, value in res.get("releases", {}).items()
        if key.endswith(".0") and key != "0.0.0" and len(value) > 0
    ]
    has_versions = len(_version_data) > 0

    if has_versions:
        df_versions = pl.DataFrame(
            _version_data,
            schema={"version": pl.Utf8, "datetime": pl.Utf8},
        ).with_columns(datetime=pl.col("datetime").str.to_datetime())

        base_chart = alt.Chart(df_versions)

        date_lines = base_chart.mark_rule(strokeDash=[5, 5]).encode(
            x=alt.X("datetime:T", title="Date"), tooltip=["version:N", "datetime:T"]
        )

        date_text = base_chart.mark_text(angle=270, align="left", dx=15, dy=0).encode(
            x="datetime:T", y=alt.value(10), text="version:N"
        )
    else:
        date_lines = None
        date_text = None
    return date_lines, date_text, has_versions


@app.cell
def _(alt, date_lines, date_text, df, granularity_select, has_versions, show_versions):
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
    if show_versions.value and has_versions:
        out += date_lines + date_text

    out = out.properties(
        title="Code Archaeology: Lines of Code by Period Added",
        width=800,
        height=500,
    )

    out
    return chart, out


@app.cell
def _(Path, alt, chart, date_lines, date_text, has_versions, out, repo_name):
    Path("charts").mkdir(exist_ok=True)

    clean_path = Path("charts") / (repo_name + "-clean.json")
    clean_path.write_text(out.to_json())

    versioned_path = Path("charts") / (repo_name + "-versioned.json")
    if has_versions:
        versioned_chart = (
            (chart + date_lines + date_text)
            .properties(
                title="Code Archaeology: Lines of Code by Period Added",
                width=800,
                height=500,
            )
            .to_dict()
        )
        versioned_path.write_text(alt.Chart.from_dict(versioned_chart).to_json())
    else:
        versioned_path.write_text(out.to_json())
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
