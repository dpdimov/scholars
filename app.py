import streamlit as st
import pandas as pd
import plotly.express as px
import re

st.set_page_config(page_title="B&M Scholars Database", layout="wide")

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]
TYPES = ["career", "year"]
METRICS = ["rank", "rank_ns", "h", "h_ns", "nc", "nc_ns", "c", "c_ns",
           "npciting", "npciting_ns", "np60", "self_pct",
           "rank_subfield", "rank_subfield_ns", "subfield_count"]


@st.cache_data
def load_data():
    df = pd.read_csv("bm_scholars_database.csv")
    if "entrepreneurship" in df.columns:
        df["entrepreneurship"] = df["entrepreneurship"].astype(str).str.strip().str.lower() == "true"
    else:
        df["entrepreneurship"] = False
    return df


def col_name(typ, year, metric):
    return f"{typ}_{year}_{metric}"


def get_year_type_options():
    return [f"{t} {y}" for y in YEARS for t in TYPES]


def parse_year_type(label):
    parts = label.split()
    return parts[0], int(parts[1])


df = load_data()

# ── Sidebar filters ──
st.sidebar.title("Filters")

countries = sorted(df["cntry"].dropna().unique())
sel_countries = st.sidebar.multiselect("Country", countries)

entre_only = st.sidebar.checkbox("Entrepreneurship scholars only")

name_search = st.sidebar.text_input("Search name")

# Apply filters
mask = pd.Series(True, index=df.index)
if sel_countries:
    mask &= df["cntry"].isin(sel_countries)
if entre_only:
    mask &= df["entrepreneurship"]
if name_search:
    mask &= df["authfull"].str.contains(name_search, case=False, na=False)

filtered = df[mask]

st.sidebar.markdown(f"**{len(filtered):,}** / {len(df):,} scholars")

st.sidebar.divider()
st.sidebar.markdown(
    "**Data source:** Ioannidis, John P.A. (2025), "
    '"August 2025 data-update for "Updated science-wide author databases of '
    'standardized citation indicators"", Elsevier Data Repository, V8, '
    "doi: [10.17632/btchxktzyw.8](https://doi.org/10.17632/btchxktzyw.8)",
    unsafe_allow_html=False,
)
st.sidebar.markdown("**Created by:** Dimo Dimov")
st.sidebar.markdown(
    "**License:** [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)"
)

# ── Tabs ──
tab1, tab2, tab3, tab4 = st.tabs(["Scholar Table", "Visualizations", "Scholar Profile", "Institution Comparison"])

# ═══════════════════════════════════════════
# Tab 1: Scholar Table
# ═══════════════════════════════════════════
with tab1:
    st.header("Scholar Table")
    yt = st.selectbox("Year + Type", get_year_type_options(), index=get_year_type_options().index("career 2024"), key="tab1_yt")
    typ, yr = parse_year_type(yt)

    display_cols = {
        "authfull": "Name",
        "inst_name": "Institution",
        "cntry": "Country",
        "entrepreneurship": "Entrepreneurship",
        col_name(typ, yr, "rank"): "Rank",
        col_name(typ, yr, "h"): "H-index",
        col_name(typ, yr, "nc"): "Citations",
        col_name(typ, yr, "c"): "Composite (C)",
    }
    existing = {k: v for k, v in display_cols.items() if k in filtered.columns}
    view = filtered[list(existing.keys())].rename(columns=existing)
    view = view.sort_values("Rank", na_position="last")

    st.dataframe(view.reset_index(drop=True), use_container_width=True, height=600)

    csv_bytes = view.to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered CSV", csv_bytes, "scholars_filtered.csv", "text/csv")

