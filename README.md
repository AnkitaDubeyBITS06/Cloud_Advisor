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

## Step 1 - Setup (Windows, Python 3.11+)

**1a. Install the Python packages**

```powershell
cd cloud_advisor
python -m pip install -r requirements.txt
```

**1b. Install Ollama** from https://ollama.com/download (the llama icon appears in the system tray).

**1c. If PowerShell says `ollama` is not recognised**, add Ollama to the PATH:

```powershell
# this terminal only
$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"

# permanent (run once, then close and reopen PyCharm)
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:LOCALAPPDATA\Programs\Ollama", "User")
```

**1d. Download the model** (only needed once) and check it is there:

```powershell
ollama pull qwen2.5:3b
ollama list
```

`qwen2.5:3b` is small and fast enough on a laptop without a GPU. On a faster PC you can use `qwen3:8b`
(type it in the sidebar, or run with `--model qwen3:8b`).

---

## Step 2 - Run (tests first, then the UI)

Run in this order:

```powershell
python quick_test.py          # 1. quick check that everything works (5 classical agents, ~10 s, no Ollama needed)
python quick_test.py --llm    # 2. optional: also test the LLM agent (Ollama running, ~10 min on CPU)
streamlit run app.py          # 3. open the UI: pick a scenario, click "Run all agents"
```

Don't run step 2 and step 3 at the same time - they compete for the CPU.

**Optional settings** - only change these if the defaults don't suit your PC. Set them **in the same terminal,
before** step 2 or 3; they last only for that terminal window.

| Setting | What it does | Default | When to use |
|---|---|---|---|
| `$env:OLLAMA_MODEL = "qwen3:8b"` | Which Ollama model the LLM agent uses | `qwen2.5:3b` | To try a bigger model on a faster PC |
| `$env:LLM_REFLECTIONS = "1"` | How many times the code sends the LLM's draft back to fix problems | `2` | Set `1` or `0` if the LLM is too slow |
| `$env:OLLAMA_NUM_CTX = "8192"` | How much text the model can read at once | `4096` | Only if answers get cut off; a different value makes Ollama reload the model |
| `$env:OLLAMA_TIMEOUT = "1200"` | Seconds one LLM step may take before giving up (stops it hanging forever) | `600` (10 min) | Increase on a very slow PC; decrease (e.g. `"180"`) to fail faster |

Example: `$env:LLM_REFLECTIONS = "1"` then `streamlit run app.py`.

---

## Step 3 - Using the UI

0. **View** (top of the sidebar) - *All scenarios on one page* shows A, B and C side by side, one summary
   table of every agent across all three scenarios, and the cheapest working answer per scenario.
   *One scenario in detail* shows each agent's full reasoning. Results run in one view are reused in the other.
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

### When to click "Reset experience to seed"
The Learning agent's memory (`experience.json`) carries over between runs - every run adds one success or
failure. **Reset experience to seed** puts it back to the starting values in `experience_seed.json`.

| Situation | Reset? | Why |
|---|---|---|
| Final run for screenshots / submission | **Yes, first** | Results match the README and `test_results/`; the before -> after table starts from known values |
| Demonstrating that the agent learns | **No** | Run the same scenario several times and watch the counts grow and its choice change |
| Learning agent gives an unexpected answer | **Yes** | Earlier runs may have shifted its counts |

Only the Learning agent is affected - the other agents have no memory.

---

## Step 4 - Screenshots

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

## How fairness, learning and evidence checking work

**Same input for every agent.** Each agent gets its own identical copy of the scenario. A fingerprint
(a short code computed from the data, shown above the comparison table) is checked before and after
every agent, proving no agent saw different or changed data.

**Same yardstick.** Every recommendation is re-checked at the **busiest hour** with the same cost and
response-time model, so the comparison table is fair even for agents that only looked at one reading.

**How the Learning agent learns** (`agents/learning_agent.py`, experience stored in `experience.json`):
1. *Performance element* - recognises the situation (busy / idle / up-and-down) and picks the action
   with the best past success rate.
2. *Problem generator* - now and then tries a different action to gain new experience.
3. *Critic* - judges the outcome: are all targets met without wasting money?
4. *Learning element* - adds one success or failure to the counts, so the next decision can change.

The UI shows the counts **before -> after** each run. `test_results/learning_curve.md` starts the agent
with **no experience**: it succeeds in 1 of 3 scenarios in round 1 and 3 of 3 from round 6, once its
counts point to the right action for each situation (the few later misses are deliberate exploration steps, marked `*`).

