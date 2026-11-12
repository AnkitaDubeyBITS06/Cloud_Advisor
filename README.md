# Cloud Resource and Cost Optimization Advisor

Recommends cloud server configurations (instance size and count) that balance
**response time, availability and cost**, using simulated workload metrics.
It only gives advice - it never changes real cloud resources.

Six agents receive **the same scenario** and their decisions are compared side by side.

| Agent | How it decides |
|---|---|
| Simple Reflex | If-then rules on the latest reading only |
| Model-Based Reflex | Rules on an internal memory of the last 24 hours (peak, trough, trend, last action) |
| Goal-Based | Searches all options and picks the cheapest one that meets every target |
| Utility-Based | Scores options on performance, availability and cost; picks the highest score |
| Learning | Performance element picks the action that worked best before; critic judges the outcome; learning element updates success/failure counts; problem generator explores now and then |
| LLM (Ollama) | Local Qwen model (`qwen2.5:3b`) via LangChain tool calling (ReAct). Code reviews its draft and asks it to revise (Reflection); unresolved problems are flagged for a human (human in the loop) |

---

## Folder structure

```
cloud_advisor/
├── scenarios.py          # scenarios A, B, C + instance prices
├── quick_test.py         # runs all agents, checks the results, writes test_results/
├── app.py                # Streamlit UI
├── requirements.txt
├── experience_seed.json  # starting experience for the Learning agent
├── test_results/         # output of quick_test.py
├── screenshots/          # UI screenshots
└── agents/
    ├── common.py         # shared cost / response-time model and output format
    ├── simple_reflex.py
    ├── model_based.py
    ├── goal_based.py
    ├── utility_based.py
    ├── learning_agent.py
    ├── llm_agent.py      # LLM agent: tools, evidence check, reflection
    └── evaluation.py     # checks every option at the busiest hour
```

---

## Setup (Windows, Python 3.11+)

```powershell
cd cloud_advisor
python -m pip install -r requirements.txt
```

Install Ollama from https://ollama.com/download.

If PowerShell says `ollama` is not recognised, add Ollama to the PATH first:

```powershell
# this terminal only
$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"

```

Then download the model (only needed once) and check it is there:

```powershell
ollama pull qwen2.5:3b
ollama list
```
---

## Run

```powershell
python quick_test.py          # 1. quick check that everything works (5 classical agents, ~10 s, no Ollama needed)
python quick_test.py --llm    # 2. optional: also test the LLM agent (Ollama running, ~10 min on CPU)
streamlit run app.py          # 3. open the UI: pick a scenario, click "Run all agents"
```

Don't run step 2 and step 3 at the same time - they compete for the CPU.

**Optional settings** - only change these if the defaults don't suit your PC. Set them **in the same terminal,
before** step 2 or 3; they last only for that terminal window.

| Optional Setting | What it does | Default | When to use |
|---|---|---|---|
| `$env:OLLAMA_MODEL = "qwen3:8b"` | Which Ollama model the LLM agent uses | `qwen2.5:3b` | To try a bigger model on a faster PC |
| `$env:LLM_REFLECTIONS = "1"` | How many times the code sends the LLM's draft back to fix problems | `2` | Set `1` or `0` if the LLM is too slow |
| `$env:OLLAMA_NUM_CTX = "4096"` | How much text the model can read at once (memory use) | `8192` | If the PC is short of RAM |
| `$env:OLLAMA_TIMEOUT = "1200"` | Seconds one model call may take before giving up | `600` | Rarely needed |

Example: `$env:LLM_REFLECTIONS = "1"` then `streamlit run app.py`.

---

## Using the UI

1. **Sidebar** - choose the scenario, the Ollama model, the Utility agent's weights and the Learning agent's settings.
   Click **Reset experience to seed**, then **Run all agents**.
2. **Scenario overview** - current config, monthly cost, peak response vs target, availability vs SLA,
   and 24-hour charts. *Raw scenario input* shows the exact data every agent receives.
3. **Comparison across agents** - one row per agent: action, config, cost, response and CPU at the
   busiest hour, availability, whether all targets are met, and whether a human review is needed.
4. **Why the decisions differ** - plain-English explanation of each agent's choice.
5. **Agent tabs** - for each agent: current-state summary, candidate configurations, reasoning and
   trade-offs, recommendation and monitoring plan. Extra detail per agent:
   - *Model-Based*: internal state
   - *Utility-Based*: score of each option
   - *Learning*: its four components and the experience counts **before -> after** the run
   - *LLM*: every tool call and result, the evidence check, reflection rounds, and a
     **Needs human review** flag if problems remain

