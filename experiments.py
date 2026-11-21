"""
The 3 x 3 experiment: 3 transmission pathways x 3 intervention timings = 9 conditions
(D1-D3, I1-I3, V1-V3). Every condition uses the same population, initial infections,
disease timing and random seeds; only the pathway and the intervention timing change.
"""

import statistics
from dataclasses import replace

import pandas as pd

from asf_model import PATHWAYS, TIMINGS, Settings, run_simulation

CONDITIONS = [(p, t) for p in PATHWAYS for t in TIMINGS]  # D1, D2, D3, I1, ... V3

INDICATORS = {
    "total_infected": "Total infections",
    "percent_infected": "Infection percentage (%)",
    "total_deaths": "Total deaths",
    "total_survived": "Survived",
    "peak_infectious": "Peak infectious",
    "peak_day": "Peak infection day",
    "outbreak_duration": "Outbreak duration (days)",
    "final_susceptible": "Final susceptible",
}


def condition_settings(pathway, timing, base=None):
    return replace(base or Settings(), pathway=pathway, timing=timing)


def run_condition(pathway, timing, runs=30, base_seed=1000, base=None, on_progress=None):
    """Runs one condition `runs` times. Run r uses seed base_seed + r in EVERY condition."""
    rows, curves = [], []
    for r in range(runs):
        settings = replace(condition_settings(pathway, timing, base), seed=base_seed + r)
        result = run_simulation(settings)
        rows.append(
            {
                "condition": settings.condition,
                "pathway": PATHWAYS[pathway],
                "timing": TIMINGS[timing],
                "run": r + 1,
                "seed": settings.seed,
                **result.summary,
            }
        )
        curves.append([d["I"] for d in result.daily])
        if on_progress:
            on_progress()
    return rows, curves


def run_all_conditions(runs=30, base_seed=1000, base=None, on_progress=None):
    """All 9 conditions. Returns a table with one row per run, and mean infectious curves."""
    all_rows, mean_curves = [], {}
    for pathway, timing in CONDITIONS:
        rows, curves = run_condition(pathway, timing, runs, base_seed, base, on_progress)
        all_rows.extend(rows)
        days = len(curves[0])
        mean_curves[rows[0]["condition"]] = [sum(c[d] for c in curves) / len(curves) for d in range(days)]
    return pd.DataFrame(all_rows), mean_curves


def summarize(df):
    """Mean and standard deviation (plus min and max) of every indicator for every condition."""
    out = []
    for condition, group in df.groupby("condition", sort=False):
        row = {"Condition": condition, "Pathway": group["pathway"].iloc[0], "Intervention": group["timing"].iloc[0], "Runs": len(group)}
        for key, label in INDICATORS.items():
            values = group[key].tolist()
            row[f"{label} mean"] = statistics.mean(values)
            row[f"{label} SD"] = statistics.stdev(values) if len(values) > 1 else 0.0
            row[f"{label} min"] = min(values)
            row[f"{label} max"] = max(values)
        out.append(row)
    return pd.DataFrame(out)
