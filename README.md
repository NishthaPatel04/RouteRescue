# RouteRescue — Agentic travel-disruption recovery (PoC)

Five cooperating agents turn a disrupted journey into a ranked, validated recovery plan.
All transport data is **SIMULATED** (synthetic Pune–Mumbai–Nashik network in `data.py`).

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Optional: `python -m pytest -q` runs the validation tests.
Optional: start Ollama (`ollama run llama3`) and tick "Use local LLM" for an LLM-written explanation;
the Critic checks its numbers, and the app falls back to the template explainer if Ollama is not running.

## Agents (agents.py)

| Agent | Job |
| --- | --- |
| Planner | Parses form + free-text disruption → blocked services, delays, closures, budget, deadline, scoring weights |
| Research | Searches the network for paths that avoid the disruption (applies delays) |
| Executor | Computes time, cost, transfers, convenience; normalises; ranks by weighted score |
| Critic | Hard rules: no cancelled/closed service, within budget, meets deadline, transfer ≥ 10 min, continuity, data-source tag. If < 3 routes pass → relaxed retry (max 2); stops early if no new routes |
| Explainer | Recommended route, 2 backups, itinerary, reasons; or honest "no compliant route" with closest options |

Flow: Planner → Research → Executor → Critic → (retry → Research) → Explainer.
`build_langgraph()` shows the same graph as a LangGraph StateGraph (optional).

## Demo scenarios

| Scenario | What it shows |
| --- | --- |
| A: Simple cancellation | 12127 cancelled → Deccan Queen recommended, cab rejected (budget), tight connections rejected |
| B: Tight budget | Rs 200 budget → most options rejected, Critic retries, partial result flagged |
| C: Missed connection | Local delayed 30 min → 0-min connection at Lonavala rejected |
| D: No compliant route | Cancellation + expressway closed + 10:00 deadline → no route; closest options shown with violations |