---

## Scenarios

| | Type | Situation | Good answer |
|---|---|---|---|
| A | critical | CPU always ~92%, response 600 ms vs 200 ms target | Add capacity |
| B | normal | CPU ~11%, expensive servers ($584/month) | Downsize to save money |
| C | edge | Idle at night, overloaded in the day; the latest reading is off-peak | Scheduled scaling |

---

## LLM tools

| Tool | Returns |
|---|---|
| `get_resource_metrics()` | Current config, 24-hour CPU / memory / response time, peak and trough |
| `get_service_level_targets()` | Response-time target, availability SLA, current availability |
| `get_scaling_policy()` | Allowed instance sizes and prices, instance limits, CPU thresholds |
| `get_cost_estimate(instance_type, count, scheduled)` | Monthly cost, CPU, memory, response time and availability at the busiest hour, and whether targets are met |

The LLM must call at least two tools. Code then checks that every number it quotes came from a tool
result and that it evaluated the config it recommends (**evidence check**).

---

## Results (from `quick_test.py --llm` and the Streamlit UI)

| Agent | A | B | C |
|---|---|---|---|
| Simple Reflex | 2 x xlarge, $584 | 2 x large, $292 | 2 x medium - **fails at peak** |
| Model-Based | 2 x xlarge, $584 | 2 x large, $292 | scheduled 1->3 large - misses availability |
| Goal-Based | 5 x medium, $365 | 4 x small, $146 | scheduled 2->11 small, $196 |
| Utility-Based | 5 x medium, $365 | 4 x small, $146 | scheduled 2->11 small, $196 |
| Learning | 2 x xlarge, $584 | 2 x large, $292 | scheduled 2->3 large, $347 |
| LLM (qwen2.5:3b) | 2 x xlarge, $584 - passed review | keeps 2 x xlarge, $584 - **flagged for human review** (a $292 option it checked also works) | keeps 2 x large, $292 - fails targets at peak, **flagged for human review** |

Full details per scenario: `test_results/scenario_A.md`, `scenario_B.md`, `scenario_C.md`;
summary: `test_results/summary.md`; all checks: `test_results/checks.md` (19/19 passed).

### Why the decisions differ
- **Simple Reflex** only sees the last reading. In C that reading is at night, so it downsizes and fails at the next peak.
- **Model-Based** sees the whole day, so it spots the peak in C, but keeps only one server at night, which risks availability.
- **Goal-Based** and **Utility-Based** compare every option, so they find the cheapest one that works.
- **Learning** repeats what worked before, so it is safe but not always the cheapest.
- **LLM** collects evidence with tools (ReAct). Code reviews its draft (Reflection): it must evaluate its own
  recommendation, meet the targets and quote only tool numbers. The small 3B model often ignores the review,
  so if problems remain after the revisions the answer is flagged **Needs human review** instead of being trusted.

---

## Screenshots

| File | Shows |
|---|---|
| `screenshots/01_scenario_A_overview.png` | Scenario A overview and charts |
| `screenshots/02_comparison_A.png` | Comparison table and explanation - A |
| `screenshots/03_agent_reasoning_A.png` | An agent's reasoning, candidates and monitoring plan |
| `screenshots/04_comparison_B.png` | Comparison - B |
| `screenshots/05_comparison_C.png` | Comparison - C (edge case) |
| `screenshots/06_llm_tool_calls.png` | LLM tool calls and evidence check |
| `screenshots/07_llm_reflection.png` | LLM reflection and "Needs human review" |
| `screenshots/08_learning_agent.png` | Learning agent components and experience before -> after |
| `screenshots/09_quick_test.png` | `quick_test.py --llm` - 19/19 checks passed |

---

## Limitations
- Data, prices and the response-time / availability formulas are simplified simulations.
- The Learning agent's history is small and its outcomes are judged by the same simulator, not real measurements.
- Simple Reflex, Model-Based and Learning use one-step changes, so they don't always find the cheapest option.
- LLM answers vary between runs. The 3B model runs on CPU and often ignores review feedback (B and C);
  the review catches this and flags it, but cannot force a correct answer. A larger model on a GPU is likely to do better.
