# Git Code Archaeology Notebook Plan

## Objective
Create a marimo notebook that analyzes any git repository and produces a stacked area chart showing lines of code over time, broken down by the year each line was originally added.

## Core Features
1. Parse git history using `git blame` to track when lines were added
2. Group lines by the year they were committed
3. Show how code from each year accumulates over time via stacked area chart
4. Save output as PNG and interactive HTML

## Tech Stack
- **marimo** - notebook framework
- **polars** - data processing (fast, expressive pipelines)
- **altair** - declarative visualization
- **uv** - dependency management (inline script metadata)

## Proposed Structure (Single marimo notebook)

### Cells:

1. **Imports** - marimo, subprocess, polars, altair, datetime

2. **Documentation** - Title and explanation

3. **Configuration UI**:
   - Repository path input (text, default ".")
   - Number of commits to sample (slider)
   - File extensions filter (comma-separated)

4. **Git Functions**:
   - `run_git_command()` - Execute git commands safely
   - `get_commit_list()` - Get commits with dates → returns Polars DataFrame
   - `get_tracked_files()` - List files at a commit
   - `get_blame_info()` - Parse `git blame --line-porcelain` output

5. **Polars Pipeline** - Single expressive pipeline that:
   - Iterates sampled commits
   - Collects blame data per commit
   - Aggregates line counts by (commit_date, year_added)
   - Returns tidy DataFrame ready for Altair

6. **Run Analysis** - Button + progress bar

7. **Altair Visualization** - Stacked area chart with:
   - x: commit_date
   - y: line_count (stacked)
   - color: year_added
   - Interactive tooltips

8. **Export** - Save PNG (via altair_saver) and HTML

## Polars Pipeline Design

```python
# Collect raw blame data
raw_data = []
for commit_hash, commit_date in sampled_commits:
    for file in get_tracked_files(repo, commit_hash, extensions):
        blame = get_blame_info(repo, commit_hash, file)
        for year, count in blame.items():
            raw_data.append((commit_date, year, count))

# Single Polars pipeline
df = (
    pl.DataFrame(raw_data, schema=["commit_date", "year_added", "line_count"])
    .group_by(["commit_date", "year_added"])
    .agg(pl.col("line_count").sum())
    .sort(["commit_date", "year_added"])
)
```

## Altair Chart Design

```python
chart = (
    alt.Chart(df)
    .mark_area()
    .encode(
        x="commit_date:T",
        y="line_count:Q",
        color=alt.Color("year_added:O", scale=alt.Scale(scheme="viridis")),
        order=alt.Order("year_added:O"),
        tooltip=["commit_date", "year_added", "line_count"]
    )
    .properties(title="Code Archaeology: Lines by Year Added")
)
```

## File to Create
- `git_archaeology.py` (marimo notebook with uv inline metadata)

## Dependencies (via uv inline script)
```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "polars",
#     "altair",
#     "vl-convert-python",  # for PNG export
# ]
# ///
```
