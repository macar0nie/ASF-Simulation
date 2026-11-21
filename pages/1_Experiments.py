"""
Experiments page: the 3 x 3 design (9 conditions x N runs), summary table, charts and CSV export.
"""

import altair as alt
import pandas as pd
import streamlit as st

from asf_model import PATHWAYS, TIMINGS, Settings
from experiments import CONDITIONS, INDICATORS, run_all_conditions, summarize
from style import apply_style, header

st.set_page_config(page_title="ASF Experiments", page_icon="🧪", layout="wide")
apply_style()
header(
    "Experiments: 3 transmission pathways × 3 intervention timings",
    "9 conditions (D1–V3) · every condition uses the same population, initial infections, disease timing and random seeds",
)

defaults = Settings()
conditions_table = pd.DataFrame(
    [
        {
            "Condition": f"{p[0].upper()}{i + 1}",
            "Transmission pathway": PATHWAYS[p],
            "Intervention timing": {"none": "No intervention", "early": f"Early (day {defaults.early_day})", "late": f"Late (day {defaults.late_day})"}[t],
        }
        for p in PATHWAYS
        for i, t in enumerate(TIMINGS)
    ]
)
with st.expander("Experimental conditions and fixed settings", expanded=False):
    st.dataframe(conditions_table, hide_index=True, use_container_width=True)
    st.markdown(
        f"Fixed for all conditions: {defaults.num_pigs} pigs in {defaults.num_pens} pens, {defaults.initial_infectious} infectious pigs in Pen 1 on day 0, "
        f"{defaults.days} days, intervention effectiveness e = {defaults.effectiveness}, routine carcass removal after 3 days. "
        "Run *r* uses seed = base seed + *r* in every condition."
    )

