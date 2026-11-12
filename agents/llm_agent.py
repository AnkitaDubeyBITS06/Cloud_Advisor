"""
AGENT 6 - LLM (AI LANGUAGE MODEL)
=================================
In plain words: an AI model running on this computer (through Ollama) acts like an analyst.
  1. It ASKS for data using four "tools" (metrics, targets, scaling rules, cost estimates).
  2. It writes a recommendation based on what the tools told it.
  3. Our code then REVIEWS the draft: did it check the option it recommends? does that option
     meet the targets? are all its numbers real? If not, it is asked to fix it (up to 2 times).
  4. If problems are still there, the answer is marked "Needs human review" rather than trusted.

Technical notes - LLM Agent (ReAct + Reflection): a local Ollama model (default qwen2.5:3b) through LangChain with tool calling.

The model gets four tools that read the SAME scenario dict as the other agents and use
the SAME estimator (common.py / evaluation.py):
    get_resource_metrics()      get_service_level_targets()
    get_scaling_policy()        get_cost_estimate(instance_type, count, scheduled)
It must call at least two different tools, then reply with a JSON recommendation.
REFLECTION (Session 6, pattern 2): code checks the draft against a standard - recommended config
evaluated with get_cost_estimate, targets met, action consistent with the config, numbers grounded,
a cheaper option checked - and sends the problems back for up to MAX_REFLECTIONS revisions.
Afterwards an evidence check verifies that the numbers it quotes appear in tool outputs
and that it actually evaluated the config it recommends. The recommendation is re-scored
with the shared estimator so it is comparable with the other agents.
"""
import json
import os
import re
import statistics

from scenarios import CATALOG, SIZE_ORDER
from .common import monthly_cost, result
from .evaluation import (MAX_COUNT, MEM_LIMIT_PCT, PEAK_CPU_TARGET, classify_action, fixed_at_peak,
                         peak_sample, recommendation, scheduled_at_peak, trough_sample, tradeoffs)

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
DEFAULT_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ACTIONS = ["keep", "scale_up", "scale_down", "scale_out", "scheduled_scaling"]

SYSTEM_PROMPT = """You are a cloud resource and cost optimisation advisor. You ADVISE only; you never change resources.
Gather evidence with the tools before answering:
1. Call get_resource_metrics and get_service_level_targets.
2. Call get_scaling_policy to see the allowed sizes and limits.
3. Call get_cost_estimate for the current config and for at least two alternatives
   (different sizes/counts, and scheduled=true if the load has a clear peak).
Estimates are made at the PEAK hour. Only quote numbers that appear in tool results.

When done, reply with ONLY this JSON object and nothing else:
{
  "current_state_summary": "...",
  "candidates": [{"config": "e.g. 3 x large", "monthly_cost": 0, "response_ms": 0, "availability_pct": 0, "note": "..."}],
  "recommendation": {"action": "keep|scale_up|scale_down|scale_out|scheduled_scaling",
                     "instance_type": "...", "count": 0, "scheduled": false},
  "reasoning": ["..."],
  "trade_offs": ["..."],
  "monitoring_plan": ["..."],
  "confidence": "low|medium|high"
}"""


