"""
THE WEB APP (Streamlit)
=======================
In plain words: the screen you use. Pick a scenario on the left, click "Run all agents",
and see every agent's advice, their reasoning, and a side-by-side comparison.

Streamlit UI - Cloud Resource and Cost Optimization Advisor.

    cd cloud_advisor
    streamlit run app.py
"""
import json

import pandas as pd
import streamlit as st

from scenarios import SCENARIOS
from agents import run_all
from agents.common import monthly_cost
from agents.evaluation import fixed_at_peak, peak_sample
from agents.learning_agent import ACTIONS, EXPERIENCE_PATH, load_experience, reset_experience
from agents.llm_agent import DEFAULT_MODEL, DEFAULT_URL

st.set_page_config(page_title="Cloud Cost Optimization Advisor", layout="wide")

# ---- Left-hand panel: choose the scenario and settings ----
with st.sidebar:
    st.header("View")
    view = st.radio("Show", ["All scenarios on one page", "One scenario in detail"],
                    help="All scenarios: A, B and C side by side. One scenario: full detail for each agent.")
    st.header("Scenario")
    sid = st.selectbox("Select scenario", list(SCENARIOS),
                       format_func=lambda k: f"{SCENARIOS[k]['name']} ({SCENARIOS[k]['type']})")
    st.header("LLM agent")
    use_llm = st.checkbox("Run LLM agent (Ollama)", value=True)
    llm_model = st.text_input("Ollama model", DEFAULT_MODEL)
    llm_url = st.text_input("Ollama URL", DEFAULT_URL)
    st.header("Utility weights")
    w_perf = st.slider("Performance", 0.0, 1.0, 0.4, 0.05)
    w_av = st.slider("Availability", 0.0, 1.0, 0.3, 0.05)
    w_cost = st.slider("Cost", 0.0, 1.0, 0.3, 0.05)
    st.header("Learning agent")
    epsilon = st.slider("Exploration (epsilon)", 0.0, 0.5, 0.0, 0.05)
    learn = st.checkbox("Update experience after run", value=True)
    run_clicked = st.button("Run all agents" if view.startswith("One") else "Run all agents on A, B and C",
                            type="primary", use_container_width=True)
    if st.button("Reset experience to seed", use_container_width=True):
        reset_experience(EXPERIENCE_PATH)
        st.success("Experience reset.")

SETTINGS = dict(weights={"performance": w_perf, "availability": w_av, "cost": w_cost},
                epsilon=epsilon, learn=learn, include_llm=use_llm, llm_model=llm_model, llm_url=llm_url)


def tick(v):
    return "✅" if v else "❌"


