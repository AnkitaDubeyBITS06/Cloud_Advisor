"""
AGENT 1 - SIMPLE REFLEX
=======================
In plain words: like a thermostat. It looks ONLY at the latest reading and follows fixed rules:
  - busy or slow?           -> use a bigger server
  - almost idle?            -> use a smaller server
  - otherwise               -> leave it as it is
It has no memory and does not plan ahead, so one unusual reading can fool it
(see scenario C, where the last reading happens to be at a quiet time).
"""
from scenarios import SIZE_ORDER
from .common import (latest, candidate, recommendation_from, result, shift_size)

CPU_HIGH = 80      # %  -> scale up
CPU_LOW = 20       # %  -> scale down (together with MEM_LOW)
MEM_LOW = 30       # %


class SimpleReflexAgent:
    name = "Simple Reflex"

    def decide(self, scenario):
        p = latest(scenario)                      # the only thing it perceives
        itype, count = scenario["instance_type"], scenario["count"]
        target = scenario["targets"]["response_ms"]

        keep = candidate(scenario, "Keep current", itype, count)
        up = candidate(scenario, "Scale up one size", shift_size(itype, +1), count)
        down = candidate(scenario, "Scale down one size", shift_size(itype, -1), count)

        # --- condition-action rules (first match wins) ---
        if p["cpu"] > CPU_HIGH or p["response_ms"] > target:
            chosen, action, rule = up, "scale_up", (
                f"RULE 1: CPU {p['cpu']}% > {CPU_HIGH}% or response {p['response_ms']} ms "
                f"> {target} ms -> scale up one size.")
        elif p["cpu"] < CPU_LOW and p["mem"] < MEM_LOW:
            chosen, action, rule = down, "scale_down", (
                f"RULE 2: CPU {p['cpu']}% < {CPU_LOW}% and memory {p['mem']}% < {MEM_LOW}% "
                f"-> scale down one size.")
        else:
            chosen, action, rule = keep, "keep", (
                "RULE 3: no rule fired (CPU/response in acceptable range) -> keep current.")

        # Guard: already at the end of the catalog
        if action == "scale_up" and itype == SIZE_ORDER[-1]:
            chosen, action = keep, "keep"
            rule += " Already at the largest size, so keeping."
        if action == "scale_down" and itype == SIZE_ORDER[0]:
            chosen, action = keep, "keep"
            rule += " Already at the smallest size, so keeping."

        reasoning = [
            rule,
            f"Only the latest sample (hour {p['hour']}) was used; earlier hours were ignored.",
            f"Estimated result: CPU {chosen['cpu_pct']}%, response {chosen['response_ms']} ms, "
            f"${chosen['monthly_cost']}/month.",
        ]
        monitoring = [
            "Re-evaluate on every new metrics sample (rules are stateless).",
            f"Alert if CPU > {CPU_HIGH}% or response time > {target} ms.",
            "Check CPU again 15 minutes after any change.",
        ]
        return result(self.name, scenario, [keep, up, down],
                      recommendation_from(chosen, action), reasoning, monitoring,
                      limitation="Blind to trends and peaks: a single snapshot can mislead.")
