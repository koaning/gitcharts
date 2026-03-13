# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "polars==1.35.2",
#     "altair==6.0.0",
#     "pydantic>=2.0.0",
#     "diskcache==5.6.3",
#     "tenacity>=8.0.0",
#     "httpx>=0.27.0",
# ]
# ///

import marimo

__generated_with = "0.20.4"
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
def _(mo):
    params_form = (
        mo.md("""
    {repo_url}

    {file_extensions}

    {sample_count}
    """)
        .batch(
            repo_url=mo.ui.text(
                value="https://github.com/marimo-team/marimo",
                label="Repository URL (HTTPS)",
                full_width=True,
            ),
            file_extensions=mo.ui.text(
                value=".py,.js,.ts,.java,.c,.cpp,.h,.go,.rs,.rb,.md,.pyx,.cu,.rst",
                label="File extensions to analyze (comma-separated, leave empty for all)",
                full_width=True,
            ),
            sample_count=mo.ui.slider(
                start=10,
                stop=200,
                value=200,
                step=5,
                label="Number of commits to sample",
            ),
        )
        .form()
    )

    params_form
    return (params_form,)


@app.cell
def _(mo):
    granularity_select = mo.ui.dropdown(
        options=["Year", "Quarter"],
        value="Quarter",
        label="Time granularity",
    )
    return (granularity_select,)


@app.cell
def _(granularity_select, mo):
    version_source = mo.ui.dropdown(
        options=["none", "git tags", "pypi"],
        value="git tags",
        label="Version source",
    )
    show_versions = mo.ui.checkbox(label="show versions")
    invert_layers = mo.ui.checkbox(label="invert layers")
    mo.hstack([version_source, granularity_select, show_versions, invert_layers])
    return invert_layers, show_versions, version_source


@app.cell
def _():
    from pydantic import BaseModel, Field
    from pydantic_core import PydanticUndefined


    class RepoParams(BaseModel):
        repo: str = Field(description="Repository URL (HTTPS)")
        samples: int = Field(default=200, description="Number of commits to sample")
        file_extensions: str = Field(
            default=".py,.js,.ts,.java,.c,.cpp,.h,.go,.rs,.rb,.md,.pyx,.cu,.rst",
            description="Comma-separated file extensions to analyze",
        )
        version_source: str = Field(
            default="git tags", description="Version source: none, git tags, or pypi"
        )
        pypi_name: str = Field(
            default="", description="PyPI package name (defaults to repo name)"
        )

    return PydanticUndefined, RepoParams


