"""
Build a longitudinal Business & Management scholars database
from Stanford/Elsevier Top 2% Scientist Excel files.

Auto-discovers files matching 'Scholars YYYY year*.xlsx' and 'Scholars YYYY career*.xlsx',
extracts Business & Management scholars, and merges them with fuzzy name matching.

Caching: Each source file's B&M extract is cached as a small CSV in _cache/.
After caching, you can delete the large .xlsx source files. When new files are
added, only the new ones are read; cached extracts are reused for the rest.

Usage: python build_bm_database.py
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = SCRIPT_DIR / "_cache"
FILE_PATTERN = re.compile(
    r"Scholars\s+(\d{4})\s+(year|career)", re.IGNORECASE
)

# Columns to keep from each file (original names)
KEEP_COLS_STABLE = ["authfull", "inst_name", "cntry", "firstyr", "lastyr"]

# Columns with fixed names across all years
FIXED_METRIC_COLS = {
    "rank": "rank",
    "rank (ns)": "rank_ns",
    "c": "c",
    "c (ns)": "c_ns",
    "self%": "self_pct",
    "rank sm-subfield-1": "rank_subfield",
    "rank sm-subfield-1 (ns)": "rank_subfield_ns",
    "sm-subfield-1 count": "subfield_count",
    "npciting": "npciting",
    "npciting (ns)": "npciting_ns",
}

# Columns whose names vary by year — detected dynamically via regex
# Each entry: (regex pattern, canonical output name)
VARIABLE_METRIC_PATTERNS = [
    (re.compile(r"^h\d{2}$"),          "h"),
    (re.compile(r"^h\d{2} \(ns\)$"),   "h_ns"),
    (re.compile(r"^nc\d{4} \(ns\)$"),  "nc_ns"),
    (re.compile(r"^nc\d{4}$"),         "nc"),
    (re.compile(r"^np60\d{2}$"),       "np60"),
]

FUZZY_THRESHOLD = 90

# Path to entrepreneurship reviewer database (optional)
ENT_REVIEWER_DB = Path("/Users/dpd24/Dropbox/PycharmProjects/ent-reviewers/scopus_reviewer_database.xlsx")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cache_path_for(year: int, ftype: str) -> Path:
    """Return the cache CSV path for a given year/type combo."""
    return CACHE_DIR / f"{ftype}_{year}_bm.csv"


def discover_sources(directory: Path) -> list[dict]:
    """Find all year/type combos from Excel files and/or cached extracts.

    Returns a list of dicts with keys: year, type, xlsx_path (or None), cached (bool).
    """
    found = {}  # key = (year, type) -> dict

    # Check Excel files
    for p in sorted(directory.glob("Scholars *.xlsx")):
        if p.name.startswith("~$"):
            continue
        m = FILE_PATTERN.search(p.name)
        if m:
            year = int(m.group(1))
            ftype = m.group(2).lower()
            found[(year, ftype)] = {
                "year": year,
                "type": ftype,
                "xlsx_path": p,
                "cached": cache_path_for(year, ftype).exists(),
            }

    # Check cache for year/type combos without an xlsx present
    if CACHE_DIR.exists():
        for cp in sorted(CACHE_DIR.glob("*_bm.csv")):
            m2 = re.match(r"(year|career)_(\d{4})_bm\.csv", cp.name)
            if m2:
                ftype = m2.group(1)
                year = int(m2.group(2))
                if (year, ftype) not in found:
                    found[(year, ftype)] = {
                        "year": year,
                        "type": ftype,
                        "xlsx_path": None,
                        "cached": True,
                    }

    return sorted(found.values(), key=lambda x: (x["year"], x["type"]))


def normalize_name(name: str) -> str:
    """Normalize a scholar name for matching.

    - lowercase
    - strip accents
    - remove periods, extra spaces
    - keep 'lastname, firstname' core
    """
    if not isinstance(name, str):
        return ""
    # Strip accents
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    # Remove periods
    s = s.replace(".", "")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def detect_sheet_name(path: Path) -> str:
    """Detect the data sheet name (varies by year: 'Data', 'Career', '2019', etc.)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    sheets = wb.sheetnames
    wb.close()
    # Prefer well-known sheet names
    for name in ["Data", "Career"]:
        if name in sheets:
            return name
    # Try sheets matching a year like '2019', '2020'
    for s in sheets:
        if re.match(r"^\d{4}$", s):
            return s
    # Fall back to last sheet (skip 'Key' and generic 'SheetN')
    for s in reversed(sheets):
        if s != "Key":
            return s
    return sheets[0]


