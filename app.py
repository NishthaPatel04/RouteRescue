"""RouteRescue - Streamlit PoC.

Run:  pip install streamlit pandas
      streamlit run app.py
"""
import pandas as pd
import streamlit as st

from agents import TARGET_VALID, WEIGHTS, run_pipeline, to_hhmm
from data import CITIES, LEGS, SCENARIOS

st.set_page_config(page_title="RouteRescue", page_icon="🚆", layout="wide")

AGENT_ICON = {"Planner": "🧭", "Research": "🔎", "Executor": "⚙️", "Critic": "🛡️", "Explainer": "💬"}
KIND_STYLE = {"reject": "❌", "warn": "⚠️", "ok": "✅", "info": "•"}
MODES = ["any", "train", "bus", "metro", "cab"]

# ---------------------------------------------------------------- Sidebar: input
st.sidebar.title("🚆 RouteRescue")
st.sidebar.caption("Agentic travel-disruption recovery · PoC on SIMULATED data")

preset_name = st.sidebar.selectbox("Demo scenario", ["Custom"] + list(SCENARIOS), index=1)
p = SCENARIOS.get(preset_name, SCENARIOS["A: Simple cancellation"])

with st.sidebar.form("trip"):
    origin = st.selectbox("Origin", CITIES, index=CITIES.index(p["origin"]))
    destination = st.selectbox("Destination", CITIES, index=CITIES.index(p["destination"]))
    start = st.text_input("Ready to depart at (HH:MM)", p["start"])
    use_deadline = st.checkbox("Must arrive by a deadline", value=bool(p["deadline"]))
    deadline = st.text_input("Latest arrival (HH:MM)", p["deadline"] or "12:00")
    budget = st.number_input("Budget (Rs)", min_value=0, value=int(p["budget"]), step=50)
    mode = st.selectbox("Preferred mode", MODES, index=MODES.index(p["mode"]))
    priority = st.selectbox("Priority", list(WEIGHTS), index=list(WEIGHTS).index(p["priority"]))
    disruption = st.text_area("Describe the disruption", p["disruption"], height=80,
                              help="e.g. 'Train 12127 cancelled', 'LOC-PL1 delayed by 30 min', 'expressway closed'")
    use_llm = st.checkbox("Use local LLM via Ollama for the explanation", value=False,
                          help="Falls back to the mock/template explainer if Ollama is not running.")
    submitted = st.form_submit_button("Find recovery plan", type="primary", width="stretch")