@app.cell
def _(PydanticUndefined, RepoParams, mo):
    cli_args = mo.cli_args()

    if mo.app_meta().mode == "script":
        if "help" in cli_args or len(cli_args) == 0:
            print("Usage: uv run git_archaeology.py --repo <url> [--samples <n>]")
            print()
            for name, field in RepoParams.model_fields.items():
                default = (
                    " (required)"
                    if field.default is PydanticUndefined
                    else f" (default: {field.default})"
                )
                print(f"  --{name:12s} {field.description}{default}")
            exit()
        repo_params = RepoParams(**{k.replace("-", "_"): v for k, v in cli_args.items()})
    return (repo_params,)


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
    TIMESTAMP_PATTERN = re.compile(r"\(.*?\s+(\d{10})\s+[+-]\d{4}\s+\d+\)")

    # Single shared pool for file-level blame — avoids spinning up/down per commit
    _file_executor = ThreadPoolExecutor(max_workers=64)


    def run_git_command(cmd: list[str], repo_path: str) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
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


    @cache.memoize()
    def get_tracked_files(
        repo_path: str, commit_hash: str, extensions: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """Get list of (file_path, blob_hash) pairs at a specific commit."""
        output = run_git_command(
            ["git", "ls-tree", "-r", commit_hash],
            repo_path,
        )
        results = []
        for line in output.strip().split("\n"):
            if not line:
                continue
            # Format: <mode> <type> <blob_hash>\t<path>
            meta, file_path = line.split("\t", 1)
            blob_hash = meta.split()[2]
            if extensions and not any(file_path.endswith(ext) for ext in extensions):
                continue
            results.append((file_path, blob_hash))
        return results


    def get_blame_info(repo_path: str, commit_hash: str, file_path: str) -> list[int]:
        """Get blame timestamps for a file. Uses -t for raw timestamp output."""
        try:
            output = run_git_command(
                ["git", "blame", "-t", commit_hash, "--", file_path],
                repo_path,
            )
        except (RuntimeError, UnicodeDecodeError):
            return []

        return [
            int(m.group(1))
            for line in output.split("\n")
            if line and (m := TIMESTAMP_PATTERN.search(line))
        ]


    def get_blame_by_blob(
        blob_hash: str, repo_path: str, commit_hash: str, file_path: str
    ) -> list[int]:
        """Cache blame results by blob hash — identical blob = identical blame."""
        cache_key = ("blame_v1", blob_hash)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        result = get_blame_info(repo_path, commit_hash, file_path)
        cache.set(cache_key, result)
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


    @cache.memoize()
    def analyze_single_commit(
        repo_path: str,
        commit_hash: str,
        commit_timestamp: int,
        extensions: list[str] | None,
    ) -> list[tuple[int, int]]:
        """Analyze a single commit with blob-level blame dedup."""
        files = get_tracked_files(repo_path, commit_hash, extensions)

        def blame_file(file_blob: tuple[str, str]) -> list[int]:
            file_path, blob_hash = file_blob
            return get_blame_by_blob(blob_hash, repo_path, commit_hash, file_path)

        results = []
        file_futures = {_file_executor.submit(blame_file, fb): fb for fb in files}
        for future in as_completed(file_futures):
            for ts in future.result():
                results.append((commit_timestamp, ts))
        return results


    @cache.memoize(ignore=["progress_bar", "is_script"])
    def collect_blame_data(
        repo_path: str,
        sampled_commits: list[tuple[str, datetime]],
        extensions: list[str] | None,
        progress_bar=None,
        is_script: bool = False,
        max_workers: int = 32,
    ) -> list[tuple[int, int]]:
        """Collect raw blame data from sampled commits in parallel."""
        raw_data = []
        total = len(sampled_commits)
        done = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    analyze_single_commit, str(repo_path), h, int(d.timestamp()), extensions
                ): (h, d)
                for h, d in sampled_commits
            }
            for future in as_completed(futures):
                commit_hash, _ = futures[future]
                done += 1
                if progress_bar:
                    progress_bar.update(title=f"Analyzed {commit_hash[:8]}...")
                if is_script:
                    print(f"  [{done}/{total}] Analyzed {commit_hash[:8]}")
                raw_data.extend(future.result())

        return raw_data

    return collect_blame_data, get_commit_list, sample_commits