# ----------------------------------------------------------------- tools (plain Python)
# The four tools the AI can call. Each one reads the same scenario data as the other agents.
class ScenarioTools:
    def __init__(self, scenario):
        self.s = scenario

    def get_resource_metrics(self) -> str:
        """Current configuration plus 24 hourly samples of CPU %, memory % and response time (ms),
        with mean / peak / trough summaries."""
        h = self.s["history"]
        pk, tr = peak_sample(self.s), trough_sample(self.s)
        return json.dumps({
            "current_config": {"instance_type": self.s["instance_type"], "count": self.s["count"],
                               **CATALOG[self.s["instance_type"]],
                               "monthly_cost": monthly_cost(self.s["instance_type"], self.s["count"])},
            "summary": {"cpu_mean": round(statistics.mean(x["cpu"] for x in h), 1),
                        "cpu_peak": pk["cpu"], "cpu_peak_hour": pk["hour"],
                        "cpu_trough": tr["cpu"], "cpu_trough_hour": tr["hour"],
                        "mem_mean": round(statistics.mean(x["mem"] for x in h), 1),
                        "mem_peak": max(x["mem"] for x in h),
                        "response_ms_peak": max(x["response_ms"] for x in h),
                        "response_ms_latest": h[-1]["response_ms"],
                        "hours_above_70pct_cpu": sum(x["cpu"] > 70 for x in h)},
            "hourly_cpu_pct": [x["cpu"] for x in h],
            "hourly_mem_pct": [x["mem"] for x in h],
            "hourly_response_ms": [x["response_ms"] for x in h],
        })

    def get_service_level_targets(self) -> str:
        """Service-level targets (response time ms, availability %) and the current availability."""
        return json.dumps({**self.s["targets"], "current_availability_pct": self.s["current_availability_pct"]})

    def get_scaling_policy(self) -> str:
        """Scaling policy: allowed instance sizes with prices, instance-count limits, CPU thresholds
        and whether scheduled scaling is allowed."""
        return json.dumps({
            "allowed_sizes": {t: CATALOG[t] for t in SIZE_ORDER},
            "min_instances": 1, "max_fixed_instances": MAX_COUNT, "max_scheduled_instances": 2 * MAX_COUNT,
            "target_peak_cpu_pct": PEAK_CPU_TARGET, "scale_out_cpu_pct": 80, "scale_in_cpu_pct": 20,
            "memory_limit_pct": MEM_LIMIT_PCT, "cooldown_minutes": 15,
            "scheduled_scaling_allowed": True,
            "note": "Scheduled scaling keeps a small baseline off-peak and adds instances for hours above 70% CPU.",
        })

    def get_cost_estimate(self, instance_type: str, count: int, scheduled: bool = False) -> str:
        """Estimate monthly cost (USD), peak CPU %, peak memory %, peak response time (ms), availability %
        and whether targets are met for a configuration. scheduled=true evaluates scheduled scaling
        for that instance type (instance counts are then chosen automatically)."""
        if instance_type not in CATALOG:
            return json.dumps({"error": f"unknown instance_type '{instance_type}'", "valid": SIZE_ORDER})
        c = scheduled_at_peak(self.s, instance_type) if scheduled else \
            fixed_at_peak(self.s, instance_type, max(1, int(count)))
        keep = ["label", "instance_type", "count", "baseline_count", "monthly_cost", "cpu_pct", "mem_pct",
                "response_ms", "availability_pct", "meets_response_target", "meets_availability",
                "memory_ok", "meets_goal"]
        return json.dumps({k: c[k] for k in keep if k in c})


# ----------------------------------------------------------------- evidence check
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def _numbers(obj):
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        return [float(x) for x in _NUM.findall(obj)]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _numbers(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in _numbers(v)]
    return []


def check_grounding(answer, tool_log, rec):
    # Fact-check: every number the AI quotes must appear in what the tools returned
    evidence = []
    for t in tool_log:
        try:
            evidence += _numbers(json.loads(t["output"]))
        except (json.JSONDecodeError, TypeError):
            evidence += _numbers(t["output"])
        evidence += _numbers(t.get("args", {}))
    match = lambda x: any(abs(x - e) <= max(0.02 * abs(e), 0.6) for e in evidence)
    claimed = [n for n in _numbers(answer) if abs(n) > 10]       # skip small counts
    grounded = [n for n in claimed if match(n)]
    tools_used = sorted({t["name"] for t in tool_log})
    evaluated = bool(rec) and any(
        t["name"] == "get_cost_estimate" and t["args"].get("instance_type") == rec["instance_type"]
        and bool(t["args"].get("scheduled")) == bool(rec.get("scheduled")) for t in tool_log)
    ratio = len(grounded) / len(claimed) if claimed else 1.0
    return {"tools_used": tools_used, "distinct_tools": len(tools_used),
            "numbers_claimed": len(claimed), "numbers_grounded": len(grounded),
            "grounded_ratio": round(ratio, 2),
            "ungrounded_numbers": sorted({n for n in claimed if not match(n)})[:20],
            "recommendation_evaluated_with_tool": evaluated,
            "passed": len(tools_used) >= 2 and ratio >= 0.8 and evaluated}


