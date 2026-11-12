"""
QUICK TEST
==========
In plain words: runs every agent on every scenario, checks that they behave as expected
(e.g. "in scenario C the simple agent should be fooled") and saves the results in
test_results/ for the report. Prints PASS or FAIL for each check.

    python quick_test.py            # five classical agents + offline LLM check (fake model)
    python quick_test.py --llm      # also the real Ollama LLM agent (Ollama must be running)
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from scenarios import SCENARIOS
from agents import run_all, LearningAgent
from agents.learning_agent import EXPERIENCE_PATH, load_experience, reset_experience

OUT = Path(__file__).resolve().parent / "test_results"
COLS = ["Agent", "Action", "Config", "Cost (USD/mo)", "Agent's own est. response (ms)",
        "Peak response (ms)", "Peak CPU (%)", "Availability (%)", "Meets all targets at peak", "Needs human review"]
checks = []


def check(name, cond):
    checks.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def md_table(rows):
    f = lambda v: "yes" if v is True else "no" if v is False else ("-" if v is None else str(v))
    return "\n".join(["| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
                     + ["| " + " | ".join(f(r.get(c)) for c in COLS) + " |" for r in rows])


def write_report(res):
    s = res["scenario"]
    lines = [f"# {s['name']} ({s['type']})", "", f"Input fingerprint (same for every agent): `{res['fingerprint']}`", "",
             "## Comparison", "", md_table(res["comparison"]), "", "## Why decisions differ", ""]
    lines += [f"- {x}" for x in res["why_different"]] + [""]
    for o in res["outputs"]:
        lines += [f"## {o['agent']}", "", o["summary"], "", f"**Recommendation:** `{json.dumps(o['recommendation'])}`",
                  "", "**Reasoning**"] + [f"- {x}" for x in o["reasoning"]]
        lines += ["", "**Monitoring plan**"] + [f"- {x}" for x in o["monitoring_plan"]]
        if o["candidates"]:
            lines += ["", "**Candidates**"] + [f"- {c.get('label', c.get('config'))}: ${c.get('monthly_cost')}/mo, "
                                               f"response {c.get('response_ms')} ms" for c in o["candidates"][:6]]
        if "tool_log" in o:
            lines += ["", "**Tool calls**"] + [f"- `{t['name']}({json.dumps(t['args'])})`" for t in o["tool_log"]]
            lines += ["", f"**Evidence check:** `{json.dumps(o['grounding'])}`"]
        lines.append("")
    (OUT / f"scenario_{s['id']}.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / f"scenario_{s['id']}.json").write_text(json.dumps(
        {k: res[k] for k in ("fingerprint", "outputs", "comparison", "why_different")}, indent=2, default=str),
        encoding="utf-8")


def by_agent(res):
    return {o["agent"]: o for o in res["outputs"]}, {r["Agent"]: r for r in res["comparison"]}


def offline_llm_check():
    """Runs the LLM agent with a scripted fake chat model: no Ollama needed, but needs langchain-core."""
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        print("  [SKIP] langchain-core not installed")
        return
    from agents.llm_agent import LLMAgent

    class FakeChat:
        def bind_tools(self, tools):
            return self

        def invoke(self, msgs):
            outs = [m.content for m in msgs if isinstance(m, ToolMessage)]
            if not outs:
                return AIMessage(content="", tool_calls=[{"name": "get_resource_metrics", "args": {}, "id": "1"},
                                                         {"name": "get_service_level_targets", "args": {}, "id": "2"}])
            if len(outs) == 2:
                return AIMessage(content="", tool_calls=[
                    {"name": "get_cost_estimate", "args": {"instance_type": "large", "count": 2}, "id": "3"},
                    {"name": "get_cost_estimate", "args": {"instance_type": "xlarge", "count": 2}, "id": "4"}])
            e = json.loads(outs[-1])
            return AIMessage(content=json.dumps({
                "recommendation": {"action": "scale_up", "instance_type": "xlarge", "count": 2, "scheduled": False},
                "reasoning": [f"2 x xlarge gives {e['response_ms']} ms at peak for ${e['monthly_cost']}/month."],
                "monitoring_plan": ["Alert when response > 200 ms."], "confidence": "high"}))

    o = LLMAgent(chat_model=FakeChat()).decide(SCENARIOS["A"])
    g = o["grounding"]
    check("LLM (fake model) calls >= 2 distinct tools", g["distinct_tools"] >= 2)
    check("LLM (fake model) evidence check passes", g["passed"])

    class Broken:
        def bind_tools(self, tools):
            return self

        def invoke(self, msgs):
            raise ConnectionError("Ollama not running")
    check("LLM handles Ollama being unavailable", "error" in LLMAgent(chat_model=Broken()).decide(SCENARIOS["A"]))


def learning_curve(rounds=10, epsilon=0.2):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "exp.json"
        reset_experience(p, empty=True)
        rows = []
        for r in range(1, rounds + 1):
            outs = [LearningAgent(p, epsilon=epsilon).decide(s) for s in SCENARIOS.values()]
            rows.append((r, sum(o["outcome_success"] for o in outs),
                         ", ".join(f"{o['scenario']}:{o['recommendation']['action']}{'*' if o['explored'] else ''}" for o in outs)))
        exp = load_experience(p)
    lines = ["# Learning agent - learning curve from EMPTY experience", "",
             f"{rounds} rounds x {len(SCENARIOS)} scenarios, epsilon = {epsilon} (* = exploration).", "",
             "| Round | Successes | Actions |", "|---|---|---|"] + [f"| {r} | {w}/{len(SCENARIOS)} | {a} |" for r, w, a in rows]
    lines += ["", "## Final experience", "", "| Situation | Action | Success | Failure |", "|---|---|---|---|"]
    lines += [f"| {s} | {a} | {v['success']} | {v['failure']} |" for s, acts in exp.items()
              if isinstance(acts, dict) and not s.startswith("_") for a, v in acts.items()]
    return "\n".join(lines), rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also run the real Ollama LLM agent")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    reset_experience(EXPERIENCE_PATH)
    summary = ["# Summary - all scenarios", ""]

    for sid, s in SCENARIOS.items():
        print(f"\nScenario {s['name']}")
        res = run_all(s, include_llm=args.llm, llm_model=args.model)
        write_report(res)
        summary += [f"## {s['name']}", "", md_table(res["comparison"]), ""]
        for r in res["comparison"]:
            print(f"  {r['Agent']:<20} {str(r['Action']):<18} {r['Config']:<30} ${r['Cost (USD/mo)']}"
                  f"  peak {r['Peak response (ms)']} ms  ok={r['Meets all targets at peak']}"
                  + ("  NEEDS HUMAN REVIEW" if r.get("Needs human review") else ""))
        out, row = by_agent(res)
        check("all agents received identical input", len({res["fingerprint"]}) == 1 and len(out) >= 5)
        check("every output has summary, candidates, recommendation, reasoning, monitoring plan",
              all(o["summary"] and o["reasoning"] and o["monitoring_plan"] and "action" in o["recommendation"]
                  for o in res["outputs"] if "error" not in o))
        if sid == "A":
            check("A: no classical agent scales down", all(out[a]["recommendation"]["action"] != "scale_down"
                                                           for a in list(out)[:5]))
            check("A: Goal/Utility/Learning meet all targets at peak",
                  all(row[a]["Meets all targets at peak"] for a in ("Goal-Based", "Utility-Based", "Learning")))
        if sid == "B":
            cur = s["count"] * {"xlarge": 0.40}[s["instance_type"]] * 730
            check("B: every classical agent cuts cost", all(row[a]["Cost (USD/mo)"] < cur for a in list(row)[:5]))
        if sid == "C":
            check("C (edge): Simple Reflex is fooled by the off-peak sample",
                  out["Simple Reflex"]["recommendation"]["action"] == "scale_down"
                  and not row["Simple Reflex"]["Meets all targets at peak"])
            check("C (edge): Model-Based detects the peak and schedules scaling",
                  out["Model-Based Reflex"]["recommendation"]["action"] == "scheduled_scaling")
            check("C (edge): Goal/Utility/Learning meet all targets at peak",
                  all(row[a]["Meets all targets at peak"] for a in ("Goal-Based", "Utility-Based", "Learning")))
        lo = out["Learning"]
        check(f"{sid}: Learning agent updated its experience",
              sum(sum(v.values()) for v in lo["experience_after"].values())
              == sum(sum(v.values()) for v in lo["experience_before"].values()) + 1)

    print("\nOffline LLM checks")
    offline_llm_check()
    curve, rows = learning_curve()
    (OUT / "learning_curve.md").write_text(curve, encoding="utf-8")
    print("\nLearning curve (from empty experience)")
    check("Learning: later rounds succeed at least as often as the first round", rows[-1][1] >= rows[0][1])
    (OUT / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    reset_experience(EXPERIENCE_PATH)

    passed = sum(ok for _, ok in checks)
    print(f"\n{passed}/{len(checks)} checks passed. Reports written to {OUT}")
    (OUT / "checks.md").write_text("# quick_test checks\n\n" + "\n".join(
        f"- [{'x' if ok else ' '}] {n}" for n, ok in checks) + f"\n\n**{passed}/{len(checks)} passed**\n", encoding="utf-8")
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
