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
    import pygit2
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

    # Repo cache for the main thread (used by _get_changed_files)
    _main_repos: dict[str, pygit2.Repository] = {}


    def _get_repo(repo_path: str) -> pygit2.Repository:
        if repo_path not in _main_repos:
            _main_repos[repo_path] = pygit2.Repository(repo_path)
        return _main_repos[repo_path]


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
        """Run git blame as subprocess (releases GIL → true parallelism with threads)."""
        try:
            result = subprocess.run(
                ["git", "blame", "--porcelain", commit_hash, "--", file_path],
                cwd=repo_path,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return []
            # --porcelain: lines starting with "author-time " have the timestamp
            # Using find() is faster than startswith() per line for large output
            out = result.stdout
            timestamps = []
            pos = 0
            marker = "author-time "
            marker_len = 12
            while True:
                pos = out.find(marker, pos)
                if pos == -1:
                    break
                end = out.find("\n", pos + marker_len)
                if end == -1:
                    end = len(out)
                timestamps.append(int(out[pos + marker_len:end]))
                pos = end
            return timestamps
        except Exception:
            return []


    def _blame_key(repo_path: str, commit_hash: str, file_path: str) -> str:
        return f"blame2\x00{commit_hash}\x00{file_path}"


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


    def _get_changed_files(repo_path: str, prev_hash: str, curr_hash: str) -> set[str] | None:
        """Get set of file paths that changed between two commits using pygit2 diff.
        Returns None on failure (caller should re-blame everything)."""
        try:
            repo = _get_repo(repo_path)
            prev_commit = repo.get(pygit2.Oid(hex=prev_hash))
            curr_commit = repo.get(pygit2.Oid(hex=curr_hash))
            diff = repo.diff(prev_commit.tree, curr_commit.tree)
            changed = set()
            for patch in diff:
                changed.add(patch.delta.old_file.path)
                changed.add(patch.delta.new_file.path)
            return changed
        except Exception:
            return None  # fallback: caller will treat all files as changed


    def collect_blame_data(
        repo_path: str,
        sampled_commits: list[tuple[str, datetime]],
        extensions: list[str] | None,
        progress_bar=None,
        is_script: bool = False,
        workers: int = 32,
    ) -> list[tuple[datetime, int]]:
        """Collect raw blame data from sampled commits.

        Uses incremental diffing: for each commit after the first, only re-blames
        files that changed since the previous sampled commit. Unchanged files reuse
        their previous blame result. This typically reduces work by 80-95%.
        """
        import time

        repo_path_str = str(repo_path)
        raw_data: list[tuple[datetime, int]] = []
        total_commits = len(sampled_commits)

        # Running state: file → blame timestamps, carried forward between commits
        current_blame: dict[str, list[int]] = {}
        prev_commit_hash: str | None = None

        for ci, (commit_hash, commit_date) in enumerate(sampled_commits):
            t0 = time.perf_counter()

            files = get_tracked_files(repo_path_str, commit_hash, extensions)
            file_set = set(files)

            # Determine which files need re-blaming
            if prev_commit_hash is None:
                # First commit: everything is new
                need_blame = set(files)
            else:
                changed = _get_changed_files(repo_path_str, prev_commit_hash, commit_hash)
                if changed is None:
                    # diff failed — be safe, re-blame everything
                    need_blame = file_set
                else:
                    # Only blame files that are (a) changed and (b) still exist
                    need_blame = file_set & changed
                    # Also blame files that are new (not in previous blame state)
                    need_blame |= file_set - set(current_blame)

            # Remove deleted files from running state
            for f in list(current_blame):
                if f not in file_set:
                    del current_blame[f]

            # Check cache for files that need blaming
            uncached_files: list[str] = []
            for f in need_blame:
                cached = cache.get(_blame_key(repo_path_str, commit_hash, f))
                if cached is not None:
                    current_blame[f] = cached
                else:
                    uncached_files.append(f)

            # Parallel blame for uncached files
            new_results: dict[str, list[int]] = {}
            if uncached_files:
                executor = ThreadPoolExecutor(max_workers=workers)
                futures = {
                    executor.submit(_blame_uncached, repo_path_str, commit_hash, f): f
                    for f in uncached_files
                }
                pending = set(futures)
                try:
                    while pending:
                        done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                        for future in done:
                            f = futures[future]
                            new_results[f] = future.result()
                except KeyboardInterrupt:
                    if is_script:
                        print("\n  Interrupted.", flush=True)
                    import os
                    os._exit(1)
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)

                # Update running state + batch cache write in single transaction
                with cache.transact():
                    for f, timestamps in new_results.items():
                        current_blame[f] = timestamps
                        cache.set(_blame_key(repo_path_str, commit_hash, f), timestamps)

            # Build raw_data for this commit from the running state
            for f in files:
                if f in current_blame:
                    for ts in current_blame[f]:
                        raw_data.append((commit_date, ts))

            elapsed = time.perf_counter() - t0
            n_files = len(files)
            n_reused = n_files - len(need_blame)
            n_cache_hit = len(need_blame) - len(uncached_files)
            n_blamed = len(uncached_files)
            n_lines = sum(len(current_blame.get(f, [])) for f in files)
            msg = (
                f"[{ci + 1}/{total_commits}] {commit_hash[:8]} — "
                f"{n_files} files ({n_blamed} blamed, {n_cache_hit} cached, {n_reused} reused), "
                f"{n_lines} lines in {elapsed:.1f}s"
            )
            if progress_bar:
                progress_bar.update(title=msg)
            if is_script:
                print(f"  {msg}", flush=True)

            prev_commit_hash = commit_hash

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