c1, c2, c3 = st.columns([1, 1, 2])
runs = c1.number_input("Runs per condition", 5, 100, 30, step=5)
base_seed = c2.number_input("Base seed", 0, 1_000_000, 1000, step=1)
c3.markdown(f'<p class="small-note" style="margin-top:2rem">{9 * int(runs)} simulation runs in total (about 30–60 seconds).</p>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_experiment(runs, base_seed):
    bar = st.progress(0.0, text="Running simulations...")
    done = [0]
    total = runs * len(CONDITIONS)

    def tick():
        done[0] += 1
        bar.progress(done[0] / total, text=f"Running simulations... {done[0]}/{total}")

    df, curves = run_all_conditions(runs, base_seed, on_progress=tick)
    bar.empty()
    return df, curves


if st.button("▶  Run all 9 conditions", type="primary"):
    st.session_state.experiment = cached_experiment(int(runs), int(base_seed))

if "experiment" not in st.session_state:
    st.info("Press **Run all 9 conditions** to run the full experiment.")
    st.stop()

runs_df, curves = st.session_state.experiment
summary = summarize(runs_df)

# ---- Table VI format ---------------------------------------------------------
st.subheader("Results summary (mean ± standard deviation)")
fmt = lambda m, sd: f"{m:.1f} ± {sd:.1f}"
table6 = pd.DataFrame(
    {
        "Condition": summary["Condition"],
        "Pathway": summary["Pathway"],
        "Intervention": summary["Intervention"],
        "Infections": [fmt(m, s) for m, s in zip(summary["Total infections mean"], summary["Total infections SD"])],
        "Infection %": [fmt(m, s) for m, s in zip(summary["Infection percentage (%) mean"], summary["Infection percentage (%) SD"])],
        "Deaths": [fmt(m, s) for m, s in zip(summary["Total deaths mean"], summary["Total deaths SD"])],
        "Peak infectious": [fmt(m, s) for m, s in zip(summary["Peak infectious mean"], summary["Peak infectious SD"])],
        "Peak day": [fmt(m, s) for m, s in zip(summary["Peak infection day mean"], summary["Peak infection day SD"])],
        "Outbreak duration": [fmt(m, s) for m, s in zip(summary["Outbreak duration (days) mean"], summary["Outbreak duration (days) SD"])],
        "Final susceptible": [fmt(m, s) for m, s in zip(summary["Final susceptible mean"], summary["Final susceptible SD"])],
    }
)
st.dataframe(table6, hide_index=True, use_container_width=True)
st.caption(f"{int(summary['Runs'].iloc[0])} runs per condition, seeds {int(runs_df['seed'].min())}–{int(runs_df['seed'].max())}. "
           "Outbreak duration = last day on which any pig was exposed or infectious.")

timing_order = list(TIMINGS.values())
timing_colors = alt.Scale(domain=timing_order, range=["#dc2626", "#16a34a", "#f59e0b"])

# ---- Grouped bars --------------------------------------------------------------
st.subheader("Effect of intervention timing within each pathway")
means = summary[["Condition", "Pathway", "Intervention", "Total infections mean", "Total deaths mean"]].rename(
    columns={"Total infections mean": "Infections", "Total deaths mean": "Deaths"}
)
c1, c2 = st.columns(2)
for col, metric in ((c1, "Infections"), (c2, "Deaths")):
    bars = alt.Chart(means).mark_bar().encode(
        x=alt.X("Intervention:N", sort=timing_order, title=None, axis=alt.Axis(labels=False, ticks=False)),
        y=alt.Y(f"{metric}:Q", title=f"Mean {metric.lower()}"),
        color=alt.Color("Intervention:N", scale=timing_colors, sort=timing_order, legend=alt.Legend(orient="bottom", title=None)),
        column=alt.Column("Pathway:N", sort=list(PATHWAYS.values()), title=None),
        tooltip=["Condition", "Pathway", "Intervention", alt.Tooltip(f"{metric}:Q", format=".1f")],
    ).properties(width=120, height=260, title=f"Mean {metric.lower()} per condition")
    col.altair_chart(bars)

# ---- Curves per pathway ------------------------------------------------------------
st.subheader("Average number of infectious pigs over time")
rows = []
for code, curve in curves.items():
    pathway = {"D": "Direct", "I": "Indirect", "V": "Vector-borne"}[code[0]]
    timing = timing_order[int(code[1]) - 1]
    rows += [{"day": d, "Infectious": v, "Pathway": pathway, "Intervention": timing} for d, v in enumerate(curve)]
curve_df = pd.DataFrame(rows)
lines = alt.Chart(curve_df).mark_line(strokeWidth=2.5).encode(
    x=alt.X("day:Q", title="Simulation day"),
    y=alt.Y("Infectious:Q", title="Mean infectious pigs"),
    color=alt.Color("Intervention:N", scale=timing_colors, sort=timing_order, legend=alt.Legend(orient="bottom", title=None)),
).properties(width=290, height=250).facet(column=alt.Column("Pathway:N", sort=list(PATHWAYS.values()), title=None))
st.altair_chart(lines)

# ---- Variation -------------------------------------------------------------------
st.subheader("Variation between runs (total infections per run)")
box = alt.Chart(runs_df.rename(columns={"timing": "Intervention", "pathway": "Pathway", "total_infected": "Total infections"})).mark_boxplot(extent="min-max", size=28).encode(
    x=alt.X("condition:N", title="Condition", sort=[r["Condition"] for _, r in conditions_table.iterrows()]),
    y=alt.Y("Total infections:Q"),
    color=alt.Color("Intervention:N", scale=timing_colors, sort=timing_order, legend=alt.Legend(orient="bottom", title=None)),
).properties(height=300)
st.altair_chart(box, use_container_width=True)

# ---- Data and downloads ---------------------------------------------------------
st.subheader("Recorded data")
st.dataframe(runs_df, hide_index=True, use_container_width=True, height=260)
c1, c2, c3 = st.columns(3)
c1.download_button("Download all runs (CSV)", runs_df.to_csv(index=False), "asf_experiment_runs.csv", "text/csv", use_container_width=True)
c2.download_button("Download summary table (CSV)", table6.to_csv(index=False), "asf_experiment_summary.csv", "text/csv", use_container_width=True)
c3.download_button("Download full statistics (CSV)", summary.to_csv(index=False), "asf_experiment_statistics.csv", "text/csv", use_container_width=True)