with st.sidebar.expander("Known services (synthetic timetable)"):
    st.dataframe(pd.DataFrame(LEGS)[["service_id", "name", "mode", "from", "to", "depart", "arrive", "fare"]],
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------- Main
st.title("RouteRescue")
st.caption("Five cooperating agents turn a disrupted journey into a ranked, validated recovery plan.")


def valid_hhmm(s):
    try:
        h, m = s.split(":")
        return 0 <= int(h) < 24 and 0 <= int(m) < 60
    except Exception:
        return False


if not submitted and "result" not in st.session_state:
    st.info("Pick a demo scenario or fill in the form, then press **Find recovery plan**.")
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, (a, d) in zip([c1, c2, c3, c4, c5], [
        ("🧭 Planner", "Parses the request and disruption; sets constraints and weights"),
        ("🔎 Research", "Finds alternative routes that avoid the disruption"),
        ("⚙️ Executor", "Computes time, cost, transfers, convenience; ranks"),
        ("🛡️ Critic", "Rejects infeasible routes; triggers a relaxed retry"),
        ("💬 Explainer", "Recommended route, backups, itinerary, reasons"),
    ]):
        col.markdown(f"**{a}**  \n{d}")
    st.stop()

if submitted:
    errors = []
    if origin == destination:
        errors.append("Origin and destination must differ.")
    if not valid_hhmm(start) or (use_deadline and not valid_hhmm(deadline)):
        errors.append("Times must be HH:MM.")
    if errors:
        for e in errors:
            st.error(e)
        st.stop()
    request = {"origin": origin, "destination": destination, "start": start,
               "deadline": deadline if use_deadline else None, "budget": int(budget),
               "mode": mode, "priority": priority, "disruption": disruption}
    st.session_state["result"] = run_pipeline(request, use_llm=use_llm)

state = st.session_state["result"]
req = state["request"]

# Summary metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Candidates examined", len(state["ranked"]))
m2.metric("Passed validation", len(state["valid"]))
m3.metric("Critic retries", state["retries"])
m4.metric("Response time", f"{state['elapsed_ms']} ms")

tab_plan, tab_trace, tab_compare = st.tabs(["Recovery plan", "Agent trace", "All options"])


def route_card(route, title, highlight=False):
    legs = route["legs"]
    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.markdown(f"**{route['label']}**  ·  `SIMULATED`")
        a, b, c, d = st.columns(4)
        a.metric("Arrives", to_hhmm(legs[-1]["arr_min"]))
        b.metric("Cost", f"Rs {route['cost']}")
        c.metric("Transfers", route["transfers"])
        d.metric("Score", route["score"])
        for w in route.get("warnings", []):
            st.caption(f"⚠️ {w}")
        for v in route.get("violations", []):
            st.caption(f"❌ {v}")


with tab_plan:
    if state["status"] == "none":
        st.error("No route meets every constraint. Closest options are shown with their violations.")
        for i, r in enumerate(state.get("closest", []), 1):
            route_card(r, f"Closest option {i}")
    else:
        if state["status"] == "partial":
            st.warning(f"Only {len(state['valid'])} route(s) passed validation (target {TARGET_VALID}).")
        best = state["recommendation"]
        route_card(best, "✅ Recommended route", highlight=True)

        st.markdown("##### Itinerary")
        rows = []
        for i, l in enumerate(best["legs"]):
            rows.append({"Step": i + 1, "Service": f"{l['name']} ({l['service_id']})", "Mode": l["mode"],
                         "From": l["from"], "Depart": to_hhmm(l["dep_min"]), "To": l["to"],
                         "Arrive": to_hhmm(l["arr_min"]), "Fare (Rs)": l["fare"],
                         "Delay": f"+{l['delay']} min" if l["delay"] else "", "Data": l["source"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        st.markdown("##### Why this route")
        st.write(state["explanation"])
        st.caption(f"Explanation source: {state['explanation_source']}")

        if state["backups"]:
            st.markdown("##### Backup options")
            cols = st.columns(len(state["backups"]))
            for col, (i, r) in zip(cols, enumerate(state["backups"], 1)):
                with col:
                    route_card(r, f"Backup {i}")

with tab_trace:
    st.caption("Each step is an agent action or hand-off. ❌ = Critic rejection, ⚠️ = retry or warning.")
    for t in state["trace"]:
        st.markdown(f"{AGENT_ICON.get(t['agent'], '•')} **{t['agent']}** {KIND_STYLE[t['kind']]} {t['message']}")
    with st.expander("Planner output (structured constraints)"):
        st.json({"plan": state["plan"], "constraints": state["constraints"], "weights": state["weights"]})

with tab_compare:
    rows = []
    for r in state["ranked"]:
        rows.append({"Route": r["label"], "Arrives": to_hhmm(r["legs"][-1]["arr_min"]),
                     "Travel time (min)": r["total_min"], "Cost (Rs)": r["cost"],
                     "Transfers": r["transfers"], "Convenience": r["convenience"], "Score": r["score"],
                     "Valid": "✅" if not r["violations"] else "❌",
                     "Critic notes": "; ".join(r["violations"] + r["warnings"]), "Data": "SIMULATED"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Score: weighted sum of normalised time, cost, transfers and (1 - convenience); lower is better.")

st.divider()
st.caption("All timetable, fare and disruption data in this demo is SIMULATED. Live data would be tagged LIVE.")
