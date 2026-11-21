# ASF Simulation: African Swine Fever Transmission in a Pig Farm

A Streamlit web app that simulates how African Swine Fever (ASF) spreads among individual pigs in a hypothetical 6-pen farm through **three transmission pathways** (direct, indirect, vector-borne) under **three intervention timings** (none, early on day 3, late on day 15). You choose a condition and press **Start**, and a 3D farm replays the run day by day. Every run is listed in a run recorder. A second page runs all 9 conditions 30 times each and compares them.

> Educational model with simplified assumptions. It does not predict real outbreaks. ASF does not infect humans.

## Files

| File | What it contains |
|---|---|
| `asf_model.py` | **The simulation model**: pigs, pens, movement, infection, disease states. Pure Python, no UI. |
| `ASF_Simulation.py` | Main Streamlit page: condition and inputs, Start / Stop, 3D playback, results, run recorder |
| `pages/1_Experiments.py` | Experiments page: 9 conditions × 30 runs, summary table, charts, CSV downloads |
| `experiments.py` | The 9 conditions, repeated runs, mean / SD / min / max |
| `style.py` | Shared page styling |
| `viewer.py` | Builds the 3D farm (Three.js). It only replays results; it does not compute anything. |
| `run_experiments.py` | Runs all 9 conditions without the app and saves `results_runs.csv` and `results_summary.csv` |
| `tests/test_model.py` | 30 verification tests (pytest), following the report's verification list |
| `static/three/` | The Three.js library files (MIT licence), so the 3D view works without a CDN |
| `.streamlit/config.toml` | Turns on static file serving (needed for the 3D view) |
| `requirements.txt` | Python packages: `streamlit`, `pandas` |

## Run it on your computer (Windows)

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/. In the installer, tick **"Add python.exe to PATH"**.
2. Open the project folder in VS Code and open a terminal (*Terminal → New Terminal*).
3. Install the packages (one time):
   ```powershell
   pip install -r requirements.txt
   ```
4. Start the app:
   ```powershell
   streamlit run ASF_Simulation.py
   ```
   Your browser opens at http://localhost:8501. Press `Ctrl + C` in the terminal to stop the app.

Other commands:
```powershell
python -m pytest -q          # run the 30 tests
python run_experiments.py    # 9 conditions x 30 runs -> results_runs.csv, results_summary.csv
```

## Put it online (free standalone link): Streamlit Community Cloud

1. Create a GitHub account and a **new repository** (e.g., `asf-simulation`).
2. Upload **all** files and folders of this project to it, including the hidden `.streamlit` folder and the `static` folder. With GitHub Desktop or `git push` the hidden folder is included automatically. With *Add file → Upload files* on the website, drag the whole project folder in.
3. Go to https://share.streamlit.io and sign in with GitHub.
4. Click **Create app** → *Deploy a public app from GitHub* and choose:
   - Repository: your repository
   - Branch: `main`
   - Main file path: **`ASF_Simulation.py`**
   - App URL: choose a name, e.g. `asf-simulation` → `https://asf-simulation.streamlit.app`
5. Click **Deploy**. The first build takes a few minutes. After that, the link works for anyone, with no login needed.

Free apps go to sleep after a period without visitors. The first visit then shows a "wake up" button and takes a short moment, so open your link a few minutes before your demo or defense.

**Backup host:** the same code also runs on Hugging Face Spaces (choose the Streamlit template).

## How to use the app