def build_column_mapping(all_headers: list[str]) -> dict[str, str]:
    """Build a mapping from actual column names to canonical output names.

    Returns {actual_col_name: canonical_name} for all metric columns found.
    """
    mapping = {}
    for h in all_headers:
        if h in FIXED_METRIC_COLS:
            mapping[h] = FIXED_METRIC_COLS[h]
            continue
        for pat, canonical in VARIABLE_METRIC_PATTERNS:
            if pat.match(h):
                mapping[h] = canonical
                break
    return mapping


def load_or_extract(source: dict) -> pd.DataFrame:
    """Load B&M scholars from cache, or extract from xlsx and cache the result."""
    year = source["year"]
    ftype = source["type"]
    prefix = f"{ftype}_{year}_"
    cp = cache_path_for(year, ftype)

    if source["cached"]:
        print(f"  Loading from cache: {cp.name}")
        df = pd.read_csv(cp)
        print(f"    → {len(df)} Business & Management scholars (cached)")
        return df

    # Extract from xlsx
    path = source["xlsx_path"]
    print(f"  Reading {path.name} ...")

    sheet = detect_sheet_name(path)

    # First pass: read all columns to detect variable names
    df_all = pd.read_excel(path, sheet_name=sheet, nrows=0)
    all_headers = list(df_all.columns)
    col_map = build_column_mapping(all_headers)

    # Determine which columns to read
    cols_to_read = list(KEEP_COLS_STABLE) + list(col_map.keys()) + ["sm-subfield-1"]
    cols_to_read = [c for c in cols_to_read if c in all_headers]

    df = pd.read_excel(path, sheet_name=sheet, usecols=cols_to_read)
    df = df[df["sm-subfield-1"] == "Business & Management"].copy()
    print(f"    → {len(df)} Business & Management scholars")

    # Rename: actual col -> prefix + canonical name
    rename_map = {actual: prefix + canonical for actual, canonical in col_map.items()}
    df.rename(columns=rename_map, inplace=True)

    # Keep stable cols + prefixed metric cols
    prefixed = [prefix + canonical for canonical in col_map.values()]
    keep = KEEP_COLS_STABLE + prefixed
    df = df[[c for c in keep if c in df.columns]]

    # Save to cache
    CACHE_DIR.mkdir(exist_ok=True)
    df.to_csv(cp, index=False)
    print(f"    Cached to {cp.name}")

    return df


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def merge_all(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple year/type DataFrames into one scholar-level database."""
    if len(dfs) == 0:
        raise ValueError("No dataframes to merge")
    if len(dfs) == 1:
        df = dfs[0].copy()
        df.insert(0, "scholar_id", range(1, len(df) + 1))
        return df, []

    # Start with first df; merge others one at a time
    merged = dfs[0].copy()
    merged["_norm"] = merged["authfull"].apply(normalize_name)
    fuzzy_log = []

    for df_new in dfs[1:]:
        df_new = df_new.copy()
        df_new["_norm"] = df_new["authfull"].apply(normalize_name)

        # Identify metric columns in df_new (non-stable, non-internal)
        metric_cols = [c for c in df_new.columns
                       if c not in KEEP_COLS_STABLE and not c.startswith("_")]

        # --- Pass 1: Exact match on authfull ---
        exact = merged.merge(
            df_new[["authfull"] + metric_cols],
            on="authfull", how="inner",
        )
        matched_in_merged = set(exact["authfull"])
        matched_in_new = set(exact["authfull"])

        # Update merged with new metric cols from exact matches
        merged = merged.merge(
            df_new[["authfull"] + metric_cols],
            on="authfull", how="left",
        )

        # --- Pass 2: Fuzzy match for unmatched ---
        unmatched_new = df_new[~df_new["authfull"].isin(matched_in_new)].copy()
        unmatched_merged_mask = ~merged["authfull"].isin(matched_in_merged)
        unmatched_merged = merged[unmatched_merged_mask].copy()

        fuzzy_matches = {}  # new_idx -> (merged_idx, score, new_authfull, merged_authfull)

        if len(unmatched_new) > 0 and len(unmatched_merged) > 0:
            merged_norms = unmatched_merged["_norm"].tolist()
            merged_idxs = unmatched_merged.index.tolist()
            merged_auths = unmatched_merged["authfull"].tolist()
            merged_insts = unmatched_merged["inst_name"].fillna("").tolist()
            merged_cntrs = unmatched_merged["cntry"].fillna("").tolist()

            for new_idx, new_row in unmatched_new.iterrows():
                new_norm = new_row["_norm"]
                new_inst = str(new_row.get("inst_name", "") or "")
                new_cntry = str(new_row.get("cntry", "") or "")
                best_score = 0
                best_m_idx = None

                for i, m_norm in enumerate(merged_norms):
                    score = fuzz.ratio(new_norm, m_norm)
                    if score < FUZZY_THRESHOLD:
                        continue
                    # Boost if institution or country also match
                    bonus = 0
                    if new_inst and new_inst.lower() == merged_insts[i].lower():
                        bonus += 3
                    if new_cntry and new_cntry.lower() == merged_cntrs[i].lower():
                        bonus += 2
                    total = score + bonus
                    if total > best_score:
                        best_score = total
                        best_m_idx = i

                if best_m_idx is not None:
                    actual_score = fuzz.ratio(new_norm, merged_norms[best_m_idx])
                    fuzzy_matches[new_idx] = (
                        merged_idxs[best_m_idx],
                        actual_score,
                        new_row["authfull"],
                        merged_auths[best_m_idx],
                    )
                    fuzzy_log.append({
                        "name_in_new_file": new_row["authfull"],
                        "name_in_merged": merged_auths[best_m_idx],
                        "fuzzy_score": actual_score,
                        "inst_new": new_inst,
                        "inst_merged": merged_insts[best_m_idx],
                        "cntry_new": new_cntry,
                        "cntry_merged": merged_cntrs[best_m_idx],
                    })

        # Apply fuzzy matches: fill metric cols into merged rows
        for new_idx, (m_idx, score, _, _) in fuzzy_matches.items():
            for col in metric_cols:
                merged.at[m_idx, col] = unmatched_new.at[new_idx, col]
            # Update stable cols if newer data
            for sc in ["inst_name", "cntry", "lastyr"]:
                val = unmatched_new.at[new_idx, sc]
                if pd.notna(val):
                    merged.at[m_idx, sc] = val

        # Append truly new scholars (no match at all)
        matched_new_idxs = set(fuzzy_matches.keys())
        truly_new = unmatched_new[~unmatched_new.index.isin(matched_new_idxs)]
        if len(truly_new) > 0:
            merged = pd.concat([merged, truly_new], ignore_index=True)

    # Clean up
    merged.drop(columns=["_norm"], inplace=True, errors="ignore")

    # Update stable columns: prefer most recent non-null
    # (already handled during merge)

    # Add scholar_id
    # Sort by latest career rank if available, else year rank
    rank_cols = sorted(
        [c for c in merged.columns if c.endswith("_rank") and "subfield" not in c],
        reverse=True,
    )
    if rank_cols:
        merged["_sort"] = merged[rank_cols[0]]
        merged.sort_values("_sort", inplace=True, na_position="last")
        merged.drop(columns=["_sort"], inplace=True)

    merged.reset_index(drop=True, inplace=True)
    merged.insert(0, "scholar_id", range(1, len(merged) + 1))

    return merged, fuzzy_log


# ---------------------------------------------------------------------------
# Entrepreneurship flagging
# ---------------------------------------------------------------------------

def name_to_lastfirst(name: str) -> str:
    """Convert 'First Middle Last' to normalized 'last, first' for matching."""
    parts = name.strip().split()
    if len(parts) < 2:
        return normalize_name(name)
    # Last token is surname (handles "De Massis" edge cases poorly,
    # but normalize_name + fuzzy matching compensates)
    last = parts[-1]
    first = " ".join(parts[:-1])
    return normalize_name(f"{last}, {first}")


def flag_entrepreneurship(merged: pd.DataFrame) -> pd.DataFrame:
    """Add 'entrepreneurship' flag by matching against the reviewer database."""
    if not ENT_REVIEWER_DB.exists():
        print("\n  Entrepreneurship reviewer DB not found, skipping flag.")
        return merged

    print("\nFlagging entrepreneurship scholars...")
    ent_df = pd.read_excel(ENT_REVIEWER_DB, usecols=["Name"])
    ent_names = ent_df["Name"].dropna().unique()
    print(f"  Loaded {len(ent_names)} entrepreneurship reviewers")

    # Build normalized lookup from reviewer names
    ent_norms = {normalize_name(n): n for n in ent_names}
    # Also build "last, first" versions for matching against authfull
    ent_lastfirst = {name_to_lastfirst(n): n for n in ent_names}

    merged["_norm"] = merged["authfull"].apply(normalize_name)
    merged["entrepreneurship"] = False

    matched_exact = 0
    matched_fuzzy = 0

    for idx, row in merged.iterrows():
        bm_norm = row["_norm"]

        # Exact match against last,first normalized forms
        if bm_norm in ent_lastfirst:
            merged.at[idx, "entrepreneurship"] = True
            matched_exact += 1
            continue

        # Also try direct normalized match
        if bm_norm in ent_norms:
            merged.at[idx, "entrepreneurship"] = True
            matched_exact += 1
            continue

        # Fuzzy match against last,first forms
        best_score = 0
        for enorm in ent_lastfirst:
            score = fuzz.ratio(bm_norm, enorm)
            if score > best_score:
                best_score = score
        if best_score >= FUZZY_THRESHOLD:
            merged.at[idx, "entrepreneurship"] = True
            matched_fuzzy += 1

    merged.drop(columns=["_norm"], inplace=True)

    total = merged["entrepreneurship"].sum()
    print(f"  Matched: {matched_exact} exact + {matched_fuzzy} fuzzy = {total} flagged")
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Stanford/Elsevier Top 2% — Business & Management Database Builder")
    print("=" * 60)

    # Step 1: Discover files (xlsx + cached extracts)
    sources = discover_sources(SCRIPT_DIR)
    if not sources:
        print("ERROR: No matching 'Scholars YYYY year/career*.xlsx' files")
        print(f"  and no cached extracts in {CACHE_DIR}")
        return

    print(f"\nFound {len(sources)} source(s):")
    for s in sources:
        status = "cached" if s["cached"] else "xlsx"
        if s["xlsx_path"] and s["cached"]:
            status = "cached (xlsx also present)"
        name = s["xlsx_path"].name if s["xlsx_path"] else f"{s['type']}_{s['year']}_bm.csv"
        print(f"  {name}  (year={s['year']}, type={s['type']}, {status})")

    # Step 2: Extract/load B&M scholars from each source
    print("\nExtracting Business & Management scholars...")
    dfs = []
    for s in sources:
        df = load_or_extract(s)
        dfs.append(df)

    # Step 3: Merge
    print("\nMerging into single database...")
    merged, fuzzy_log = merge_all(dfs)

    # Step 3b: Save fuzzy match review file
    if fuzzy_log:
        review_path = SCRIPT_DIR / "fuzzy_matches_review.csv"
        pd.DataFrame(fuzzy_log).to_csv(review_path, index=False)
        print(f"\nFuzzy match review file: {review_path}")
        print(f"  {len(fuzzy_log)} fuzzy matches to review")
    else:
        print("\nNo fuzzy matching needed (single file or all exact matches).")

    # Step 3c: Flag entrepreneurship scholars
    merged = flag_entrepreneurship(merged)

    # Step 4: Save output
    out_xlsx = SCRIPT_DIR / "bm_scholars_database.xlsx"
    out_csv = SCRIPT_DIR / "bm_scholars_database.csv"

    print(f"\nSaving to {out_xlsx.name} ...")
    merged.to_excel(out_xlsx, index=False, freeze_panes=(1, 0))
    print(f"Saving to {out_csv.name} ...")
    merged.to_csv(out_csv, index=False)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total scholars: {len(merged)}")
    print(f"Total columns:  {len(merged.columns)}")
    if "entrepreneurship" in merged.columns:
        ent_count = merged["entrepreneurship"].sum()
        print(f"Entrepreneurship scholars: {ent_count} of {len(merged)}")

    # Show which year/type combos are present
    metric_prefixes = set()
    for c in merged.columns:
        m = re.match(r"(year|career)_(\d{4})_", c)
        if m:
            metric_prefixes.add(f"{m.group(1)}_{m.group(2)}")
    if metric_prefixes:
        print(f"Year/type combos: {', '.join(sorted(metric_prefixes))}")

    # Show sample
    print(f"\nTop 5 scholars:")
    display_cols = ["scholar_id", "authfull", "inst_name", "cntry"]
    print(merged[display_cols].head().to_string(index=False))
    print("\nDone!")


if __name__ == "__main__":
    main()
