"""
AGENT 3 - GOAL-BASED
====================
In plain words: like a route planner. It has a clear goal -
"fast enough, available enough and not running out of memory, even at the busiest hour" -
then it checks EVERY possible option and picks the cheapest one that reaches the goal.
An option either passes or fails; there is no "nearly good enough".

Technical notes:

Goal (all must hold at the PEAK sample):
    response time <= target  AND  availability >= SLA  AND  memory <= 85%
The agent predicts the outcome of every candidate, keeps those that reach the
goal and picks the cheapest. A goal is pass/fail, so it can't express
"almost good enough" - that's what the Utility-Based agent adds.
"""
from .common import result
from .evaluation import (MEM_LIMIT_PCT, all_candidates, classify_action, fixed_at_peak,
                         peak_sample, recommendation, tradeoffs)


def goal_test(c):
    # Pass/fail: does this option meet every target?
    return c["meets_goal"]


class GoalBasedAgent:
    name = "Goal-Based"

    def decide(self, scenario):
        t = scenario["targets"]
        pk = peak_sample(scenario)
        current = fixed_at_peak(scenario, scenario["instance_type"], scenario["count"], "Keep current")
        space = all_candidates(scenario)
        reached = sorted((c for c in space if goal_test(c)), key=lambda c: (c["monthly_cost"], c["response_ms"]))

        reasoning = [
            f"Goal: at peak (hour {pk['hour']}, CPU {pk['cpu']}%), response <= {t['response_ms']} ms, "
            f"availability >= {t['availability_pct']}%, memory <= {MEM_LIMIT_PCT}%.",
            f"Current config reaches the goal: {goal_test(current)} "
            f"(peak response {current['response_ms']} ms, availability {current['availability_pct']}%).",
            f"Searched {len(space)} candidates ({len(space) - 5} fixed sizes/counts + 5 scheduled-scaling plans); "
            f"{len(reached)} reach the goal.",
        ]
        if reached:
            chosen = reached[0]
            action = classify_action(scenario, chosen)
            reasoning.append(f"Plan: the cheapest goal-reaching option is '{chosen['label']}' at "
                             f"${chosen['monthly_cost']}/month (peak response {chosen['response_ms']} ms).")
            if len(reached) > 1:
                reasoning.append(f"Next cheapest: '{reached[1]['label']}' at ${reached[1]['monthly_cost']}/month.")
            shown = [current] + reached[:4]
        else:
            chosen = min(space, key=lambda c: c["response_ms"])
            action = classify_action(scenario, chosen)
            reasoning.append(f"No candidate reaches the goal; falling back to the fastest one, "
                             f"'{chosen['label']}' ({chosen['response_ms']} ms).")
            shown = [current, chosen]

        reasoning += tradeoffs(scenario, chosen)
        monitoring = [
            f"Alert if response time > {t['response_ms']} ms or availability < {t['availability_pct']}%.",
            f"Alert if memory > {MEM_LIMIT_PCT}% (the goal assumes headroom).",
            "Re-run the goal test whenever traffic or targets change; the plan is only as good as its goal.",
        ]
        if action == "scheduled_scaling":
            monitoring.append("Check the scaling schedule fires before each peak and scale-in happens after it.")
        return result(self.name, scenario, shown, recommendation(chosen, action), reasoning, monitoring,
                      goal_satisfying=len(reached), searched=len(space))