# ═══════════════════════════════════════════
# Tab 2: Visualizations
# ═══════════════════════════════════════════
with tab2:
    st.header("Visualizations")

    # Country distribution
    st.subheader("Top-20 Countries by Scholar Count")
    country_counts = filtered["cntry"].value_counts().head(20).sort_values()
    fig_country = px.bar(x=country_counts.values, y=country_counts.index,
                         orientation="h", labels={"x": "Count", "y": "Country"})
    fig_country.update_layout(height=500)
    st.plotly_chart(fig_country, use_container_width=True)

    # Top-N scholars by selected metric
    st.subheader("Top-N Scholars by Metric")
    c1, c2, c3 = st.columns(3)
    with c1:
        yt2 = st.selectbox("Year + Type", get_year_type_options(),
                           index=get_year_type_options().index("career 2024"), key="tab2_yt")
    with c2:
        metric_choice = st.selectbox("Metric", ["c", "h", "nc", "npciting", "np60"], key="tab2_metric")
    with c3:
        top_n = st.slider("N", 5, 50, 20, key="tab2_n")

    typ2, yr2 = parse_year_type(yt2)
    metric_col = col_name(typ2, yr2, metric_choice)
    if metric_col in filtered.columns:
        topn = filtered.dropna(subset=[metric_col]).nlargest(top_n, metric_col)
        fig_topn = px.bar(topn, x=metric_col, y="authfull", orientation="h",
                          labels={metric_col: metric_choice, "authfull": "Scholar"})
        fig_topn.update_layout(yaxis=dict(autorange="reversed"), height=max(400, top_n * 22))
        st.plotly_chart(fig_topn, use_container_width=True)

    # Entrepreneurship breakdown
    st.subheader("Entrepreneurship Breakdown")
    entre_counts = filtered["entrepreneurship"].value_counts().rename({True: "Entrepreneurship", False: "Non-Entrepreneurship"})
    c4, c5 = st.columns(2)
    with c4:
        st.metric("Entrepreneurship", int(entre_counts.get("Entrepreneurship", 0)))
        st.metric("Non-Entrepreneurship", int(entre_counts.get("Non-Entrepreneurship", 0)))
    with c5:
        rank_col = col_name("career", 2024, "rank")
        if rank_col in filtered.columns:
            avg = filtered.groupby("entrepreneurship")[rank_col].mean()
            st.metric("Avg Rank (Entrepreneurship)", f"{avg.get(True, float('nan')):.0f}")
            st.metric("Avg Rank (Non-Entrepreneurship)", f"{avg.get(False, float('nan')):.0f}")

    # Rank distribution
    st.subheader("Rank Distribution")
    yt3 = st.selectbox("Year + Type", get_year_type_options(),
                       index=get_year_type_options().index("career 2024"), key="tab2_hist_yt")
    typ3, yr3 = parse_year_type(yt3)
    rank_hist_col = col_name(typ3, yr3, "rank")
    if rank_hist_col in filtered.columns:
        fig_hist = px.histogram(filtered.dropna(subset=[rank_hist_col]), x=rank_hist_col, nbins=50,
                                labels={rank_hist_col: "Rank"})
        st.plotly_chart(fig_hist, use_container_width=True)

    # Top institutions by average rank
    st.subheader("Top-20 Institutions by Average Rank")
    yt_inst = st.selectbox("Year + Type", get_year_type_options(),
                           index=get_year_type_options().index("career 2024"), key="tab2_inst_yt")
    typ_inst, yr_inst = parse_year_type(yt_inst)
    rank_inst_col = col_name(typ_inst, yr_inst, "rank")
    if rank_inst_col in filtered.columns:
        inst_avg = (filtered.dropna(subset=[rank_inst_col])
                    .groupby("inst_name")[rank_inst_col].mean()
                    .nsmallest(20).sort_values(ascending=True))
        fig_inst = px.bar(x=inst_avg.values, y=inst_avg.index, orientation="h",
                          labels={"x": "Avg Rank", "y": "Institution"})
        fig_inst.update_layout(height=500)
        st.plotly_chart(fig_inst, use_container_width=True)