@app.cell
def _(
    clone_or_update_repo,
    get_commit_list,
    mo,
    params_form,
    repo_params,
    sample_commits,
):
    mo.stop(
        mo.app_meta().mode != "script" and params_form.value is None,
        mo.md("Fill in the form above and click **Submit** to start."),
    )

    # Clone or use cached repo
    repo_url = (
        repo_params.repo
        if mo.app_meta().mode == "script"
        else params_form.value["repo_url"].strip()
    )
    # Accept short GitHub references like "koaning/scikit-lego"
    if "/" in repo_url and not repo_url.startswith(("http://", "https://", "git@")):
        repo_url = f"https://github.com/{repo_url}"
    with mo.status.spinner(f"Cloning/updating repository..."):
        repo_path = clone_or_update_repo(repo_url)

    # Parse configuration
    n_samples = (
        repo_params.samples if mo.app_meta().mode == "script" else params_form.value["sample_count"]
    )
    extensions_str = (
        repo_params.file_extensions
        if mo.app_meta().mode == "script"
        else params_form.value["file_extensions"]
    )
    extensions_str = extensions_str.strip()
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
        raw_data = collect_blame_data(
            repo_path,
            sampled,
            extensions,
            progress_bar=bar,
            is_script=mo.app_meta().mode == "script",
        )

    # Column-oriented construction avoids slow row-by-row datetime inspection
    if raw_data:
        commit_timestamps, line_timestamps = map(list, zip(*raw_data))
    else:
        commit_timestamps, line_timestamps = [], []
    raw_df = pl.DataFrame(
        {"commit_date": commit_timestamps, "line_timestamp": line_timestamps}
    ).with_columns(pl.from_epoch("commit_date", time_unit="s").alias("commit_date"))
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

    # Vectorized period derivation using native Polars dt ops
    ts_col = pl.from_epoch(pl.col("line_timestamp"), time_unit="s")

    if granularity == "Year":
        period_expr = ts_col.dt.year().cast(pl.Utf8).alias("period")
    else:  # Quarter
        period_expr = pl.concat_str(
            ts_col.dt.year().cast(pl.Utf8),
            pl.lit("-Q"),
            ((ts_col.dt.month() - 1) // 3 + 1).cast(pl.Utf8),
        ).alias("period")

    df = (
        raw_df.with_columns(period_expr)
        .group_by(["commit_date", "period"])
        .len()
        .rename({"len": "line_count"})
        .sort(["commit_date", "period"])
    )
    return (df,)


@app.cell
def _(
    datetime,
    mo,
    params_form,
    repo_params,
    repo_path,
    subprocess,
    version_source,
):
    import re as _re

    _repo = repo_params.repo if mo.app_meta().mode == "script" else params_form.value["repo_url"]
    parts = _repo.rstrip("/").split("/")
    repo_name = parts[-1].replace(".git", "")

    _source = repo_params.version_source if mo.app_meta().mode == "script" else version_source.value
    version_rows = []

    if _source == "git tags":
        _result = subprocess.run(
            [
                "git",
                "for-each-ref",
                "--sort=creatordate",
                "--format=%(refname:short)|%(creatordate:unix)",
                "refs/tags",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        _VERSION_RE = _re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.0$")
        for _line in _result.stdout.strip().split("\n"):
            if _line and _VERSION_RE.match(_line.split("|")[0]):
                _tag, _ts = _line.split("|", 1)
                if _ts.strip():
                    version_rows.append(
                        {"version": _tag, "datetime": datetime.fromtimestamp(int(_ts))}
                    )

    elif _source == "pypi":
        import httpx
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        )
        def _fetch_pypi(name):
            return httpx.get(f"https://pypi.org/pypi/{name}/json")

        _pypi_name = (repo_params.pypi_name if mo.app_meta().mode == "script" else "") or repo_name
        try:
            _resp = _fetch_pypi(_pypi_name)
            if _resp.status_code == 200:
                for _key, _value in _resp.json().get("releases", {}).items():
                    if _key.endswith(".0") and _key != "0.0.0" and len(_value) > 0:
                        version_rows.append(
                            {
                                "version": _key,
                                "datetime": datetime.fromisoformat(_value[0]["upload_time"]),
                            }
                        )
        except Exception:
            pass
    return repo_name, version_rows


@app.cell
def _(alt, pl, version_rows):
    date_lines = None
    date_text = None
    if version_rows:
        df_versions = pl.DataFrame(
            version_rows, schema={"version": pl.Utf8, "datetime": pl.Datetime}
        )
        base_chart = alt.Chart(df_versions)

        date_lines = base_chart.mark_rule(strokeDash=[5, 5]).encode(
            x=alt.X("datetime:T", title="Date"), tooltip=["version:N", "datetime:T"]
        )

        date_text = base_chart.mark_text(angle=270, align="left", dx=15, dy=0).encode(
            x="datetime:T", y=alt.value(10), text="version:N"
        )
    return date_lines, date_text


@app.cell
def _(
    alt,
    date_lines,
    date_text,
    df,
    granularity_select,
    invert_layers,
    show_versions,
):
    color_title = "Year Added" if granularity_select.value == "Year" else "Quarter Added"
    sort_order = "descending" if invert_layers.value else "ascending"

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
            order=alt.Order("period:O", sort=sort_order),
            tooltip=["commit_date:T", "period:O", "line_count:Q"],
        )
    )

    out = chart
    if show_versions.value and date_lines is not None:
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
    if date_lines is not None:
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
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
