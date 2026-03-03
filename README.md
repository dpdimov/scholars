# B&M Scholars Database

A tool for building and exploring a longitudinal database of **Business & Management** scholars from the Stanford/Elsevier Top 2% Scientist rankings (2019–2024).

## Project Structure

| File | Description |
|---|---|
| `build_bm_database.py` | Data pipeline — extracts, merges, and flags scholars |
| `app.py` | Streamlit dashboard for interactive exploration |
| `bm_scholars_database.csv` | Output database (built by the pipeline) |
| `bm_scholars_database.xlsx` | Same output in Excel format |
| `fuzzy_matches_review.csv` | Log of fuzzy name matches for manual review |
| `_cache/` | Cached per-year B&M extracts (avoids re-reading large xlsx files) |

## Data Pipeline (`build_bm_database.py`)

Builds the unified scholars database from source Excel files.

**What it does:**

1. **Auto-discovers** source files matching `Scholars YYYY year*.xlsx` / `Scholars YYYY career*.xlsx`
2. **Extracts** Business & Management scholars from each file
3. **Caches** extracts as small CSVs in `_cache/` — source xlsx files can be deleted after caching
4. **Merges** all year/type extracts into a single scholar-level database using:
   - Exact name matching
   - Fuzzy name matching (rapidfuzz, threshold 90) with institution/country boosting
5. **Flags entrepreneurship scholars** by matching against an external reviewer database
6. **Outputs** `bm_scholars_database.csv` and `.xlsx`

**Usage:**

```bash
python build_bm_database.py
```

## Dashboard (`app.py`)

An interactive Streamlit app with four tabs.

**Run:**

```bash
streamlit run app.py
```

### Sidebar Filters

- **Country** — filter by one or more countries
- **Entrepreneurship scholars only** — toggle to show only flagged scholars
- **Search name** — free-text search on scholar names

All tabs respond to these filters. A scholar count is displayed at the bottom of the sidebar.

### Tab 1: Scholar Table

- Sortable, searchable table of all (filtered) scholars
- Select a year + type combination (e.g. "career 2024") to choose which metrics are displayed
- Columns: Name, Institution, Country, Entrepreneurship, Rank, H-index, Citations, Composite (C)
- **Download filtered CSV** button for export

### Tab 2: Visualizations

- **Top-20 Countries** — horizontal bar chart of scholar counts by country
- **Top-N Scholars by Metric** — configurable bar chart (metric, year/type, N)
- **Entrepreneurship Breakdown** — counts and average rank comparison
- **Rank Distribution** — histogram of ranks for a selected year/type
- **Top-20 Institutions by Average Rank** — horizontal bar chart

### Tab 3: Scholar Profile

- Select a scholar from the filtered list
- Displays institution, country, first year, and entrepreneurship status
- **Metrics table** — all available metrics across every year and type
- **Rank trend chart** — line chart of rank over time (career vs. single-year)

### Tab 4: Institution Comparison

Compare two or more institutions (or institution groups) side by side.

- **Institution Groups** — create named groups to merge institution name variants (e.g. group "University of Bath" and "University of Bath, School of Management" under one label). Groups persist for the session.
- **Comparison selector** — pick individual institutions and/or defined groups
- **Summary table** — scholar count, average/median rank, average H-index, average citations, average composite score, entrepreneurship percentage
- **Metric comparison** — grouped bar chart of averages
- **Metric distribution** — box plot (rank, H-index, citations, or composite) with group-aware labels
- **Top 5 scholars** — expandable list per institution/group, ranked by selected year/type

## Data Source

Ioannidis, John P.A. (2024), "August 2024 data-update for "Updated science-wide author databases of standardized citation indicators"", Elsevier Data Repository, V7, doi: [10.17632/btchxktzyw.7](https://doi.org/10.17632/btchxktzyw.7)

## Installation

```bash
pip install -r requirements.txt
```

### Dependencies

| Package | Used by |
|---|---|
| `streamlit` | Dashboard app |
| `pandas` | Data loading and manipulation (both scripts) |
| `plotly` | Interactive charts in the dashboard |
| `openpyxl` | Reading/writing Excel files in the pipeline |
| `rapidfuzz` | Fuzzy name matching in the pipeline |
