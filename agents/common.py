"""
SHARED HELPERS
==============
In plain words: small calculators that every agent uses, so they all do the maths the same way.

  - monthly_cost()  -> how much a set of servers costs per month
  - estimate()      -> "if we switched to these servers, how busy would they be and how fast
                        would the service respond?"
  - result()        -> the one answer format every agent must return
                        (summary, options considered, recommendation, reasoning, monitoring plan)
"""
import math
from scenarios import CATALOG, SIZE_ORDER

HOURS_PER_MONTH = 730   # average number of hours in a month


def latest(scenario):
    # The most recent hourly reading
    return scenario["history"][-1]


def capacity(itype, count):
    # Total processing power = power of one server x number of servers
    return CATALOG[itype]["vcpus"] * count


def monthly_cost(itype, count):
    return round(CATALOG[itype]["hourly"] * count * HOURS_PER_MONTH, 2)


def shift_size(itype, step):
    """Move up (+1) or down (-1) the catalog; clamps at the ends."""
    i = SIZE_ORDER.index(itype) + step
    return SIZE_ORDER[max(0, min(len(SIZE_ORDER) - 1, i))]


def estimate(scenario, itype, count, cpu=None, mem=None, resp=None):
    """Estimate cpu / memory / response time if the workload ran on itype x count.
    Uses the latest sample unless cpu/mem/resp are given (e.g. a peak sample).
    Response time uses base = resp*(1-cpu); new resp = base/(1-new_cpu)."""
    s = latest(scenario)
    cpu = s["cpu"] if cpu is None else cpu
    mem = s["mem"] if mem is None else mem
    resp = s["response_ms"] if resp is None else resp
    cur_cap = capacity(scenario["instance_type"], scenario["count"])
    new_cap = capacity(itype, count)
    new_cpu = min(99.0, cpu * cur_cap / new_cap)
    used_gb = mem / 100 * CATALOG[scenario["instance_type"]]["mem_gb"] * scenario["count"]
    new_mem = min(100.0, used_gb / (CATALOG[itype]["mem_gb"] * count) * 100)
    base = resp * (1 - cpu / 100)
    return {
        "cpu_pct": round(new_cpu, 1),
        "mem_pct": round(new_mem, 1),
        "response_ms": round(base / (1 - new_cpu / 100)),
        "monthly_cost": monthly_cost(itype, count),
    }


def candidate(scenario, label, itype, count, **kw):
    est = estimate(scenario, itype, count, **kw)
    est.update({
        "label": label, "instance_type": itype, "count": count,
        "meets_response_target": est["response_ms"] <= scenario["targets"]["response_ms"],
    })
    return est


def summarize(scenario):
    s = latest(scenario)
    t = scenario["targets"]
    return (f"{scenario['name']}: running {scenario['count']} x {scenario['instance_type']} "
            f"(${monthly_cost(scenario['instance_type'], scenario['count'])}/month). "
            f"Latest CPU {s['cpu']}%, memory {s['mem']}%, response {s['response_ms']} ms "
            f"(target {t['response_ms']} ms), availability "
            f"{scenario['current_availability_pct']}% (SLA {t['availability_pct']}%).")


def result(agent, scenario, candidates, recommendation, reasoning, monitoring_plan, **extra):
    """The single output format every agent must return."""
    out = {
        "agent": agent,
        "scenario": scenario["id"],
        "summary": summarize(scenario),
        "candidates": candidates,
        "recommendation": recommendation,   # dict: action, instance_type, count, est_*
        "reasoning": reasoning,             # list[str]
        "monitoring_plan": monitoring_plan, # list[str]
    }
    out.update(extra)
    return out


def recommendation_from(cand, action):
    return {"action": action, "instance_type": cand["instance_type"], "count": cand["count"],
            "est_cpu_pct": cand["cpu_pct"], "est_response_ms": cand["response_ms"],
            "est_monthly_cost": cand["monthly_cost"]}


def peak_count(count, peak_cpu, target_cpu=70):
    return max(1, math.ceil(count * peak_cpu / target_cpu))