# ═══════════════════════════════════════════
# Tab 3: Scholar Profile
# ═══════════════════════════════════════════
with tab3:
    st.header("Scholar Profile")
    names = sorted(filtered["authfull"].dropna().unique())
    if not names:
        st.warning("No scholars match the current filters.")
    else:
        chosen = st.selectbox("Select scholar", names, key="profile_name")
        scholar = df[df["authfull"] == chosen].iloc[0]

        # Stable info
        c6, c7, c8, c9 = st.columns(4)
        c6.metric("Institution", scholar["inst_name"])
        c7.metric("Country", scholar["cntry"])
        c8.metric("First Year", int(scholar["firstyr"]) if pd.notna(scholar["firstyr"]) else "N/A")
        c9.metric("Entrepreneurship", "Yes" if scholar["entrepreneurship"] else "No")

        # Build metrics table across years
        rows = []
        for yr in YEARS:
            for typ in TYPES:
                row = {"Type": typ, "Year": yr}
                for m in ["rank", "h", "nc", "c", "npciting", "np60", "self_pct",
                           "rank_subfield", "subfield_count"]:
                    c_name = col_name(typ, yr, m)
                    row[m] = scholar.get(c_name, None)
                rows.append(row)
        metrics_df = pd.DataFrame(rows)
        st.subheader("Metrics Across Years")
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

        # Rank trend chart
        st.subheader("Rank Trend")
        trend_rows = []
        for yr in YEARS:
            for typ in TYPES:
                rc = col_name(typ, yr, "rank")
                val = scholar.get(rc, None)
                if pd.notna(val):
                    trend_rows.append({"Year": yr, "Type": typ, "Rank": val})
        if trend_rows:
            trend_df = pd.DataFrame(trend_rows)
            fig_trend = px.line(trend_df, x="Year", y="Rank", color="Type", markers=True)
            fig_trend.update_yaxes(autorange="reversed")
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("No rank data available for this scholar.")

