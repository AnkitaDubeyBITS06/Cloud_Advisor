"""
RUNNING ALL AGENTS TOGETHER
===========================
In plain words: gives the same scenario to all six agents (each gets its own identical copy),
collects their answers, re-checks every recommendation at the busiest hour, and builds the
comparison table plus the "why the decisions differ" explanation.
"""
import copy
import hashlib
import json
from collections import defaultdict

from .simple_reflex import SimpleReflexAgent
from .model_based import ModelBasedReflexAgent
from .goal_based import GoalBasedAgent
from .utility_based import UtilityBasedAgent
from .learning_agent import LearningAgent, EXPERIENCE_PATH
from .evaluation import availability, fixed_at_peak

__all__ = ["SimpleReflexAgent", "ModelBasedReflexAgent", "GoalBasedAgent", "UtilityBasedAgent",
           "LearningAgent", "build_agents", "run_all", "fingerprint"]


def fingerprint(scenario):
    return hashlib.sha256(json.dumps(scenario, sort_keys=True).encode()).hexdigest()[:12]


def build_agents(weights=None, epsilon=0.0, learn=True, experience_path=EXPERIENCE_PATH,
                 include_llm=False, llm_model=None, llm_url=None, chat_model=None):
    agents = [SimpleReflexAgent(), ModelBasedReflexAgent(), GoalBasedAgent(), UtilityBasedAgent(weights),
              LearningAgent(experience_path, epsilon=epsilon, learn=learn)]
    if include_llm:
        from .llm_agent import LLMAgent, DEFAULT_MODEL, DEFAULT_URL
        agents.append(LLMAgent(llm_model or DEFAULT_MODEL, llm_url or DEFAULT_URL, chat_model=chat_model))
    return agents


def peak_check(scenario, rec):
    """Re-score any agent's recommendation at the peak sample with the shared model."""
    if rec.get("instance_type") is None:
        return None
    c = fixed_at_peak(scenario, rec["instance_type"], rec["count"])
    base = rec.get("baseline_count")
    if base:
        c["availability_pct"] = availability(base, c["cpu_pct"])
        c["meets_availability"] = c["availability_pct"] >= scenario["targets"]["availability_pct"]
        c["meets_goal"] = c["meets_response_target"] and c["meets_availability"] and c["memory_ok"]
    c["monthly_cost"] = rec.get("est_monthly_cost", c["monthly_cost"])
    return c


def config_label(rec):
    if rec.get("instance_type") is None:
        return "-"
    if rec.get("baseline_count"):
        return f"{rec['baseline_count']}->{rec['count']} x {rec['instance_type']} (scheduled)"
    return f"{rec['count']} x {rec['instance_type']}"


def comparison_row(scenario, out):
    rec = out["recommendation"]
    pc = peak_check(scenario, rec)
    return {
        "Agent": out["agent"],
        "Action": rec.get("action"),
        "Config": config_label(rec),
        "Cost (USD/mo)": rec.get("est_monthly_cost"),
        "Agent's own est. response (ms)": rec.get("est_response_ms"),
        "Peak response (ms)": pc["response_ms"] if pc else None,
        "Peak CPU (%)": pc["cpu_pct"] if pc else None,
        "Availability (%)": pc["availability_pct"] if pc else None,
        "Meets all targets at peak": pc["meets_goal"] if pc else None,
        "Needs human review": out.get("needs_human_review", False),
    }


WHY = {
    "Simple Reflex": "reacts only to the latest sample (hour {h})",
    "Model-Based Reflex": "reads its internal state over all 24 hours (peak, trough, trend, last action)",
    "Goal-Based": "searches all candidates and takes the cheapest one that reaches every target at peak",
    "Utility-Based": "maximises a weighted score of performance, availability and cost",
    "Learning": "repeats the action with the best past success rate for this kind of situation",
    "LLM (Ollama)": "reasons over the tool evidence it chose to request",
}


def explain_differences(scenario, outputs, rows):
    h = scenario["history"][-1]["hour"]
    by_action = defaultdict(list)
    for o in outputs:
        by_action[o["recommendation"].get("action")].append(o["agent"])
    lines = ["Actions chosen: " + "; ".join(f"{a}: {', '.join(n)}" for a, n in by_action.items()) + "."]
    ok = [r for r in rows if r["Meets all targets at peak"]]
    bad = [r["Agent"] for r in rows if r["Meets all targets at peak"] is False]
    if ok:
        best = min(ok, key=lambda r: r["Cost (USD/mo)"])
        lines.append(f"Meet every target at peak: {', '.join(r['Agent'] for r in ok)}. "
                     f"Cheapest of these: {best['Agent']} ({best['Config']}, ${best['Cost (USD/mo)']}/mo).")
    if bad:
        lines.append(f"Miss at least one target at peak: {', '.join(bad)}.")
    for r in rows:
        own, peak = r["Agent's own est. response (ms)"], r["Peak response (ms)"]
        if own is not None and peak is not None and peak > 1.5 * own:
            lines.append(f"{r['Agent']} estimated {own} ms from an off-peak sample, but at peak it would be {peak} ms.")
    for o in outputs:
        lines.append(f"{o['agent']} {WHY.get(o['agent'], '').format(h=h)} -> {o['recommendation'].get('action')} "
                     f"({config_label(o['recommendation'])}).")
    return lines


def run_all(scenario, **kwargs):
    fp = fingerprint(scenario)
    outputs = []
    for agent in build_agents(**kwargs):
        s = copy.deepcopy(scenario)                # identical, isolated input for every agent
        outputs.append(agent.decide(s))
        assert fingerprint(s) == fp, f"{agent.name} modified its input"
    rows = [comparison_row(scenario, o) for o in outputs]
    return {"scenario": scenario, "fingerprint": fp, "outputs": outputs, "comparison": rows,
            "why_different": explain_differences(scenario, outputs, rows)}
