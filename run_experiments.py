"""
Runs all 9 conditions without the app and saves the results (for the report).
Usage:  python run_experiments.py            (30 runs per condition, base seed 1000)
        python run_experiments.py 50 2000    (50 runs, base seed 2000)
Creates results_runs.csv and results_summary.csv in this folder.
"""
import sys

import pandas as pd

from experiments import run_all_conditions, summarize

runs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
base_seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1000

df, _ = run_all_conditions(runs, base_seed)
summary = summarize(df)
df.to_csv("results_runs.csv", index=False)
summary.to_csv("results_summary.csv", index=False)

print(f"{runs} runs per condition, seeds {base_seed}-{base_seed + runs - 1}\n")
cols = ["Total infections", "Total deaths", "Peak infectious", "Peak infection day", "Outbreak duration (days)", "Final susceptible"]
table = pd.DataFrame({"Condition": summary["Condition"], "Pathway": summary["Pathway"], "Intervention": summary["Intervention"]})
for c in cols:
    table[c] = [f"{m:.1f} ± {s:.1f}" for m, s in zip(summary[f"{c} mean"], summary[f"{c} SD"])]
pd.set_option("display.width", 250)
print(table.to_string(index=False))
