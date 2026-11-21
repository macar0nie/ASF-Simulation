"""
ASF Simulation - main page.

1. Choose the condition (transmission pathway + intervention timing) and the inputs.
2. Press "Start simulation": Python runs the whole simulation with those inputs.
3. The 3D farm replays the run day by day (Pause / Stop inside the 3D view).
4. Every run is added to the Run recorder table at the bottom (downloadable as CSV).

Run locally with:  streamlit run ASF_Simulation.py
"""

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from asf_model import INTERVENTION_MEASURES, PATHWAYS, TIMINGS, Settings, run_simulation
from style import apply_style, header
from viewer import STATE_COLORS, build_viewer_html

st.set_page_config(page_title="ASF Simulation", page_icon="🐖", layout="wide")
apply_style()

DEFAULTS = Settings()
INPUT_KEYS = [
    "pathway", "timing", "effectiveness", "num_pigs", "initial_infectious", "days", "seed",
    "direct_coefficient", "indirect_coefficient", "vector_coefficient",
    "recovery_prob", "movement_speed", "transfers_per_week", "detection_delay",
]
if "initialised" not in st.session_state:
    for key in INPUT_KEYS:
        st.session_state[key] = getattr(DEFAULTS, key)
    st.session_state.recorder = []
    st.session_state.initialised = True

# ---------------------------------------------------------------------------
# Sidebar: inputs. Everything is inside a form, so NOTHING runs until Start.
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Simulation settings")
    with st.form("inputs"):
        st.markdown("**Experimental condition**")
        st.radio("Transmission pathway", list(PATHWAYS), format_func=PATHWAYS.get, key="pathway", horizontal=True)
        st.radio("Intervention timing", list(TIMINGS), key="timing",
                 format_func=lambda t: {"none": "None", "early": f"Early (day {DEFAULTS.early_day})", "late": f"Late (day {DEFAULTS.late_day})"}[t])
        st.slider("Intervention effectiveness (e)", 0.0, 1.0, step=0.05, key="effectiveness",
                  help="Share of the pathway's infection risk removed once the intervention starts: λ × (1 − e).")

        st.markdown("**Population**")
        st.slider("Number of pigs", 30, 240, step=6, key="num_pigs", help="Spread evenly over 6 pens.")
        st.slider("Initially infectious pigs (Pen 1)", 1, 10, key="initial_infectious")
        st.slider("Simulation length (days)", 20, 120, step=5, key="days")

        st.markdown("**Transmission coefficients** (only the selected pathway's is used)")
        st.slider("Direct (per close contact)", 0.0, 0.5, step=0.01, key="direct_coefficient")
        st.slider("Indirect (per unit of pen contamination)", 0.0, 0.01, step=0.0005, format="%.4f", key="indirect_coefficient")
        st.slider("Vector-borne (per day, all ticks infected)", 0.0, 2.0, step=0.05, key="vector_coefficient")

        st.markdown("**Disease and farm**")
        st.slider("Recovery probability", 0.0, 1.0, step=0.01, key="recovery_prob", help="Chance an infectious pig survives instead of dying.")
        st.slider("Pig movement speed (m/h)", 0.0, 3.0, step=0.1, key="movement_speed")
        st.slider("Pig transfers between pens (per week)", 0.0, 14.0, step=0.5, key="transfers_per_week")
        st.slider("Detection delay for isolation (days)", 0, 7, key="detection_delay", help="Direct pathway only: days an infectious pig goes unnoticed.")
        st.number_input("Random seed", 0, 1_000_000, step=1, key="seed", help="Same seed + same inputs = exactly the same run.")

        started = st.form_submit_button("▶  Start simulation", type="primary", use_container_width=True)

    if st.button("⏹  Stop / reset view", use_container_width=True):
        st.session_state.pop("result", None)
        st.rerun()
    if st.button("Restore default values", use_container_width=True):
        for key in INPUT_KEYS:
            st.session_state[key] = getattr(DEFAULTS, key)
        st.rerun()

