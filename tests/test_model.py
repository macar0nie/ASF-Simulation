"""
Verification tests (they follow the verification list in the report, Section II-F).
Run with:  python -m pytest -q
"""
import math
from dataclasses import replace

import pytest

from asf_model import (ALLOWED_TRANSITIONS, MARGIN, ROUTINE_CARCASS_DELAY, D, E, I, R, S, Settings, Simulation,
                       infection_probability, run_simulation)

BASE = Settings(days=40)
PATHWAYS = ["direct", "indirect", "vector"]


# 1. Correct population and number of infectious pigs
@pytest.mark.parametrize("k", [1, 2, 5])
def test_initial_population_and_infections(k):
    sim = Simulation(replace(BASE, initial_infectious=k))
    assert len(sim.pigs) == BASE.num_pigs
    infectious = [p for p in sim.pigs if p.state == I]
    assert len(infectious) == k and all(p.pen == 0 for p in infectious)
    assert sum(p.state == S for p in sim.pigs) == BASE.num_pigs - k


# 2. Only the selected transmission pathway is active
@pytest.mark.parametrize("pathway", PATHWAYS)
def test_only_selected_pathway_is_active(pathway):
    sim = Simulation(replace(BASE, pathway=pathway))
    sim.run()
    routes = {p.route for p in sim.pigs if p.route and p.route != "initial"}
    assert routes == {pathway}
    if pathway != "indirect":
        assert all(c == 0 for c in sim.contamination)
    if pathway != "vector":
        assert all(t == 0 for t in sim.tick_infection)


def test_inactive_pathway_coefficients_have_no_effect():
    """Changing the coefficient of a pathway that is NOT selected changes nothing."""
    a = run_simulation(replace(BASE, pathway="direct", indirect_coefficient=0.0, vector_coefficient=0.0))
    b = run_simulation(replace(BASE, pathway="direct", indirect_coefficient=0.01, vector_coefficient=2.0))
    assert a.daily == b.daily


# 3. Disease state transitions follow the model
@pytest.mark.parametrize("pathway", PATHWAYS)
def test_only_allowed_state_changes(pathway):
    result = run_simulation(replace(BASE, pathway=pathway, timing="early", recovery_prob=0.3))
    for before, after in zip(result.states, result.states[1:]):
        for a, b in zip(before.upper(), after.upper()):
            assert a == b or b in ALLOWED_TRANSITIONS[a], f"{a} -> {b}"


# 4. Probabilities stay within valid limits
def test_probability_is_between_0_and_1():
    for hazard in (-5, 0, 0.001, 0.5, 1, 10, 1000, float("nan")):
        assert 0 <= infection_probability(hazard) <= 1
    assert infection_probability(0) == 0
    assert math.isclose(infection_probability(1), 1 - math.exp(-1))


# 5. Early and late interventions begin on their assigned days
@pytest.mark.parametrize("timing,start", [("early", 3), ("late", 15)])
def test_intervention_starts_on_assigned_day(timing, start):
    result = run_simulation(replace(BASE, timing=timing))
    for d in result.daily:
        assert d["intervention_active"] == (d["day"] >= start)


def test_no_intervention_is_never_active():
    assert not any(d["intervention_active"] for d in run_simulation(BASE).daily)


# 6. The intervention reduces the active hazard by (1 - e)
@pytest.mark.parametrize("pathway", PATHWAYS)
def test_intervention_reduces_hazard(pathway):
    sim = Simulation(replace(BASE, pathway=pathway, timing="late", effectiveness=0.8))
    for _ in range(14):
        sim.step()
    pig = next(p for p in sim.pigs if p.state == S and p.pen == 0)
    sim.contamination[0], sim.tick_infection[0] = 10.0, 0.5
    contacts = {pig.id: 3}
    before = sim.hazard(pig, contacts)  # day 14: not active yet
    sim.day = 15
    after = sim.hazard(pig, contacts)  # day 15: active
    assert before > 0 and math.isclose(after, before * 0.2)


