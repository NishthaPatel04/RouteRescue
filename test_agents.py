"""Validation tests for the RouteRescue agents.  Run:  python -m pytest -q"""
from agents import check_route, run_pipeline, to_min
from data import SCENARIOS


def all_shown(state):
    shown = [state["recommendation"]] + state["backups"] if state["recommendation"] else []
    return [r for r in shown if r]


def test_every_shown_route_passes_hard_rules():
    for s in SCENARIOS.values():
        state = run_pipeline(s)
        for r in all_shown(state):
            hard, _ = check_route(r, state)
            assert hard == [], (s["disruption"], r["label"], hard)


def test_cancelled_service_never_recommended():
    state = run_pipeline(SCENARIOS["A: Simple cancellation"])
    for r in all_shown(state):
        assert all(l["service_id"] != "12127" for l in r["legs"])


def test_budget_respected():
    s = SCENARIOS["B: Tight budget"]
    state = run_pipeline(s)
    assert all(r["cost"] <= s["budget"] for r in all_shown(state))


def test_missed_connection_detected():
    state = run_pipeline(SCENARIOS["C: Missed connection"])
    notes = " ".join(" ".join(r["violations"]) for r in state["rejected"])
    assert "connection at Lonavala" in notes


def test_no_compliant_route_reported_honestly():
    s = SCENARIOS["D: No compliant route"]
    state = run_pipeline(s)
    assert state["status"] == "none" and state["recommendation"] is None
    assert state["retries"] >= 1
    assert all(r["legs"][-1]["arr_min"] > to_min(s["deadline"]) for r in state["closest"])