def parse_json_answer(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    blob = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None


# ----------------------------------------------------------------- reflection (critique of a draft)
MAX_REFLECTIONS = int(os.getenv("LLM_REFLECTIONS", "2"))   # set LLM_REFLECTIONS=0 or 1 to run faster


def critique(scenario, answer, tool_log):
    # The reviewer: lists everything wrong with the AI's draft (empty list = all good)
    """Return a list of problems with the LLM's draft answer (empty list = acceptable)."""
    if not answer:
        return ["Your reply was not valid JSON. Reply with ONLY the JSON object described in the instructions."]
    r = answer.get("recommendation") or {}
    itype, count, sched = r.get("instance_type"), r.get("count"), bool(r.get("scheduled"))
    if itype not in CATALOG:
        return [f"recommendation.instance_type must be one of {SIZE_ORDER}."]
    problems = []
    evals = [json.loads(t["output"]) for t in tool_log if t["name"] == "get_cost_estimate"
             and not json.loads(t["output"]).get("error")]
    mine = [e for e in evals if e["instance_type"] == itype and bool(e.get("baseline_count")) == sched
            and (sched or e["count"] == count)]
    if not mine:
        problems.append(f"You never evaluated your recommended config ({count} x {itype}, scheduled={sched}). "
                        "Call get_cost_estimate for it and use the returned numbers.")
    else:
        e = mine[-1]
        if not e["meets_goal"]:
            fails = [k for k in ("meets_response_target", "meets_availability", "memory_ok") if not e[k]]
            problems.append(f"Your recommended config fails the targets ({', '.join(fails)}: response "
                            f"{e['response_ms']} ms, availability {e['availability_pct']}%). Choose and evaluate "
                            "a config that meets them.")
        cheaper = [x for x in evals if x["monthly_cost"] < e["monthly_cost"]]
        better = sorted((x for x in cheaper if x["meets_goal"]), key=lambda x: x["monthly_cost"])
        if better:
            b = better[0]
            problems.append(f"You evaluated '{b['label']}' at ${b['monthly_cost']}/month and it ALSO meets every target, "
                            f"but you chose a ${e['monthly_cost']}/month option. Choose the cheaper one, or explain in "
                            "reasoning why the extra cost is worth it.")
        if e["meets_goal"] and not cheaper:
            problems.append(f"The task also asks you to balance cost. Your config costs ${e['monthly_cost']}/month; "
                            "evaluate at least one cheaper option with get_cost_estimate before finalising.")
    same_as_now = (itype == scenario["instance_type"] and count == scenario["count"] and not sched)
    act = r.get("action")
    if same_as_now and act not in (None, "keep"):
        problems.append(f"action '{act}' does not match the config you gave (it is the current config).")
    if not same_as_now and act == "keep":
        problems.append("action 'keep' does not match a config that differs from the current one.")
    g = check_grounding(answer, tool_log, None)
    if g["ungrounded_numbers"]:
        problems.append(f"These numbers do not appear in any tool result: {g['ungrounded_numbers']}. "
                        "Only quote numbers returned by the tools.")
    return problems


# ----------------------------------------------------------------- agent
def build_langchain_tools(st):
    from langchain_core.tools import StructuredTool

    def get_resource_metrics() -> str:
        return st.get_resource_metrics()

    def get_service_level_targets() -> str:
        return st.get_service_level_targets()

    def get_scaling_policy() -> str:
        return st.get_scaling_policy()

    def get_cost_estimate(instance_type: str, count: int, scheduled: bool = False) -> str:
        return st.get_cost_estimate(instance_type, count, scheduled)

    funcs = [get_resource_metrics, get_service_level_targets, get_scaling_policy, get_cost_estimate]
    return [StructuredTool.from_function(func=f, name=f.__name__,
                                         description=getattr(st, f.__name__).__doc__.strip()) for f in funcs]


TIMEOUT_S = int(os.getenv("OLLAMA_TIMEOUT", "600"))     # per model call
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))     # Ollama's usual default: avoids reloading the model
KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")     # keep the model loaded between steps and runs


