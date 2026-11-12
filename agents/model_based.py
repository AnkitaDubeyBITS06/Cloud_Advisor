"""
AGENT 2 - MODEL-BASED REFLEX
============================
In plain words: like a robot vacuum that remembers the map of the room.
It still follows rules, but first it builds a MEMORY of the whole day:
the busiest hour, the quietest hour, whether load is rising, and what it did last time.
Because it remembers the busy hours, a quiet last reading does not fool it.
"""
import statistics
from collections import deque
from scenarios import CATALOG, SIZE_ORDER
from .common import (latest, candidate, estimate, monthly_cost, peak_count,
                     recommendation_from, result, shift_size, HOURS_PER_MONTH)


def _slope(values):
    """Least-squares slope (units per sample)."""
    n = len(values)
    if n < 2:
        return 0.0
    xm, ym = (n - 1) / 2, sum(values) / n
    den = sum((i - xm) ** 2 for i in range(n))
    return sum((i - xm) * (v - ym) for i, v in enumerate(values)) / den


class ModelBasedReflexAgent:
    name = "Model-Based Reflex"

    def __init__(self, window=24):
        # Internal model of the world
        self.state = {"history": deque(maxlen=window), "last_action": None}

    def observe(self, sample):
        self.state["history"].append(sample)

    def _model(self, target_ms):
        h = list(self.state["history"])
        cpu = [x["cpu"] for x in h]
        return {
            "n": len(h),
            "mean_cpu": statistics.mean(cpu),
            "peak_cpu": max(cpu),
            "trough_cpu": min(cpu),
            "mean_mem": statistics.mean(x["mem"] for x in h),
            "trend": _slope(cpu[-6:]),                       # CPU points per hour, last 6h
            "frac_high": sum(c > 80 for c in cpu) / len(cpu),
            "frac_slow": sum(x["response_ms"] > target_ms for x in h) / len(h),
            "peak_sample": max(h, key=lambda x: x["cpu"]),
            "peak_hours": sum(c > 70 for c in cpu),
        }

    def decide(self, scenario):
        # Rebuild the percept stream (keeps last_action across calls)
        self.state["history"].clear()
        for s in scenario["history"]:
            self.observe(s)

        itype, count = scenario["instance_type"], scenario["count"]
        target = scenario["targets"]["response_ms"]
        m = self._model(target)
        last = self.state["last_action"]

        keep = candidate(scenario, "Keep current", itype, count)
        up1 = candidate(scenario, "Scale up one size", shift_size(itype, +1), count)
        down1 = candidate(scenario, "Scale down one size", shift_size(itype, -1), count)
        cands = [keep, up1, down1]

        # Peak-aware schedule: small baseline, more instances at peak
        pk = m["peak_sample"]
        peak_n = peak_count(count, m["peak_cpu"])
        base_n = max(1, -(-int(count * m["trough_cpu"]) // 60))   # ceil(count*trough/60)
        peak_h = m["peak_hours"] / m["n"] * HOURS_PER_MONTH
        sched_cost = round(CATALOG[itype]["hourly"] *
                           (base_n * (HOURS_PER_MONTH - peak_h) + peak_n * peak_h), 2)
        sched_est = estimate(scenario, itype, peak_n, cpu=pk["cpu"], mem=pk["mem"],
                             resp=pk["response_ms"])
        sched = {"label": f"Scheduled/auto scaling {base_n}->{peak_n} x {itype}",
                 "instance_type": itype, "count": peak_n, "baseline_count": base_n,
                 "cpu_pct": sched_est["cpu_pct"], "mem_pct": sched_est["mem_pct"],
                 "response_ms": sched_est["response_ms"], "monthly_cost": sched_cost,
                 "meets_response_target": sched_est["response_ms"] <= target}
        cands.append(sched)

        facts = [
            f"Internal model over {m['n']} samples: mean CPU {m['mean_cpu']:.0f}%, "
            f"peak {m['peak_cpu']}%, trough {m['trough_cpu']}%, "
            f"6h trend {m['trend']:+.1f} pts/h, {m['frac_high']:.0%} of samples >80% CPU.",
        ]

        # --- rules that read the internal state (first match wins) ---
        if m["peak_cpu"] >= 75 and m["trough_cpu"] <= 30:
            chosen, action = sched, "scheduled_scaling"
            why = (f"Volatile load (peak {m['peak_cpu']}% vs trough {m['trough_cpu']}%). "
                   f"The latest sample ({latest(scenario)['cpu']}% CPU) hides the peak, so a "
                   f"snapshot rule would wrongly downsize. Keep peak capacity available via "
                   f"scheduled/auto scaling instead.")
        elif m["frac_high"] >= 0.6 or m["frac_slow"] >= 0.6:
            chosen = next((candidate(scenario, f"Scale up to {t}", t, count)
                           for t in SIZE_ORDER[SIZE_ORDER.index(itype) + 1:]
                           if (c := candidate(scenario, "", t, count))["cpu_pct"] <= 70
                           and c["meets_response_target"]), up1)
            action = "scale_up"
            why = (f"Sustained pressure: {m['frac_high']:.0%} of samples >80% CPU and "
                   f"{m['frac_slow']:.0%} over the {target} ms target. Chose the smallest size "
                   f"giving CPU <=70% and meeting the target.")
            cands.append(chosen) if chosen not in cands else None
        elif m["trend"] >= 2 and latest(scenario)["cpu"] >= 60:
            chosen, action = up1, "scale_up"
            why = f"CPU rising {m['trend']:+.1f} pts/h and already >=60%: scale up before breach."
        elif m["mean_cpu"] < 20 and m["peak_cpu"] < 40 and m["mean_mem"] < 30:
            if last == "scale_up":
                chosen, action = keep, "keep"
                why = "Low use, but last action was a scale-up; hold to avoid flapping."
            else:
                chosen, action = down1, "scale_down"
                why = (f"Persistently low: mean CPU {m['mean_cpu']:.0f}%, peak {m['peak_cpu']}%, "
                       f"mean memory {m['mean_mem']:.0f}% - never needed the capacity.")
        else:
            chosen, action = keep, "keep"
            why = "No sustained high/low pattern or trend; keep current."

        self.state["last_action"] = action        # update internal state
        rec = recommendation_from(chosen, action)
        if action == "scheduled_scaling":
            rec["baseline_count"] = chosen["baseline_count"]

        reasoning = facts + [why,
                             f"Estimated result: CPU {chosen['cpu_pct']}%, "
                             f"response {chosen['response_ms']} ms, ${chosen['monthly_cost']}/month.",
                             f"Last action stored in state: {action} (previous: {last})."]
        monitoring = [
            f"Track a rolling {m['n']}h window of CPU, memory and response time.",
            "Alert on 6h CPU trend >= +2 pts/h or peak CPU > 80%.",
            "Review peak/off-peak schedule weekly; enforce a cooldown between scaling actions.",
        ]
        return result(self.name, scenario, cands, rec, reasoning, monitoring,
                      internal_state={k: (round(v, 1) if isinstance(v, float) else v)
                                      for k, v in m.items() if k != "peak_sample"})