# =====================================================================
# VIEW 1 - ALL THREE SCENARIOS ON ONE PAGE
# =====================================================================
if view.startswith("All"):
    st.title("Cloud Resource and Cost Optimization Advisor")
    st.caption("Advisory only: analyses simulated metrics and recommends configurations. No cloud resources are changed.")

    # ---- the three situations side by side ----
    st.header("The three scenarios")
    cols = st.columns(len(SCENARIOS))
    for col, (k, sc) in zip(cols, SCENARIOS.items()):
        with col:
            pk_ = peak_sample(sc)
            st.subheader(sc["name"])
            st.caption(f"Type: {sc['type']}")
            st.markdown(f"**Now:** {sc['count']} x {sc['instance_type']} - ${monthly_cost(sc['instance_type'], sc['count'])}/month  \n"
                        f"**Peak response:** {pk_['response_ms']} ms (target {sc['targets']['response_ms']} ms)  \n"
                        f"**Availability:** {sc['current_availability_pct']}% (SLA {sc['targets']['availability_pct']}%)")
            st.line_chart(pd.DataFrame(sc["history"]).set_index("hour")[["cpu", "mem"]], height=180)

    if run_clicked:
        for k, sc in SCENARIOS.items():
            with st.spinner(f"Running all agents on {sc['name']}..." + (" (the LLM takes a few minutes)" if use_llm else "")):
                st.session_state[f"res_{k}"] = run_all(sc, **SETTINGS)

    done = {k: st.session_state.get(f"res_{k}") for k in SCENARIOS}
    if not any(done.values()):
        st.info("Click **Run all agents on A, B and C** in the sidebar. Tip: untick the LLM for an instant result.")
        st.stop()
    missing = [k for k, v in done.items() if not v]
    if missing:
        st.warning(f"Not run yet: scenario(s) {', '.join(missing)}. Click the Run button to include them.")

    # ---- one summary table: every agent x every scenario ----
    st.header("All agents across all scenarios")
    st.caption("Each cell: recommended config, monthly cost, and whether it meets every target at the busiest hour. "
               "⚠️ = LLM answer flagged for human review.")
    agents_order = []
    for r in done.values():
        if r:
            agents_order = [row["Agent"] for row in r["comparison"]]
            break
    matrix = []
    for agent in agents_order:
        row = {"Agent": agent}
        for k, r in done.items():
            if not r:
                row[f"Scenario {k}"] = "-"
                continue
            c = next(x for x in r["comparison"] if x["Agent"] == agent)
            row[f"Scenario {k}"] = (f"{c['Config']} - ${c['Cost (USD/mo)']} {tick(c['Meets all targets at peak'])}"
                                    + (" ⚠️" if c.get("Needs human review") else ""))
        matrix.append(row)
    st.dataframe(pd.DataFrame(matrix), use_container_width=True, hide_index=True)

    # ---- cheapest working answer per scenario ----
    st.subheader("Best answer per scenario")
    best_cols = st.columns(len(SCENARIOS))
    for col, (k, r) in zip(best_cols, done.items()):
        with col:
            if not r:
                st.write(f"**{k}:** not run yet")
                continue
            ok = [c for c in r["comparison"] if c["Meets all targets at peak"]]
            if ok:
                b = min(ok, key=lambda c: c["Cost (USD/mo)"])
                st.metric(f"Scenario {k} - cheapest that works", f"${b['Cost (USD/mo)']}/mo", b["Config"], delta_color="off")
                st.caption(f"Found by: {', '.join(c['Agent'] for c in ok if c['Config'] == b['Config'])}")
            else:
                st.metric(f"Scenario {k}", "No agent met every target")

    # ---- per-scenario detail ----
    st.header("Details per scenario")
    for k, r in done.items():
        if not r:
            continue
        with st.expander(f"{SCENARIOS[k]['name']} - comparison table and why the decisions differ", expanded=False):
            st.caption(f"Same input for all agents (fingerprint `{r['fingerprint']}`).")
            st.dataframe(pd.DataFrame(r["comparison"]), use_container_width=True, hide_index=True)
            for line in r["why_different"]:
                st.markdown(f"- {line}")
    st.info("For each agent's full reasoning, tool calls and learning details, switch the sidebar to "
            "**One scenario in detail** - results already run here are reused.")
    st.stop()


# =====================================================================
# VIEW 2 - ONE SCENARIO IN DETAIL
# =====================================================================
s = SCENARIOS[sid]
t = s["targets"]
st.title("Cloud Resource and Cost Optimization Advisor")
st.caption("Advisory only: analyses simulated metrics and recommends configurations. No cloud resources are changed.")

