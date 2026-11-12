"""
AGENT 5 - LEARNING
==================
In plain words: like a person who keeps a notebook of what worked before.
For each kind of situation (very busy, mostly idle, up-and-down) it remembers how often
each action succeeded or failed, and tries the one with the best track record.
After every decision it checks the result and updates the notebook (experience.json),
so next time it may choose differently.

Technical notes:

The four components of a learning agent (Russell & Norvig, AIMA Ch. 2):
    Performance element - chooses the action with the best success rate so far
    Critic              - judges the outcome against the standard (goal met, not wasteful)
    Learning element    - updates the success/failure counts in experience.json
    Problem generator   - now and then tries a different action (epsilon) to gain experience

Experience store: experience.json  ->  {situation: {action: {"success": n, "failure": n}}, "history": [...]}

1. Perceive  - classify the scenario into a situation
               (volatile / high_load / over_provisioned / steady).
2. Decide    - success rate = (success + 1) / (success + failure + 2)   (Laplace smoothing);
               pick the best, with epsilon-greedy exploration. Ties -> most conservative action.
3. Act       - map the action to a concrete config (one-step rule, like the reflex agents).
4. Learn     - a critic judges the simulated outcome at the PEAK sample and the counts are
               updated and saved, so the next run can choose differently.

Success = the outcome meets the goal (peak response, availability, memory) AND is not
wasteful: cost <= 2 x the cheapest goal-reaching option, and - if the current config already
meets the goal - it must also cut cost. If nothing can reach the goal, success = no extra
cost and no worse response time.
"""
import json
import random
import shutil
import statistics
from pathlib import Path

from .common import result, shift_size
from .evaluation import (all_candidates, fixed_at_peak, recommendation, scheduled_at_peak, tradeoffs)

HERE = Path(__file__).resolve().parent.parent
EXPERIENCE_PATH = HERE / "experience.json"
SEED_PATH = HERE / "experience_seed.json"
ACTIONS = ["keep", "scale_down", "scale_up", "scale_out", "scheduled_scaling"]   # conservative first
WASTE_FACTOR = 2.0


def situation(scenario):
    # Put the scenario into a simple category so past experience can be looked up
    cpu = [s["cpu"] for s in scenario["history"]]
    mem = [s["mem"] for s in scenario["history"]]
    if max(cpu) >= 75 and min(cpu) <= 30:
        return "volatile"
    if statistics.mean(cpu) > 70:
        return "high_load"
    if statistics.mean(cpu) < 25 and statistics.mean(mem) < 30:
        return "over_provisioned"
    return "steady"


def reset_experience(path=EXPERIENCE_PATH, empty=False):
    path = Path(path)
    if empty or not SEED_PATH.exists():
        path.write_text(json.dumps({"history": []}, indent=2))
    else:
        shutil.copy(SEED_PATH, path)
    return json.loads(path.read_text())


def load_experience(path=EXPERIENCE_PATH):
    path = Path(path)
    if not path.exists():
        return reset_experience(path)
    return json.loads(path.read_text())


def save_experience(exp, path=EXPERIENCE_PATH):
    Path(path).write_text(json.dumps(exp, indent=2))


def success_rate(stats):
    # e.g. 3 successes and 1 failure -> (3+1)/(4+2) = 0.67.
    # The +1/+2 stops a single lucky result from looking like 100%.
    return (stats["success"] + 1) / (stats["success"] + stats["failure"] + 2)


def apply_action(scenario, action):
    # Turn an action name (e.g. 'scale_up') into an actual set of servers
    t, n = scenario["instance_type"], scenario["count"]
    if action == "scale_up":
        return fixed_at_peak(scenario, shift_size(t, +1), n, "Scale up one size")
    if action == "scale_down":
        return fixed_at_peak(scenario, shift_size(t, -1), n, "Scale down one size")
    if action == "scale_out":
        return fixed_at_peak(scenario, t, n + 1, "Add one instance")
    if action == "scheduled_scaling":
        return scheduled_at_peak(scenario, t)
    return fixed_at_peak(scenario, t, n, "Keep current")


def critic(scenario, outcome):
    """CRITIC: judge the outcome against the performance standard."""
    reachable = [c for c in all_candidates(scenario) if c["meets_goal"]]
    current = fixed_at_peak(scenario, scenario["instance_type"], scenario["count"])
    if reachable:
        cheapest = min(c["monthly_cost"] for c in reachable)
        saves = (not current["meets_goal"]) or outcome["monthly_cost"] < current["monthly_cost"]
        ok = outcome["meets_goal"] and outcome["monthly_cost"] <= WASTE_FACTOR * cheapest and saves
        why = (f"meets goal: {outcome['meets_goal']}; cost ${outcome['monthly_cost']} vs waste limit "
               f"${WASTE_FACTOR * cheapest:.2f} (2 x cheapest goal-reaching ${cheapest})"
               + ("" if not current["meets_goal"] else f"; current already meets goal, so it must cut cost: {saves}"))
    else:
        ok = outcome["monthly_cost"] <= current["monthly_cost"] and outcome["response_ms"] <= current["response_ms"]
        why = "goal unreachable: success only if no extra cost and no worse response"
    return ok, why