def make_ollama(model=DEFAULT_MODEL, base_url=DEFAULT_URL):
    from langchain_ollama import ChatOllama
    base = dict(model=model, base_url=base_url, temperature=0, num_ctx=NUM_CTX, keep_alive=KEEP_ALIVE)
    for extra in ({"reasoning": False, "client_kwargs": {"timeout": TIMEOUT_S}},
                  {"client_kwargs": {"timeout": TIMEOUT_S}}, {}):
        try:                   # newer langchain-ollama accepts more options; fall back for older ones
            return ChatOllama(**base, **extra)
        except (TypeError, ValueError):
            continue
    return ChatOllama(model=model, base_url=base_url, temperature=0)


class LLMAgent:
    name = "LLM (Ollama)"

    def __init__(self, model=DEFAULT_MODEL, base_url=DEFAULT_URL, chat_model=None, max_steps=14, verbose=True):
        self.model, self.base_url, self.verbose = model, base_url, verbose
        self.chat_model = chat_model          # inject a fake model for offline tests
        self.max_steps = max_steps

    def _unavailable(self, scenario, err):
        return result(self.name, scenario, [], {"action": "unavailable"},
                      [f"LLM agent could not run: {err}"], [], error=err)

    def decide(self, scenario):
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
            st = ScenarioTools(scenario)
            tools = build_langchain_tools(st)
            llm = (self.chat_model or make_ollama(self.model, self.base_url)).bind_tools(tools)
        except Exception as e:                       # noqa: BLE001 - shown in the UI
            return self._unavailable(scenario, f"{type(e).__name__}: {e}")

        by_name = {t.name: t for t in tools}
        msgs = [SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Scenario {scenario['id']}: {scenario['name']}. "
                                     "Analyse it and recommend a configuration. Start by calling tools. /no_think")]
        tool_log, final, nudged, reflections = [], "", False, []
        try:
            import time
            for step in range(1, self.max_steps + 1):
                t0 = time.time()
                if self.verbose:
                    print(f"    [LLM {self.model}] step {step}: thinking...", flush=True)
                ai = llm.invoke(msgs)
                msgs.append(ai)
                calls = getattr(ai, "tool_calls", None) or []
                if self.verbose:
                    print(f"    [LLM] step {step} done in {time.time() - t0:.0f}s -> "
                          + (", ".join(f"{c['name']}({json.dumps(c.get('args') or {})})" for c in calls)
                             if calls else "final answer"), flush=True)
                if calls:
                    for tc in calls:
                        args = tc.get("args") or {}
                        try:
                            out = by_name[tc["name"]].invoke(args) if tc["name"] in by_name \
                                else json.dumps({"error": "unknown tool"})
                        except Exception as e:      # noqa: BLE001
                            out = json.dumps({"error": str(e)})
                        tool_log.append({"name": tc["name"], "args": args, "output": str(out)})
                        msgs.append(ToolMessage(content=str(out), tool_call_id=tc.get("id") or tc["name"]))
                    continue
                if len({t["name"] for t in tool_log}) < 2 and not nudged:
                    nudged = True
                    msgs.append(HumanMessage(content="You must call at least two different tools and base "
                                                     "your answer on their results. Call the tools now."))
                    continue
                final = ai.content if isinstance(ai.content, str) else json.dumps(ai.content)
                draft = parse_json_answer(final)
                problems = critique(scenario, draft, tool_log)                      # REFLECTION
                if problems and len(reflections) < MAX_REFLECTIONS:
                    extra = ""
                    r0 = (draft or {}).get("recommendation") or {}
                    if any(p.startswith("You never evaluated") for p in problems) and r0.get("instance_type") in CATALOG:
                        # the reviewer (code) runs the check itself and hands the evidence back
                        args = {"instance_type": r0["instance_type"], "count": int(r0.get("count") or 1),
                                "scheduled": bool(r0.get("scheduled"))}
                        out = st.get_cost_estimate(**args)
                        tool_log.append({"name": "get_cost_estimate", "args": args, "output": out, "by": "reviewer"})
                        extra = f"\nThe reviewer ran get_cost_estimate({json.dumps(args)}) for you. Result: {out}"
                        if self.verbose:
                            print(f"    [LLM] reviewer ran get_cost_estimate({json.dumps(args)})", flush=True)
                    reflections.append(problems)
                    if self.verbose:
                        print(f"    [LLM] reflection {len(reflections)}: {len(problems)} problem(s) -> asking to revise",
                              flush=True)
                    msgs.append(HumanMessage(content="Review of your draft found these problems:\n- "
                                             + "\n- ".join(problems)
                                             + extra
                                             + "\nFix them (call tools if needed), then reply with ONLY the "
                                               "corrected JSON. /no_think"))
                    continue
                break
        except Exception as e:                       # noqa: BLE001 - e.g. Ollama not running
            return self._unavailable(scenario, f"{type(e).__name__}: {e}")

        ans = parse_json_answer(final) or {}
        r = ans.get("recommendation") or {}
        chosen = None
        if r.get("instance_type") in CATALOG:
            try:
                chosen = scheduled_at_peak(scenario, r["instance_type"]) if r.get("scheduled") else \
                    fixed_at_peak(scenario, r["instance_type"], max(1, int(r.get("count") or 1)))
            except (TypeError, ValueError):
                chosen = None
        grounding = check_grounding(ans or final, tool_log,
                                    {"instance_type": r.get("instance_type"), "scheduled": r.get("scheduled")} if chosen else None)

        if chosen:
            action = r.get("action") if r.get("action") in ACTIONS else classify_action(scenario, chosen)
            rec = recommendation(chosen, action)
        else:
            rec = {"action": "unparsed"}
        reasoning = list(ans.get("reasoning") or [final[:1500] or "No final answer."])
        reasoning.append(f"Tools called ({len(tool_log)} calls, {grounding['distinct_tools']} distinct): "
                         + ", ".join(t["name"] + (" [by reviewer]" if t.get("by") else "") for t in tool_log) + ".")
        reasoning.append(f"Evidence check: {grounding['numbers_grounded']}/{grounding['numbers_claimed']} quoted numbers "
                         f"found in tool outputs; recommended config evaluated with get_cost_estimate: "
                         f"{grounding['recommendation_evaluated_with_tool']} -> "
                         f"{'PASSED' if grounding['passed'] else 'FAILED'}.")
        for i, probs in enumerate(reflections, 1):
            reasoning.append(f"Reflection {i}: draft sent back to revise - " + " | ".join(probs))
        if not reflections:
            reasoning.append("Reflection: the first draft passed the review; no revision needed.")
        unresolved = critique(scenario, ans, tool_log)                     # HUMAN IN THE LOOP
        if unresolved:
            reasoning.append(f"NEEDS HUMAN REVIEW: after {len(reflections)} revision(s) these problems remain - "
                             + " | ".join(unresolved) + " The recommendation is NOT verified; do not apply it "
                             "without a person checking it.")
        else:
            reasoning.append("Final review passed: recommendation verified against tool evidence.")
        if chosen:
            reasoning += tradeoffs(scenario, chosen)
        return result(self.name, scenario, ans.get("candidates") or [], rec, reasoning,
                      ans.get("monitoring_plan") or [],
                      llm_summary=ans.get("current_state_summary"), trade_offs=ans.get("trade_offs") or [],
                      confidence="low" if unresolved else ans.get("confidence"),
                      needs_human_review=bool(unresolved), unresolved_problems=unresolved, tool_log=tool_log, grounding=grounding,
                      raw_answer=final, model=self.model, reflections=reflections)