st.subheader(s["name"])
pk = peak_sample(s)
cur_pk = fixed_at_peak(s, s["instance_type"], s["count"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current config", f"{s['count']} x {s['instance_type']}")
c2.metric("Monthly cost", f"${monthly_cost(s['instance_type'], s['count'])}")
c3.metric("Peak response", f"{pk['response_ms']} ms", f"target {t['response_ms']} ms", delta_color="off")
c4.metric("Availability", f"{s['current_availability_pct']}%", f"SLA {t['availability_pct']}%", delta_color="off")

df = pd.DataFrame(s["history"]).set_index("hour")
g1, g2 = st.columns(2)
with g1:
    st.markdown("**CPU and memory (%)**")
    st.line_chart(df[["cpu", "mem"]])
with g2:
    st.markdown("**Response time vs target (ms)**")
    st.line_chart(df[["response_ms"]].assign(target_ms=t["response_ms"]))
with st.expander("Raw scenario input (identical for all six agents)"):
    st.json(s)

if run_clicked:
    with st.spinner("Running agents..." + (" The LLM may take a minute." if use_llm else "")):
        st.session_state[f"res_{sid}"] = run_all(s, **SETTINGS)

res = st.session_state.get(f"res_{sid}")
if not res:
    st.info("Pick a scenario and click **Run all agents** in the sidebar.")
    st.stop()

# ---- Side-by-side comparison of all agents ----
st.header("Comparison across agents")
st.caption(f"All agents received the same input (fingerprint `{res['fingerprint']}`). "
           "'Peak' columns re-check every recommendation at the busiest hour with the same shared model.")
st.dataframe(pd.DataFrame(res["comparison"]), use_container_width=True, hide_index=True)
st.subheader("Why the decisions differ")
for line in res["why_different"]:
    st.markdown(f"- {line}")

# ---- One tab per agent with its full answer ----
st.header("Agent decisions and reasoning")
tabs = st.tabs([o["agent"] for o in res["outputs"]])
for tab, o in zip(tabs, res["outputs"]):
    with tab:
        if o.get("error"):
            st.error(o["error"])
            st.markdown(f"Start Ollama and pull the model (`ollama pull {llm_model}`), then run again.")
            continue
        rec = o["recommendation"]
        a, b, c = st.columns(3)
        a.metric("Action", rec.get("action"))
        cfg = f"{rec.get('count')} x {rec.get('instance_type')}" if rec.get("instance_type") else "-"
        if rec.get("baseline_count"):
            cfg = f"{rec['baseline_count']}->{cfg}"
        b.metric("Recommended", cfg)
        c.metric("Est. cost", f"${rec.get('est_monthly_cost', '-')}/mo")
        st.markdown("**Current-state summary**")
        st.write(o.get("llm_summary") or o["summary"])
        left, right = st.columns(2)
        with left:
            st.markdown("**Reasoning and trade-offs**")
            for x in o["reasoning"] + o.get("trade_offs", []):
                st.markdown(f"- {x}")
        with right:
            st.markdown("**Monitoring plan**")
            for x in o["monitoring_plan"]:
                st.markdown(f"- {x}")
            if o.get("limitation"):
                st.warning(o["limitation"])
        if o["candidates"]:
            st.markdown("**Candidate configurations**")
            keep = ["action", "label", "config", "instance_type", "count", "baseline_count", "cpu_pct", "mem_pct",
                    "response_ms", "availability_pct", "monthly_cost", "utility", "meets_goal",
                    "meets_response_target", "note"]
            cdf = pd.DataFrame(o["candidates"])
            st.dataframe(cdf[[k for k in keep if k in cdf.columns]], use_container_width=True, hide_index=True)
        if "internal_state" in o:
            with st.expander("Internal state"):
                st.json(o["internal_state"])
        if "components" in o:
            st.markdown("**Learning agent components**")
            st.table(pd.DataFrame([{"Component": k, "This run": v} for k, v in o["components"].items()]))
        if "experience_before" in o:
            st.markdown(f"**Experience for situation `{o['situation']}`** (before -> after this run)")
            st.dataframe(pd.DataFrame([{
                "action": a_, "rate before": o["rates_before"][a_],
                "success before": o["experience_before"][a_]["success"],
                "failure before": o["experience_before"][a_]["failure"],
                "success after": o["experience_after"][a_]["success"],
                "failure after": o["experience_after"][a_]["failure"]} for a_ in ACTIONS]),
                use_container_width=True, hide_index=True)
        if o.get("needs_human_review"):
            st.error("Needs human review: the LLM's final answer still has problems after reflection. "
                     "Do not apply it without checking. " + " | ".join(o["unresolved_problems"]))
        elif "grounding" in o:
            st.success("Final review passed: recommendation verified against tool evidence.")
        if "grounding" in o:
            g = o["grounding"]
            (st.success if g["passed"] else st.warning)(
                f"Evidence check {'passed' if g['passed'] else 'failed'}: {g['distinct_tools']} distinct tools, "
                f"{g['numbers_grounded']}/{g['numbers_claimed']} numbers grounded, recommended config evaluated "
                f"with a tool: {g['recommendation_evaluated_with_tool']}.")
            if g["ungrounded_numbers"]:
                st.caption(f"Numbers not found in tool outputs: {g['ungrounded_numbers']}")
            with st.expander(f"Tool calls ({len(o['tool_log'])})"):
                for tc in o["tool_log"]:
                    st.markdown(f"`{tc['name']}({json.dumps(tc['args'])})`")
                    st.code(tc["output"][:1500], language="json")
            with st.expander("Raw LLM answer"):
                st.code(o["raw_answer"])

with st.expander("Learning agent - full experience store"):
    exp = load_experience(EXPERIENCE_PATH)
    st.dataframe(pd.DataFrame([{"situation": k, "action": a_, **v} for k, acts in exp.items()
                               if isinstance(acts, dict) and not k.startswith("_") for a_, v in acts.items()]),
                 use_container_width=True, hide_index=True)
    st.caption(f"{len(exp.get('history', []))} runs recorded since last reset.")