**How the LLM's evidence is checked** (`agents/llm_agent.py`):
1. The LLM must call at least two tools before answering.
2. Code checks every number it quotes against the tool results, and that it evaluated its own recommendation.
3. Problems are sent back for revision (up to 2 times).
4. If problems remain, the answer is flagged **Needs human review**.

---

## Rubric coverage

| Criterion | Where it is covered |
|---|---|
| Five classical agents (separate, each with its own decision mechanism) | `agents/simple_reflex.py`, `model_based.py`, `goal_based.py`, `utility_based.py`, `learning_agent.py`; agent table at the top |
| LLM agent and tool calling (local Ollama via LangChain, >= 2 tools, evidence used) | `agents/llm_agent.py`; sections *LLM tools* and *How ... evidence checking work* |
| Shared scenarios and testing (3+ scenarios, same input, edge case) | `scenarios.py` (A critical, B normal, C edge); fingerprint check; `quick_test.py` - 19 checks in `test_results/checks.md` |
| Streamlit UI and comparison | `app.py`; *Step 3 - Using the UI*; screenshots 01-05 |
| Learning and evaluation (outcome history, evidence checked, limitations) | Learning agent section above, `test_results/learning_curve.md`, screenshot 08; LLM evidence check, screenshots 06-07; *Limitations* |
| Documentation and demonstration | This README (setup, run, UI guide, results, troubleshooting), `screenshots/`, `test_results/` |

---

## Troubleshooting (problems we hit and how we fixed them)

| Problem | Cause | Fix |
|---|---|---|
| Ollama install fails: *"file is being used by another process"* | An earlier installer was still open or downloading | Close it, then `Get-Process OllamaSetup -ErrorAction SilentlyContinue \| Stop-Process -Force`, delete `$env:TEMP\OllamaSetup.exe` and install again - or download the installer from https://ollama.com/download/windows |
| `ollama` is not recognised (happens in every new PyCharm terminal) | The Ollama folder is not on the terminal's PATH | **This terminal only:** `$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"` - **Permanent (run once, then restart PyCharm):** `[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:LOCALAPPDATA\Programs\Ollama", "User")`. Note: the app and `quick_test.py` don't need the `ollama` command (Python talks to Ollama at `http://localhost:11434`); it is only needed for `ollama ps / list / pull`. The model only needs to be pulled once. |
| `pip install` didn't go into the project | The old `.venv` was copied from another project and points to the wrong folder | Create a new interpreter in PyCharm (Python 3.14 is fine) and install with `python -m pip install -r requirements.txt` |
| LLM very slow (>5 min per step) with `qwen3:8b` / `qwen3:4b` | Laptop runs the model on CPU only (`ollama ps` -> `100% CPU`); Qwen3 also "thinks" silently before answering | Use `qwen2.5:3b` (no hidden thinking, ~10-60 s per step). Plug in the charger, close heavy apps |
| Run hangs; `ollama ps` shows `Stopping...` | Ollama on Windows got stuck unloading/reloading the model mid-run | Ctrl+C, then restart Ollama: `Get-Process ollama* \| Stop-Process -Force`, start it again from the Start menu, run again. The code now keeps the model loaded (`keep_alive` 30 min) and uses Ollama's default context size (4096) so it doesn't reload, and a timeout stops endless waiting |
| Code changes "disappeared" / old version keeps coming back | PyCharm had the old file open and its **autosave** wrote the old copy over the new one | Close all editor tabs (**Don't Save**), then **File -> Reload All from Disk** (choose *Load File System Changes*). Turn off autosave: **File -> Settings -> Appearance & Behavior -> System Settings -> untick "Save files if the IDE is idle"**. Safest: close PyCharm while files are being updated and run the app from a normal Windows PowerShell |
| Small LLM ignores review feedback (B, C) | A 3B model is not strong enough to always correct itself | Expected - the answer is flagged **Needs human review** instead of being trusted |
| UI says "Running agents..." for minutes | Only the LLM is slow; it runs several steps per scenario | Watch the terminal for `[LLM] step ...` lines; use `$env:LLM_REFLECTIONS = "1"` to make it faster |

---

## Limitations
- Data, prices and the response-time / availability formulas are simplified simulations.
- The Learning agent's history is small and its outcomes are judged by the same simulator, not real measurements.
- Simple Reflex, Model-Based and Learning use one-step changes, so they don't always find the cheapest option.
- LLM answers vary between runs. The 3B model runs on CPU and often ignores review feedback (B and C);
  the review catches this and flags it, but cannot force a correct answer. A larger model on a GPU is likely to do better.
