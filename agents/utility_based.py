"""
AGENT 4 - UTILITY-BASED
=======================
In plain words: like choosing a flight by balancing price, travel time and comfort.
It gives every option a score out of 1 for speed, availability and cost, combines them
with weights (how much each one matters to us), and picks the highest total score.
Change the weights in the sidebar and its choice can change.

Technical notes:

    U = w_perf * performance + w_avail * availability + w_cost * cost      (each 0..1)

    performance  = 1 if peak response <= target, else (target / response) ** 2
    availability = 1 if >= SLA, else falls linearly to 0 at 10x the allowed downtime
    cost         = cheapest candidate cost / this candidate's cost
    x 0.5 penalty if peak memory > 85%

Unlike the goal agent it can trade a little of one objective for a lot of
another, and it ranks options even when none meets every target.
"""
from .common import result
from .evaluation import (MEM_LIMIT_PCT, all_candidates, classify_action, fixed_at_peak,
                         recommendation, tradeoffs)

DEFAULT_WEIGHTS = {"performance": 0.4, "availability": 0.3, "cost": 0.3}


def score(c, targets, cheapest):
    # Turn an option into three marks between 0 (bad) and 1 (perfect)
    perf = 1.0 if c["response_ms"] <= targets["response_ms"] else (targets["response_ms"] / c["response_ms"]) ** 2
    allowed = 100 - targets["availability_pct"]
    short = max(0.0, targets["availability_pct"] - c["availability_pct"])
    avail = max(0.0, 1 - short / (10 * allowed))
    cost = cheapest / c["monthly_cost"] if c["monthly_cost"] else 1.0
    return {"performance": round(perf, 3), "availability": round(avail, 3), "cost": round(cost, 3)}


class UtilityBasedAgent:
    name = "Utility-Based"

    def __init__(self, weights=None):
        w = dict(weights or DEFAULT_WEIGHTS)
        total = sum(w.values()) or 1
        self.weights = {k: v / total for k, v in w.items()}

    def utility(self, c, targets, cheapest):
        parts = score(c, targets, cheapest)
        u = sum(self.weights[k] * parts[k] for k in self.weights)
        if not c["memory_ok"]:
            u *= 0.5
        return round(u, 4), parts

    def decide(self, scenario):
        t = scenario["targets"]
        space = all_candidates(scenario)
        cheapest = min(c["monthly_cost"] for c in space)
        for c in space:
            c["utility"], c["utility_parts"] = self.utility(c, t, cheapest)
        ranked = sorted(space, key=lambda c: (-c["utility"], c["monthly_cost"]))
        best, second = ranked[0], ranked[1]
        current = fixed_at_peak(scenario, scenario["instance_type"], scenario["count"], "Keep current")
        current["utility"], current["utility_parts"] = self.utility(current, t, cheapest)
        action = classify_action(scenario, best)

        w = self.weights
        reasoning = [
            f"Utility = {w['performance']:.2f} x performance + {w['availability']:.2f} x availability "
            f"+ {w['cost']:.2f} x cost (each 0-1, x0.5 if peak memory > {MEM_LIMIT_PCT}%).",
            f"Scored {len(space)} candidates at the peak sample. Current config utility = {current['utility']}.",
            f"Best: '{best['label']}' utility {best['utility']} {best['utility_parts']}.",
            f"Runner-up: '{second['label']}' utility {second['utility']}; margin {best['utility'] - second['utility']:.4f}.",
        ]
        if not best["meets_goal"]:
            reasoning.append("The highest-utility option does not meet every target - it is the best compromise.")
        reasoning += tradeoffs(scenario, best)
        monitoring = [
            f"Alert if response time > {t['response_ms']} ms or availability < {t['availability_pct']}%.",
            "Track monthly cost; if prices or traffic change, re-score - the ranking can flip.",
            "Review the weights with stakeholders; they encode the business trade-off.",
        ]
        return result(self.name, scenario, [current] + ranked[:4], recommendation(best, action),
                      reasoning, monitoring, weights=w,
                      top_scores=[{"label": c["label"], "utility": c["utility"], **c["utility_parts"]}
                                  for c in ranked[:5]])
