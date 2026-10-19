"""RouteRescue agents and orchestration.

Five agents share one state dict and run as a small state machine:
Planner -> Research -> Executor -> Critic --(retry)--> Research ... -> Explainer.
The Critic's conditional edge back to Research is the decision point.

The same graph can be expressed in LangGraph (see build_langgraph at the bottom);
the plain-Python runner is used by default so the demo has no hard dependencies.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from copy import deepcopy

from data import LEGS

MIN_TRANSFER_MIN = 10      # minimum connection time between legs
LONG_WAIT_MIN = 60         # soft warning threshold
MAX_RETRIES = 2
TARGET_VALID = 3           # recommended + 2 backups

WEIGHTS = {
    "Balanced": {"time": 0.25, "cost": 0.25, "transfers": 0.25, "convenience": 0.25},
    "Fastest": {"time": 0.5, "cost": 0.15, "transfers": 0.2, "convenience": 0.15},
    "Cheapest": {"time": 0.15, "cost": 0.5, "transfers": 0.2, "convenience": 0.15},
    "Fewest transfers": {"time": 0.2, "cost": 0.15, "transfers": 0.5, "convenience": 0.15},
}


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def log(state, agent, msg, kind="info"):
    state["trace"].append({"agent": agent, "message": msg, "kind": kind})


# ---------------------------------------------------------------- Planner
def planner_agent(state):
    """Turn the form + free-text disruption into a structured request and constraint set."""
    req = state["request"]
    text = req.get("disruption", "")
    blocked, delays, closures = set(), {}, set()

    known_ids = {leg["service_id"] for leg in LEGS}
    for sid in known_ids:
        if re.search(rf"\b{re.escape(sid)}\b", text, re.I):
            m = re.search(rf"{re.escape(sid)}.*?delay\w*\s*(?:by\s*)?(\d+)", text, re.I)
            if m:
                delays[sid] = int(m.group(1))
            else:
                blocked.add(sid)
    if re.search(r"expressway|road closure|highway closed", text, re.I):
        closures.add("expressway")

    constraints = {
        "blocked_services": sorted(blocked),
        "delays_min": delays,
        "closures": sorted(closures),
        "budget": req["budget"],
        "deadline": req.get("deadline"),
        "start": req["start"],
    }
    state["constraints"] = constraints
    state["weights"] = WEIGHTS[req["priority"]]
    state["search"] = {"max_transfers": 1}
    state["plan"] = ["parse disruption", "search alternatives", "score and rank",
                     "validate against constraints", "explain recommendation"]

    parts = []
    if blocked:
        parts.append(f"blocked {', '.join(sorted(blocked))}")
    if delays:
        parts.append("delayed " + ", ".join(f"{k} +{v} min" for k, v in delays.items()))
    if closures:
        parts.append("expressway closed")
    if not parts:
        parts.append("no known service matched; searching all options")
    log(state, "Planner", f"Disruption parsed: {'; '.join(parts)}.")
    log(state, "Planner",
        f"Constraints: budget Rs {req['budget']}, depart after {req['start']}"
        + (f", arrive by {req['deadline']}" if req.get("deadline") else "")
        + f". Priority '{req['priority']}' -> weights {state['weights']}.")
    return state


# ---------------------------------------------------------------- Research
def _effective_leg(leg, delays):
    leg = dict(leg)
    d = delays.get(leg["service_id"], 0)
    leg["dep_min"] = to_min(leg["depart"]) + d
    leg["arr_min"] = to_min(leg["arrive"]) + d
    leg["delay"] = d
    leg["source"] = "SIMULATED"
    return leg


def research_agent(state):
    """Search the synthetic network for paths that avoid the disruption."""
    req, c = state["request"], state["constraints"]
    max_t = state["search"]["max_transfers"]
    start = to_min(c["start"])

    usable = []
    for leg in LEGS:
        if leg["service_id"] in c["blocked_services"]:
            continue
        if "expressway" in c["closures"] and leg["road"]:
            continue
        usable.append(_effective_leg(leg, c["delays_min"]))

    routes = []

    def dfs(city, t_ready, path):
        if city == req["destination"] and path:
            routes.append(path)
            return
        if len(path) > max_t:
            return
        for leg in usable:
            if leg["from"] != city or leg["dep_min"] < t_ready:
                continue
            if any(p["to"] == leg["to"] or p["from"] == leg["to"] for p in path):
                continue  # no loops
            dfs(leg["to"], leg["arr_min"], path + [leg])

    dfs(req["origin"], start, [])
    state["candidates"] = routes
    log(state, "Research",
        f"Found {len(routes)} candidate route(s) from {req['origin']} to {req['destination']} "
        f"with up to {max_t} transfer(s), excluding disrupted services.")
    return state


# ---------------------------------------------------------------- Executor
def executor_agent(state):
    """Compute metrics, normalise, and rank by weighted score (lower is better)."""
    req, w = state["request"], state["weights"]
    start = to_min(state["constraints"]["start"])
    scored = []
    for legs in state["candidates"]:
        total_time = legs[-1]["arr_min"] - start
        cost = sum(l["fare"] for l in legs)
        transfers = len(legs) - 1
        waits = [legs[i + 1]["dep_min"] - legs[i]["arr_min"] for i in range(transfers)]
        mode_match = (1.0 if req["mode"] == "any"
                      else sum(l["mode"] == req["mode"] for l in legs) / len(legs))
        wait_penalty = min(1.0, sum(waits) / 120) if waits else 0.0
        convenience = round(0.7 * mode_match + 0.3 * (1 - wait_penalty), 2)
        scored.append({
            "legs": legs, "total_min": total_time, "cost": cost, "transfers": transfers,
            "waits": waits, "convenience": convenience,
            "label": " -> ".join(f"{l['name']}" for l in legs),
        })

    def norm(vals):
        lo, hi = min(vals), max(vals)
        return [0.0 if hi == lo else (v - lo) / (hi - lo) for v in vals]

    if scored:
        nt = norm([r["total_min"] for r in scored])
        nc = norm([r["cost"] for r in scored])
        nx = norm([r["transfers"] for r in scored])
        for r, a, b, x in zip(scored, nt, nc, nx):
            r["score"] = round(w["time"] * a + w["cost"] * b + w["transfers"] * x
                               + w["convenience"] * (1 - r["convenience"]), 3)
    scored.sort(key=lambda r: r["score"])
    state["ranked"] = scored
    if scored:
        log(state, "Executor",
            f"Scored {len(scored)} route(s). Top by score: {scored[0]['label']} "
            f"(score {scored[0]['score']}).")
    else:
        log(state, "Executor", "Nothing to score.", "warn")
    return state


# ---------------------------------------------------------------- Critic
def check_route(route, state):
    """Return (hard_violations, soft_warnings) for one route."""
    c, req = state["constraints"], state["request"]
    hard, soft = [], []
    legs = route["legs"]
    if any(l["service_id"] in c["blocked_services"] for l in legs):
        hard.append("uses a cancelled service")
    if "expressway" in c["closures"] and any(l["road"] for l in legs):
        hard.append("uses the closed expressway")
    if route["cost"] > c["budget"]:
        hard.append(f"over budget (Rs {route['cost']} > Rs {c['budget']})")
    if c.get("deadline") and legs[-1]["arr_min"] > to_min(c["deadline"]):
        hard.append(f"arrives {to_hhmm(legs[-1]['arr_min'])}, after deadline {c['deadline']}")
    if legs[0]["dep_min"] < to_min(c["start"]):
        hard.append("departs before the passenger is ready")
    for i, wgap in enumerate(route["waits"]):
        if wgap < MIN_TRANSFER_MIN:
            hard.append(f"connection at {legs[i]['to']} is only {wgap} min (< {MIN_TRANSFER_MIN})")
    if legs[0]["from"] != req["origin"] or legs[-1]["to"] != req["destination"]:
        hard.append("route does not connect origin to destination")
    for a, b in zip(legs, legs[1:]):
        if a["to"] != b["from"]:
            hard.append("legs are not continuous")
    if any(l.get("source") not in ("SIMULATED", "LIVE") for l in legs):
        hard.append("missing data-source tag")
    if req["mode"] != "any" and not any(l["mode"] == req["mode"] for l in legs):
        soft.append(f"does not use preferred mode ({req['mode']})")
    if any(wg > LONG_WAIT_MIN for wg in route["waits"]):
        soft.append("has a wait over 60 min")
    return hard, soft


def critic_agent(state):
    valid, rejected = [], []
    for r in state["ranked"]:
        hard, soft = check_route(r, state)
        r["violations"], r["warnings"] = hard, soft
        (rejected if hard else valid).append(r)
    state["valid"], state["rejected"] = valid, rejected
    for r in rejected[:5]:
        log(state, "Critic", f"Rejected '{r['label']}': {'; '.join(r['violations'])}.", "reject")
    log(state, "Critic", f"{len(valid)} route(s) pass all hard rules; {len(rejected)} rejected.",
        "ok" if len(valid) >= TARGET_VALID else "warn")

    n_now = len(state["candidates"])
    no_progress = state["retries"] > 0 and n_now <= state.get("prev_candidates", -1)
    state["prev_candidates"] = n_now

    if len(valid) >= TARGET_VALID:
        state["decision"] = "accept"
    elif no_progress:
        state["decision"] = "accept"
        log(state, "Critic", "Relaxed search found no new routes; stopping early and reporting honestly.", "warn")
    elif state["retries"] < MAX_RETRIES:
        state["retries"] += 1
        state["search"]["max_transfers"] += 1
        state["decision"] = "retry"
        log(state, "Critic",
            f"Fewer than {TARGET_VALID} valid routes. Sending Research back with relaxed search "
            f"(max transfers -> {state['search']['max_transfers']}). Retry {state['retries']}/{MAX_RETRIES}.",
            "warn")
    else:
        state["decision"] = "accept"
        log(state, "Critic", "Retry limit reached. Reporting best available result honestly.", "warn")
    return state


# ---------------------------------------------------------------- Explainer
def _ollama_explain(prompt, model="llama3"):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    reqst = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(reqst, timeout=20) as resp:
        return json.loads(resp.read())["response"].strip()


def _numbers_consistent(text, route):
    """Critic-style check: every Rs amount in LLM text must match the computed fare."""
    amounts = {int(x) for x in re.findall(r"(?:Rs\.?|₹|INR)\s?(\d+)", text)}
    return amounts <= {route["cost"]} | {l["fare"] for l in route["legs"]}


def explainer_agent(state):
    req = state["request"]
    valid = state["valid"]
    if valid:
        best = valid[0]
        others = valid[1:3]
        reason = (f"Recommended '{best['label']}' because it has the best weighted score "
                  f"({best['score']}) for priority '{req['priority']}': arrives "
                  f"{to_hhmm(best['legs'][-1]['arr_min'])}, costs Rs {best['cost']}, "
                  f"{best['transfers']} transfer(s), and passes every hard check.")
        if others:
            reason += " Backups: " + "; ".join(
                f"{o['label']} (arr {to_hhmm(o['legs'][-1]['arr_min'])}, Rs {o['cost']})" for o in others) + "."
        if best["warnings"]:
            reason += " Note: " + "; ".join(best["warnings"]) + "."
        state["status"] = "ok" if len(valid) >= TARGET_VALID else "partial"
    else:
        best, others = None, []
        closest = sorted(state["rejected"], key=lambda r: (len(r["violations"]), r["score"]))[:3]
        state["closest"] = closest
        reason = ("No route satisfies all constraints. Showing the closest options with their "
                  "violations so the passenger can decide (for example, accept a later arrival).")
        state["status"] = "none"

    state["explanation_source"] = "template"
    if state.get("use_llm") and best:
        try:
            prompt = ("Explain in 3 sentences to a passenger why this travel option was chosen. "
                      f"Use only these facts: {reason}")
            text = _ollama_explain(prompt)
            if _numbers_consistent(text, best):
                reason = text
                state["explanation_source"] = "Ollama (verified)"
            else:
                log(state, "Critic", "LLM explanation contained numbers not in the route; using template.", "reject")
        except Exception:
            log(state, "Explainer", "Ollama not reachable; using mock/template explanation.", "warn")

    state["recommendation"], state["backups"], state["explanation"] = best, others, reason
    log(state, "Explainer", "Recovery plan ready." if best else "Reported that no compliant route exists.",
        "ok" if best else "warn")
    return state


# ---------------------------------------------------------------- Orchestrator
def run_pipeline(request: dict, use_llm: bool = False) -> dict:
    state = {"request": deepcopy(request), "trace": [], "retries": 0, "use_llm": use_llm}
    t0 = time.perf_counter()
    planner_agent(state)
    while True:
        research_agent(state)
        executor_agent(state)
        critic_agent(state)
        if state["decision"] == "accept":
            break
    explainer_agent(state)
    state["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return state


def build_langgraph():
    """Optional: the same workflow as a LangGraph StateGraph (pip install langgraph)."""
    from typing import TypedDict
    from langgraph.graph import StateGraph, END

    class S(TypedDict, total=False):
        request: dict

    g = StateGraph(dict)
    g.add_node("planner", planner_agent)
    g.add_node("research", research_agent)
    g.add_node("executor", executor_agent)
    g.add_node("critic", critic_agent)
    g.add_node("explainer", explainer_agent)
    g.set_entry_point("planner")
    g.add_edge("planner", "research")
    g.add_edge("research", "executor")
    g.add_edge("executor", "critic")
    g.add_conditional_edges("critic", lambda s: s["decision"],
                            {"retry": "research", "accept": "explainer"})
    g.add_edge("explainer", END)
    return g.compile()