# ═══════════════════════════════════════════
# Tab 4: Institution Comparison
# ═══════════════════════════════════════════
with tab4:
    st.header("Institution Comparison")

    if "inst_groups" not in st.session_state:
        st.session_state["inst_groups"] = {}

    institutions = sorted(filtered["inst_name"].dropna().unique())

    # ── Group builder ──
    with st.expander("Create Institution Group"):
        with st.form("tab4_grp_form", clear_on_submit=True):
            grp_name = st.text_input("Group name")
            grp_members = st.multiselect("Select institutions for group", institutions)
            submitted = st.form_submit_button("Add Group")
            if submitted:
                if not grp_name.strip():
                    st.warning("Group name cannot be empty.")
                elif len(grp_members) < 2:
                    st.warning("Select at least 2 institutions for a group.")
                else:
                    st.session_state["inst_groups"][grp_name.strip()] = grp_members
                    st.rerun()

    if st.session_state["inst_groups"]:
        st.markdown("**Existing groups:**")
        for gname, gmembers in list(st.session_state["inst_groups"].items()):
            cols = st.columns([4, 1])
            cols[0].write(f"**{gname}**: {', '.join(gmembers)}")
            if cols[1].button("Remove", key=f"tab4_rm_{gname}"):
                del st.session_state["inst_groups"][gname]
                st.rerun()

    # ── Comparison selector (individuals + groups) ──
    group_options = [f"[Group] {g}" for g in st.session_state["inst_groups"]]
    all_options = group_options + institutions
    sel_items = st.multiselect("Select institutions / groups to compare (2+)", all_options, key="tab4_insts")

    # Resolve selections to {display_label -> list[inst_name]}
    entities: dict[str, list[str]] = {}
    for item in sel_items:
        if item.startswith("[Group] "):
            gname = item[len("[Group] "):]
            entities[item] = st.session_state["inst_groups"][gname]
        else:
            entities[item] = [item]

    yt4 = st.selectbox("Year + Type", get_year_type_options(),
                       index=get_year_type_options().index("career 2024"), key="tab4_yt")
    typ4, yr4 = parse_year_type(yt4)

    rank4 = col_name(typ4, yr4, "rank")
    h4 = col_name(typ4, yr4, "h")
    nc4 = col_name(typ4, yr4, "nc")
    c4_col = col_name(typ4, yr4, "c")

    if len(entities) < 2:
        st.info("Select at least 2 institutions or groups to compare.")
    else:
        all_inst_names = [n for names in entities.values() for n in names]
        inst_df = filtered[filtered["inst_name"].isin(all_inst_names)]

        # ── Summary table ──
        st.subheader("Summary Comparison")
        summary_rows = []
        for label, inst_names in entities.items():
            sub = inst_df[inst_df["inst_name"].isin(inst_names)]
            row = {"Institution": label, "Scholar Count": len(sub)}
            if rank4 in sub.columns:
                row["Avg Rank"] = sub[rank4].mean()
                row["Median Rank"] = sub[rank4].median()
            if h4 in sub.columns:
                row["Avg H-index"] = sub[h4].mean()
            if nc4 in sub.columns:
                row["Avg Citations"] = sub[nc4].mean()
            if c4_col in sub.columns:
                row["Avg Composite (C)"] = sub[c4_col].mean()
            row["Entrepreneurship %"] = (sub["entrepreneurship"].sum() / len(sub) * 100) if len(sub) > 0 else 0
            summary_rows.append(row)
        summary = pd.DataFrame(summary_rows)
        st.dataframe(summary, use_container_width=True, hide_index=True)

        # ── Grouped bar chart ──
        st.subheader("Metric Comparison")
        bar_data = []
        for label, inst_names in entities.items():
            sub = inst_df[inst_df["inst_name"].isin(inst_names)]
            for m_label, col in [("Avg Rank", rank4), ("Avg H-index", h4), ("Avg Citations", nc4)]:
                if col in sub.columns:
                    bar_data.append({"Institution": label, "Metric": m_label, "Value": sub[col].mean()})
        if bar_data:
            bar_df = pd.DataFrame(bar_data)
            fig_bar = px.bar(bar_df, x="Metric", y="Value", color="Institution", barmode="group")
            st.plotly_chart(fig_bar, use_container_width=True)

        # ── Box plot ──
        st.subheader("Metric Distribution")
        metric_map = {"Rank": rank4, "H-index": h4, "Citations": nc4, "Composite (C)": c4_col}
        box_metric = st.selectbox("Metric for box plot", list(metric_map.keys()), key="tab4_box")
        box_col = metric_map[box_metric]
        if box_col in inst_df.columns:
            box_frames = []
            for label, inst_names in entities.items():
                sub = inst_df[inst_df["inst_name"].isin(inst_names)].dropna(subset=[box_col]).copy()
                sub["_group_label"] = label
                box_frames.append(sub)
            if box_frames:
                box_data = pd.concat(box_frames, ignore_index=True)
                fig_box = px.box(box_data, x="_group_label", y=box_col,
                                 labels={"_group_label": "Institution", box_col: box_metric})
                st.plotly_chart(fig_box, use_container_width=True)

        # ── Top scholars per institution/group ──
        st.subheader("Top Scholars per Institution")
        for label, inst_names in entities.items():
            sub = inst_df[inst_df["inst_name"].isin(inst_names)]
            if rank4 in sub.columns:
                top5 = sub.dropna(subset=[rank4]).nsmallest(5, rank4)
            else:
                top5 = sub.head(5)
            with st.expander(f"{label} — Top 5"):
                display = top5[["authfull", "inst_name", "cntry", "entrepreneurship"]].copy()
                display.columns = ["Name", "Institution", "Country", "Entrepreneurship"]
                for m_label, m_col in [("Rank", rank4), ("H-index", h4), ("Citations", nc4), ("Composite (C)", c4_col)]:
                    if m_col in top5.columns:
                        display[m_label] = top5[m_col].values
                st.dataframe(display, use_container_width=True, hide_index=True)