class LearningAgent:
    name = "Learning"

    def __init__(self, experience_path=EXPERIENCE_PATH, epsilon=0.0, learn=True, seed=None):
        self.path = Path(experience_path)
        self.epsilon, self.learn, self.seed = epsilon, learn, seed

    # ---- the four components -------------------------------------------------
    @staticmethod
    def performance_element(rates):
        """PERFORMANCE ELEMENT: pick the action with the best success rate (ties -> most conservative)."""
        return max(ACTIONS, key=lambda a: (rates[a], -ACTIONS.index(a)))

    def problem_generator(self, rng, best):
        """PROBLEM GENERATOR: with probability epsilon, suggest a different action to explore."""
        if rng.random() < self.epsilon:
            return True, rng.choice([a for a in ACTIONS if a != best])
        return False, best

    def learning_element(self, exp, table, scenario, sit, action, success, explored):
        """LEARNING ELEMENT: record the critic's verdict so the next decision can change."""
        table[action]["success" if success else "failure"] += 1
        exp.setdefault("history", []).append({"scenario": scenario["id"], "situation": sit,
                                              "action": action, "success": success, "explored": explored})
        save_experience(exp, self.path)

    # ---- one decision cycle ----------------------------------------------------
    def decide(self, scenario):
        exp = load_experience(self.path)
        sit = situation(scenario)
        table = exp.setdefault(sit, {})
        for a in ACTIONS:
            table.setdefault(a, {"success": 0, "failure": 0})
        before = {a: dict(table[a]) for a in ACTIONS}
        rates = {a: round(success_rate(table[a]), 3) for a in ACTIONS}
        trials = sum(v["success"] + v["failure"] for v in before.values())

        rng = random.Random(self.seed if self.seed is not None else len(exp.get("history", [])))
        best = self.performance_element(rates)                     # PERFORMANCE ELEMENT
        explored, action = self.problem_generator(rng, best)       # PROBLEM GENERATOR

        outcome = apply_action(scenario, action)
        success, why = critic(scenario, outcome)                   # CRITIC

        reasoning = [
            f"Situation recognised as '{sit}' ({trials} past trials for this situation).",
            "Performance element - success rates from experience: " + ", ".join(
                f"{a} {rates[a]:.2f} ({before[a]['success']}S/{before[a]['failure']}F)" for a in ACTIONS) + ".",
        ]
        if explored:
            reasoning.append(f"Problem generator: exploration step (epsilon={self.epsilon}) - tried '{action}' "
                             f"instead of the best-known '{best}' to gain experience.")
        elif trials == 0:
            reasoning.append(f"No experience for '{sit}' yet; all actions tie, so the most conservative ('{action}') is chosen.")
        else:
            reasoning.append(f"Performance element: '{action}' has the highest success rate ({rates[action]:.2f}).")
        reasoning.append(f"Action -> '{outcome['label']}'. Critic verdict: {'SUCCESS' if success else 'FAILURE'} ({why}).")

        if self.learn:
            self.learning_element(exp, table, scenario, sit, action, success, explored)   # LEARNING ELEMENT
            reasoning.append(f"Learning element: experience updated - {action} now {table[action]['success']}S/{table[action]['failure']}F "
                             f"(rate {rates[action]:.2f} -> {success_rate(table[action]):.2f}). "
                             + ("More likely to be chosen next time." if success else
                                "Another action may win next time."))
        else:
            reasoning.append("Learning disabled for this run: experience not updated.")
        reasoning += tradeoffs(scenario, outcome)

        after = {a: dict(table[a]) for a in ACTIONS}
        monitoring = [
            "After applying the change, record whether targets were actually met; feed that back as the outcome.",
            f"Alert if response time > {scenario['targets']['response_ms']} ms.",
            "Review the experience table monthly; old outcomes may no longer reflect the workload.",
        ]
        return result(self.name, scenario, [apply_action(scenario, a) | {"action": a} for a in ACTIONS],
                      recommendation(outcome, action), reasoning, monitoring,
                      situation=sit, rates_before=rates, experience_before=before, experience_after=after,
                      explored=explored, outcome_success=success,
                      components={
                          "Performance element": f"best-known action for '{sit}': {best} (rate {rates[best]:.2f})",
                          "Problem generator": (f"explored '{action}' (epsilon={self.epsilon})" if explored
                                                else f"no exploration this run (epsilon={self.epsilon})"),
                          "Critic": f"{'SUCCESS' if success else 'FAILURE'} - {why}",
                          "Learning element": (f"{action}: {before[action]['success']}S/{before[action]['failure']}F -> "
                                               f"{table[action]['success']}S/{table[action]['failure']}F"
                                               if self.learn else "learning disabled"),
                      })