# ---------------------------------------------------------------------------
# Run the simulation and record it
# ---------------------------------------------------------------------------
if started:
    settings = Settings(**{key: st.session_state[key] for key in INPUT_KEYS})
    with st.spinner("Running the simulation..."):
        result = run_simulation(settings)
    st.session_state.result = result
    s = result.settings
    st.session_state.recorder.append(
        {
            "Run #": len(st.session_state.recorder) + 1,
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Condition": s["condition"],
            "Pathway": PATHWAYS[s["pathway"]],
            "Intervention": TIMINGS[s["timing"]],
            "Start day": s["intervention_day"] if s["intervention_day"] is not None else "–",
            "Effectiveness": s["effectiveness"],
            "Pigs": s["num_pigs"],
            "Seed": s["seed"],
            "Total infections": result.summary["total_infected"],
            "Infection %": round(result.summary["percent_infected"], 1),
            "Deaths": result.summary["total_deaths"],
            "Survived": result.summary["total_survived"],
            "Peak infectious": result.summary["peak_infectious"],
            "Peak day": result.summary["peak_day"],
            "Outbreak duration (days)": result.summary["outbreak_duration"],
            "Final susceptible": result.summary["final_susceptible"],
        }
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
header(
    "Simulation of African Swine Fever Transmission",
    "Agent-based stochastic model of a hypothetical 6-pen pig farm · 3 transmission pathways × 3 intervention timings · "
    "educational model, not a prediction of real outbreaks",
)

result = st.session_state.get("result")
if result is None:
    st.info("Choose a transmission pathway and intervention timing in the sidebar, adjust the inputs if needed, then press **▶ Start simulation**.")
    c1, c2, c3 = st.columns(3)
    for col, (key, name) in zip((c1, c2, c3), PATHWAYS.items()):
        with col:
            st.markdown(f"#### {name}")
            st.markdown(
                {
                    "direct": "A susceptible pig is infected through close contact (within 1 m) with an infectious pen-mate.",
                    "indirect": "Infectious pigs and carcasses contaminate their pen; workers carry contamination to other pens.",
                    "vector": "Hypothetical soft ticks in each pen get infected by feeding on infectious pigs, stay infected, and infect pigs when they bite.",
                }[key]
            )
            st.caption(f"Intervention: {INTERVENTION_MEASURES[key]}.")
else:
    s = result.settings
    timing_text = TIMINGS[s["timing"]] + (f" from day {s['intervention_day']} (e = {s['effectiveness']:.2f})" if s["intervention_day"] is not None else "")
    st.markdown(
        f'<div class="condition-card"><b class="code">{s["condition"]}</b>{PATHWAYS[s["pathway"]]} transmission · {timing_text} · '
        f'{s["num_pigs"]} pigs · {s["initial_infectious"]} initially infectious · {s["days"]} days · seed {s["seed"]}</div>',
        unsafe_allow_html=True,
    )
    components.html(build_viewer_html(result), height=630)
    st.caption("Drag to rotate · right-drag to pan · scroll to zoom · Pause, Stop and speed are in the top-left of the 3D view.")

    st.subheader("Results of this run")
    sm = result.summary
    c = st.columns(4)
    c[0].metric("Total infections", f"{sm['total_infected']}  ({sm['percent_infected']:.1f}%)")
    c[1].metric("Deaths", sm["total_deaths"])
    c[2].metric("Peak infectious (day)", f"{sm['peak_infectious']}  (day {sm['peak_day']})")
    c[3].metric("Outbreak duration", f"{sm['outbreak_duration']} days")

    daily = pd.DataFrame(result.daily)
    long = daily.rename(columns={"S": "Susceptible", "E": "Exposed", "I": "Infectious", "V": "Survived", "total_dead": "Dead"}).melt(
        "day", ["Susceptible", "Exposed", "Infectious", "Survived", "Dead"], var_name="State", value_name="Pigs"
    )
    color = alt.Scale(domain=["Susceptible", "Exposed", "Infectious", "Survived", "Dead"],
                      range=[STATE_COLORS["S"], STATE_COLORS["E"], STATE_COLORS["I"], STATE_COLORS["V"], STATE_COLORS["D"]])
    chart = alt.Chart(long).mark_line(strokeWidth=2.5).encode(
        x=alt.X("day:Q", title="Simulation day"), y=alt.Y("Pigs:Q", title="Number of pigs"), color=alt.Color("State:N", scale=color)
    )
    layers = [chart]
    if s["intervention_day"] is not None:
        rule = alt.Chart(pd.DataFrame({"day": [s["intervention_day"]]})).mark_rule(strokeDash=[5, 4], color="#16a34a").encode(x="day:Q")
        layers.append(rule)
    st.altair_chart(alt.layer(*layers).properties(height=320, title="Disease states over time (dashed line = intervention start)"), use_container_width=True)

# ---------------------------------------------------------------------------
# Run recorder: every run of this session
# ---------------------------------------------------------------------------
st.subheader("Run recorder")
recorder = st.session_state.recorder
if not recorder:
    st.markdown('<p class="small-note">Each simulation you start is listed here with its condition, settings and results.</p>', unsafe_allow_html=True)
else:
    table = pd.DataFrame(recorder)
    st.dataframe(table, hide_index=True, use_container_width=True)
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("Download recorder (CSV)", table.to_csv(index=False), "asf_run_recorder.csv", "text/csv", use_container_width=True)
    if c2.button("Clear recorder", use_container_width=True):
        st.session_state.recorder = []
        st.rerun()
    st.markdown('<p class="small-note">The recorder keeps the runs of this browser session. Download the CSV to keep them.</p>', unsafe_allow_html=True)
