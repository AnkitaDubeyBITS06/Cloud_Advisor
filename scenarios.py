"""
THE TEST DATA
=============
In plain words: this file describes three made-up cloud situations (A, B and C) and
the price list of the servers we can choose from.

Every agent is given exactly the same situation, so we can compare their advice fairly.

Each situation contains:
  - what is running today   (e.g. 2 "large" servers)
  - the targets to meet     (response time and availability)
  - 24 hourly readings      (how busy the CPU and memory were, how fast the service responded)
"""

# Price list of server sizes. vcpus = processing power, mem_gb = memory,
# hourly = what one server costs per hour in US dollars (made-up prices).
CATALOG = {
    "small":   {"vcpus": 2,  "mem_gb": 4,  "hourly": 0.05},
    "medium":  {"vcpus": 4,  "mem_gb": 8,  "hourly": 0.10},
    "large":   {"vcpus": 8,  "mem_gb": 16, "hourly": 0.20},
    "xlarge":  {"vcpus": 16, "mem_gb": 32, "hourly": 0.40},
    "2xlarge": {"vcpus": 32, "mem_gb": 64, "hourly": 0.80},
}
SIZE_ORDER = ["small", "medium", "large", "xlarge", "2xlarge"]   # smallest to biggest


def _history(cpus, mems, base_ms):
    """Build 24 hourly readings.
    The busier the CPU, the slower the response (like a queue at a shop:
    the fuller it gets, the longer everyone waits)."""
    return [
        {"hour": h, "cpu": c, "mem": m,
         "response_ms": round(base_ms / (1 - c / 100))}
        for h, (c, m) in enumerate(zip(cpus, mems))
    ]


# Scenario C: quiet for 8 hours, very busy for 9 hours, quiet again at the end.
# The LAST reading is quiet, which tricks agents that only look at the latest number.
_C_CPU = [12]*8 + [45] + [92]*9 + [50] + [14]*5          # 24 hours, ends off-peak
_C_MEM = [20]*8 + [40] + [70]*9 + [40] + [22]*5

SCENARIOS = {
    "A": {
        "id": "A",
        "name": "A - Sustained high CPU, response time above target",
        "type": "critical",
        "instance_type": "large", "count": 2,
        "targets": {"response_ms": 200, "availability_pct": 99.9},
        "current_availability_pct": 99.7,
        "history": _history(
            [88, 90, 91, 92, 93, 91, 90, 92, 94, 93, 91, 90,
             92, 93, 95, 94, 92, 91, 90, 92, 93, 94, 92, 91],
            [70]*24, base_ms=30),
    },
    "B": {
        "id": "B",
        "name": "B - Low utilisation, expensive instance",
        "type": "normal",
        "instance_type": "xlarge", "count": 2,
        "targets": {"response_ms": 200, "availability_pct": 99.9},
        "current_availability_pct": 99.99,
        "history": _history(
            [10, 9, 11, 12, 10, 8, 9, 12, 14, 13, 12, 11,
             10, 12, 13, 14, 12, 11, 10, 9, 10, 11, 9, 10],
            [15, 14, 16, 17, 15, 13, 14, 17, 18, 17, 16, 15,
             15, 16, 17, 18, 16, 15, 14, 14, 15, 16, 14, 15],
            base_ms=30),
    },
    "C": {
        "id": "C",
        "name": "C - Sharp peak / off-peak swings",
        "type": "edge",
        "instance_type": "large", "count": 2,
        "targets": {"response_ms": 200, "availability_pct": 99.9},
        "current_availability_pct": 99.85,
        "history": _history(_C_CPU, _C_MEM, base_ms=30),
    },
}