# 7. Infection and mortality totals match the recorded history
@pytest.mark.parametrize("pathway", PATHWAYS)
def test_totals_match_history(pathway):
    result = run_simulation(replace(BASE, pathway=pathway))
    for d in result.daily:
        assert d["S"] + d["E"] + d["I"] + d["V"] + d["D"] + d["R"] == BASE.num_pigs
    last = result.daily[-1]
    assert result.summary["total_infected"] == BASE.num_pigs - last["S"]
    assert result.summary["total_deaths"] == last["D"] + last["R"]
    assert result.summary["peak_infectious"] == max(d["I"] for d in result.daily)


# 8. Same settings and seed give the same numbers
def test_same_seed_same_result():
    a = run_simulation(replace(BASE, seed=7, pathway="vector"))
    b = run_simulation(replace(BASE, seed=7, pathway="vector"))
    c = run_simulation(replace(BASE, seed=8, pathway="vector"))
    assert a.daily == b.daily and a.frames == b.frames
    assert a.daily != c.daily


# Zero-transmission test
@pytest.mark.parametrize("pathway", PATHWAYS)
def test_zero_transmission(pathway):
    result = run_simulation(replace(BASE, pathway=pathway, direct_coefficient=0, indirect_coefficient=0, vector_coefficient=0))
    assert result.summary["total_infected"] == BASE.initial_infectious


# Model-specific rules
def test_pigs_stay_inside_pens():
    result = run_simulation(replace(BASE, movement_speed=3, timing="early"))
    areas = result.pens + [result.isolation_pen]
    for day_frames in result.frames:
        for frame in day_frames:
            for k in range(0, len(frame), 2):
                x, z = frame[k], frame[k + 1]
                assert any(a["min_x"] + MARGIN - 0.01 <= x <= a["max_x"] - MARGIN + 0.01 and
                           a["min_z"] + MARGIN - 0.01 <= z <= a["max_z"] - MARGIN + 0.01 for a in areas)


def test_isolated_pigs_have_no_contacts():
    sim = Simulation(replace(BASE, initial_infectious=1))
    healthy = next(p for p in sim.pigs if p.state == S and p.pen == 0)
    sick = next(p for p in sim.pigs if p.state == I)
    sick.x, sick.z = healthy.x, healthy.z
    contacts = {}
    sim.count_contacts(contacts)
    assert contacts.get(healthy.id) == 1
    sick.isolated = True
    contacts = {}
    sim.count_contacts(contacts)
    assert healthy.id not in contacts


def test_ticks_stay_infected():
    """Vector pathway: the share of infected ticks in a pen never goes down."""
    sim = Simulation(replace(BASE, pathway="vector", timing="early"))
    previous = sim.tick_infection[:]
    for _ in range(BASE.days):
        sim.step()
        assert all(now >= before for now, before in zip(sim.tick_infection, previous))
        previous = sim.tick_infection[:]


def test_routine_carcass_removal_without_intervention():
    """No intervention still removes carcasses after the routine delay (normal farm practice)."""
    sim = Simulation(replace(BASE, days=60))
    sim.run()
    for p in sim.pigs:
        if p.state == D:
            assert sim.day - p.day_dead < ROUTINE_CARCASS_DELAY


def test_recovery_probability():
    long = replace(BASE, days=80)
    assert run_simulation(replace(long, recovery_prob=0.0)).summary["total_survived"] == 0
    assert run_simulation(replace(long, recovery_prob=1.0)).summary["total_deaths"] == 0


def test_early_intervention_reduces_infections_on_average():
    """Behaviour check over 10 matched seeds (direct pathway)."""
    none = [run_simulation(replace(BASE, seed=s)).summary["total_infected"] for s in range(10)]
    early = [run_simulation(replace(BASE, seed=s, timing="early")).summary["total_infected"] for s in range(10)]
    assert sum(early) < sum(none)
