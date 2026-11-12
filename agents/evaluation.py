"""
CHECKING AN OPTION AT THE BUSIEST HOUR
======================================
In plain words: before recommending a set of servers, we ask "would it still cope at the
busiest hour of the day?" - not just at a quiet moment. This file does that check and also
estimates availability (how often the service stays up). Used by agents 3-6.

Technical notes:

common.estimate() scores a config against ONE sample (the latest by default).
For planning, these agents score every candidate against the PEAK sample, so a
config that looks fine at an off-peak hour cannot sneak through.

Availability model (simplified, documented in the README):
    availability = 1 - (1 - 0.995) ** n        n = instances running at the quietest time
    minus 0.3 points when estimated peak CPU > 85% (overload -> errors / timeouts)
With 2 instances at ~92% CPU this gives 99.70%, matching scenario A's observed value.
"""
import math

from scenarios import CATALOG, SIZE_ORDER
from .common import HOURS_PER_MONTH, candidate, capacity, estimate

SINGLE_INSTANCE_AVAILABILITY = 0.995
MEM_LIMIT_PCT = 85
PEAK_CPU_TARGET = 70        # size peak capacity to ~70% CPU
BASELINE_CPU_TARGET = 60    # size off-peak capacity to ~60% CPU
MAX_COUNT = 6


def peak_sample(scenario):
    return max(scenario["history"], key=lambda s: s["cpu"])


def trough_sample(scenario):
    return min(scenario["history"], key=lambda s: s["cpu"])


def peak_hours_fraction(scenario):
    h = scenario["history"]
    return sum(s["cpu"] > 70 for s in h) / len(h)


def availability(min_count, peak_cpu):
    a = (1 - (1 - SINGLE_INSTANCE_AVAILABILITY) ** min_count) * 100
    if peak_cpu > 85:
        a -= 0.3
    return round(a, 3)


def _add_checks(scenario, c, min_count):
    t = scenario["targets"]
    c["availability_pct"] = availability(min_count, c["cpu_pct"])
    c["meets_response_target"] = c["response_ms"] <= t["response_ms"]
    c["meets_availability"] = c["availability_pct"] >= t["availability_pct"]
    c["memory_ok"] = c["mem_pct"] <= MEM_LIMIT_PCT
    c["meets_goal"] = c["meets_response_target"] and c["meets_availability"] and c["memory_ok"]
    c["evaluated_at"] = "peak"
    return c


def fixed_at_peak(scenario, itype, count, label=None):
    pk = peak_sample(scenario)
    c = candidate(scenario, label or f"{count} x {itype}", itype, count,
                  cpu=pk["cpu"], mem=pk["mem"], resp=pk["response_ms"])
    c["action_type"] = "fixed"
    return _add_checks(scenario, c, count)


def scheduled_at_peak(scenario, itype, label=None):
    """Scheduled / auto scaling: a small baseline off-peak, more instances at peak."""
    pk, tr = peak_sample(scenario), trough_sample(scenario)
    cur_cap = capacity(scenario["instance_type"], scenario["count"])
    vcpus = CATALOG[itype]["vcpus"]
    peak_n = max(1, math.ceil(pk["cpu"] / 100 * cur_cap / (vcpus * PEAK_CPU_TARGET / 100)))
    base_n = max(1, math.ceil(tr["cpu"] / 100 * cur_cap / (vcpus * BASELINE_CPU_TARGET / 100)))
    # keep enough instances off-peak to meet the availability SLA (redundancy)
    while availability(base_n, 0) < scenario["targets"]["availability_pct"] and base_n < MAX_COUNT:
        base_n += 1
    peak_n = min(max(peak_n, base_n), 2 * MAX_COUNT)
    frac = peak_hours_fraction(scenario)
    cost = round(CATALOG[itype]["hourly"] * HOURS_PER_MONTH * (base_n * (1 - frac) + peak_n * frac), 2)
    est = estimate(scenario, itype, peak_n, cpu=pk["cpu"], mem=pk["mem"], resp=pk["response_ms"])
    c = {"label": label or f"Scheduled scaling {base_n}->{peak_n} x {itype}",
         "instance_type": itype, "count": peak_n, "baseline_count": base_n,
         "cpu_pct": est["cpu_pct"], "mem_pct": est["mem_pct"],
         "response_ms": est["response_ms"], "monthly_cost": cost, "action_type": "scheduled"}
    return _add_checks(scenario, c, base_n)


def all_candidates(scenario):
    # Every option we can choose from: each server size with 1 to 6 servers,
    # plus 'scheduled scaling' (fewer servers at night, more during busy hours).
    """The shared search space: every size x 1..MAX_COUNT, plus scheduled scaling per size."""
    out = [fixed_at_peak(scenario, t, n) for t in SIZE_ORDER for n in range(1, MAX_COUNT + 1)]
    if peak_hours_fraction(scenario) > 0:          # only offer schedules when there is a peak
        out += [scheduled_at_peak(scenario, t) for t in SIZE_ORDER]
    return out


def classify_action(scenario, c):
    # Give the change a simple name: keep / scale_up / scale_down / scale_out / scheduled_scaling
    if c.get("action_type") == "scheduled":
        return "scheduled_scaling"
    cur_t, cur_n = scenario["instance_type"], scenario["count"]
    if c["instance_type"] == cur_t and c["count"] == cur_n:
        return "keep"
    cur_cap, new_cap = capacity(cur_t, cur_n), capacity(c["instance_type"], c["count"])
    if new_cap > cur_cap:
        return "scale_out" if c["count"] > cur_n else "scale_up"
    return "scale_down"


def recommendation(c, action):
    rec = {"action": action, "instance_type": c["instance_type"], "count": c["count"],
           "est_cpu_pct": c["cpu_pct"], "est_response_ms": c["response_ms"],
           "est_monthly_cost": c["monthly_cost"], "est_availability_pct": c.get("availability_pct")}
    if "baseline_count" in c:
        rec["baseline_count"] = c["baseline_count"]
    return rec


def tradeoffs(scenario, c):
    cur = fixed_at_peak(scenario, scenario["instance_type"], scenario["count"])
    t = scenario["targets"]
    d = c["monthly_cost"] - cur["monthly_cost"]
    return [
        f"Cost: ${c['monthly_cost']}/month vs ${cur['monthly_cost']} now ({'+' if d >= 0 else '-'}${abs(d):.2f}).",
        f"Peak response: {c['response_ms']} ms vs {cur['response_ms']} ms now (target {t['response_ms']} ms).",
        f"Availability: {c['availability_pct']}% vs {cur['availability_pct']}% now (SLA {t['availability_pct']}%).",
        f"Peak memory: {c['mem_pct']}% (limit {MEM_LIMIT_PCT}%).",
    ]