1. **Sidebar → Experimental condition.** Choose the **transmission pathway** (Direct / Indirect / Vector-borne) and the **intervention timing** (None / Early day 3 / Late day 15). Adjust any other input if you want.
2. Press **▶ Start simulation**. Python runs the whole simulation with those inputs (about one second).
3. The **3D farm** replays the run day by day. The title bar shows the condition code (e.g., *V3*). Use **Pause**, **Stop** (back to day 0) and the speed menu in its top-left corner. Drag to rotate, right-drag to pan, scroll to zoom. A banner shows when the intervention starts.
4. **Results of this run** shows the main indicators and a chart with the intervention day marked.
5. The **Run recorder** at the bottom lists every run you start (condition, settings, seed and results). Download it as CSV with *Download recorder*.
6. **⏹ Stop / reset view** clears the 3D view; **Restore default values** resets the inputs.
7. The **Experiments** page (left menu) runs all 9 conditions × 30 runs and shows the summary table, charts and CSV downloads.

Inputs sit inside a form, so changing a slider does **nothing** until you press Start.

## How the model works (short version)

- **Agents:** 120 pigs in 6 pens (8 m × 6 m), each with a position and a disease state. Pigs walk to random points in their pen (6 movement steps per day) and never cross fences. Workers move about 6 pigs per week between pens.
- **States:** **S**usceptible → **E**xposed (3–6 days) → **I**nfectious (5–9 days) → **D**ead (carcass stays in the pen) → **R**emoved (carcass taken out after 3 days, normal farm practice). With the *recovery probability* (default 5%), an infectious pig survives instead (**V**, Survived).
- **Start:** 2 infectious pigs in Pen 1 on day 0.
- **Infection probability per day** for a susceptible pig: **P = 1 − exp(−λ)**, where λ comes from the **selected pathway only**:
  - **Direct:** λ = direct coefficient × number of close contacts (within 1 m) with infectious pen-mates that day.
  - **Indirect:** λ = indirect coefficient × contamination of the pig's pen. Each infectious pig or carcass adds 1 unit per day, 20% fades away daily, and workers carry 10% of the other pens' average contamination into each pen.
  - **Vector-borne (hypothetical soft ticks):** λ = vector coefficient × share of infected ticks in the pen. Ticks get infected by feeding on infectious pigs (share infected grows by 0.3 × share of infectious pigs × share of uninfected ticks per day) and **stay infected**. Ticks stay in their pen.
- **Intervention** (from day 3 or day 15): **λ × (1 − e)** with e = 0.8, plus pathway-specific actions:
  - Direct: sick pigs are isolated 2 days after they become infectious, and transfers between pens stop.
  - Indirect: workers carry (1 − e) as much contamination, and carcasses are removed after 1 day.
  - Vector-borne: tick control (acaricide), so only the λ reduction applies.
- **Randomness:** all random numbers come from one generator seeded with the *random seed*. The same seed and inputs always give the same run.

## The experiment (3 × 3 design)

| | No intervention | Early (day 3) | Late (day 15) |
|---|---|---|---|
| **Direct** | D1 | D2 | D3 |
| **Indirect** | I1 | I2 | I3 |
| **Vector-borne** | V1 | V2 | V3 |

All conditions use 120 pigs, 6 pens, 2 infectious pigs in Pen 1, 60 days, e = 0.8, and seeds 1000–1029 (30 runs each, 270 runs in total). The three transmission coefficients were chosen so that the three *no-intervention* outbreaks have a similar average size (about 84–87 pigs), which makes the timing comparison fair. This does **not** mean the pathways are equally dangerous on real farms.

## Limitations

The farm is hypothetical, and the parameter values are simplified assumptions, not measurements. The vector-borne pathway represents a hypothetical farm where competent soft ticks (*Ornithodoros*) are present; this should not be assumed for Philippine farms. Ticks stay infected for the whole run and do not die or reproduce. Contamination is a relative index, not a viral load. Survived pigs are assumed not to spread the virus. Detection always happens exactly after the detection delay. Feed, water, vehicles, wild boar and spread between farms are not modelled.

## Credits

Built with Python, [Streamlit](https://streamlit.io), [pandas](https://pandas.pydata.org) and [Three.js](https://threejs.org) (MIT licence, included in `static/three/`). Disease background: World Organisation for Animal Health (WOAH), *African swine fever*.
