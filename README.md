# Cloud Resource and Cost Optimization Advisor

> **Evaluators:** every screenshot, with captions and a short summary of the results, is in
> **[`screenshots/Cloud_Advisor_Results_and_Screenshots.docx`](screenshots/Cloud_Advisor_Results_and_Screenshots.docx)**.
> That one document is easier to follow than the individual image files.

## What this project does

Picture a company running its website on rented cloud servers. Too few servers and the site gets slow or
goes down. Too many and money is wasted. This advisor looks at a day of **simulated** server readings
(CPU, memory and response time, once an hour) and suggests how many servers to run, and how big.
It aims for a good balance of **speed, availability and cost**.

It only gives advice. It never touches real cloud resources.

Six different agents get **exactly the same data** and make their own call. Their answers are then
compared side by side. Every agent reports the same five things:
a summary of the current state, the options it considered, the trade-offs, its recommendation, and what to monitor next.

| Agent | How it thinks |
|---|---|
| **Simple Reflex** | Looks only at the latest reading and applies an if-then rule |
| **Model-Based Reflex** | Remembers the whole day (peak, quiet time, trend) and applies rules to that |
| **Goal-Based** | Tries every option and picks the cheapest one that meets all the targets |
| **Utility-Based** | Gives each option a score for speed, availability and cost, and picks the best score |
| **Learning** | Repeats what worked before, checks how it went, and updates its success/failure counts |
| **LLM (Ollama)** | A small local AI model (`qwen2.5:3b`) that gathers facts with tools, then writes an answer. The code reviews that answer, sends it back if something is wrong, and flags it for a human if problems remain |

---

## What's in the submission

| Required item | Where it is |
|---|---|
| Five classical agents | `agents/simple_reflex.py`, `model_based.py`, `goal_based.py`, `utility_based.py`, `learning_agent.py` |
| LLM agent | `agents/llm_agent.py` (4 tools, evidence check, review loop) |
| Streamlit UI | `app.py` |
| `requirements.txt` and README | this folder |
| Test results for scenarios A, B, C | `test_results/` (19 of 19 checks passed) |
| Screenshots | `screenshots/Cloud_Advisor_Results_and_Screenshots.docx` |
| Comparison table and why the decisions differ | [Results](#results) below, `test_results/summary.md`, and the UI |

```
cloud_advisor/
├── app.py                # the Streamlit UI
├── quick_test.py         # runs every agent, checks the answers, writes test_results/
├── scenarios.py          # scenarios A, B, C and server prices
├── experience_seed.json  # the Learning agent's starting memory
├── diagnose_ollama.py    # helper for finding Ollama problems
├── requirements.txt
├── test_results/
├── screenshots/
└── agents/
    ├── common.py         # shared cost and response-time maths
    ├── evaluation.py     # checks every option at the busiest hour
    └── simple_reflex.py, model_based.py, goal_based.py, utility_based.py, learning_agent.py, llm_agent.py
```

---

## How to run it (Windows)

### 1. One-time setup

```powershell
cd cloud_advisor
python -m pip install -r requirements.txt
```

Install **Ollama** from https://ollama.com/download, then download the model once:

```powershell
ollama pull qwen2.5:3b
```

If PowerShell says `ollama` is not recognised, run this and try again:
`$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"`

### 2. Run

First check that Ollama is running: you should see the llama icon in the system tray.
If it's not there, open **Ollama** from the Start menu.

```powershell
python quick_test.py          # quick check of the 5 classical agents (about 10 seconds, no Ollama needed)
python quick_test.py --llm    # includes the LLM agent (about 10 minutes on a laptop CPU)
streamlit run app.py          # opens the UI in your browser
```

Two things to keep in mind:
- Run the test and the UI one after the other, not at the same time, because they fight over the CPU.
- Both test commands **overwrite** `test_results/`. Running without `--llm` wipes the LLM results, so make
  `python quick_test.py --llm` the last test you run.

**Optional settings.** You only need these if the defaults are too slow or too small for your PC. Set them in the
same terminal before running; they only last for that window.

| Setting | Default | Use it when |
|---|---|---|
| `$env:OLLAMA_MODEL = "qwen3:8b"` | `qwen2.5:3b` | You have a faster PC and want a bigger model |
| `$env:LLM_REFLECTIONS = "1"` | `2` | The LLM is too slow (this sets how often it can be sent back to revise) |
| `$env:OLLAMA_TIMEOUT = "1200"` | `600` seconds | A single LLM step needs longer on a very slow PC |
| `$env:OLLAMA_NUM_CTX = "8192"` | `4096` | The LLM's answers get cut off |

### 3. Using the UI

- **Sidebar:** pick the view, scenario, model and agent settings. Click **Reset experience to seed**, then **Run all agents**.
- **All scenarios on one page:** A, B and C side by side, one table of every agent's answer, and the cheapest working answer for each scenario.
- **One scenario in detail:** the scenario's charts, a comparison table, a plain-English "why the decisions differ", and a tab per agent with its full reasoning.
  The LLM tab shows every tool call, the evidence check, the revision rounds and the **Needs human review** flag.

**About "Reset experience to seed":** the Learning agent remembers every run in `experience.json`.
Reset it before your final run so the results match `test_results/`. Leave it alone if you want to watch
the agent learn over several runs. No other agent has a memory.

---

## The three scenarios

| | Type | What's going on | A sensible answer |
|---|---|---|---|
| **A** | Critical | CPU around 92% all day; responses take 600 ms against a 200 ms target | Add capacity |
| **B** | Normal | CPU around 11% on expensive servers ($584 a month) | Downsize and save money |
| **C** | Edge case | Quiet at night, overloaded by day, and the latest reading happens to be at night | Scale up by day, down at night |

---

## Results

| Agent | A | B | C |
|---|---|---|---|
| Simple Reflex | 2 x xlarge, $584 | 2 x large, $292 | 2 x medium, **fails at peak** |
| Model-Based | 2 x xlarge, $584 | 2 x large, $292 | scheduled 1->3 large, misses availability |
| Goal-Based | 5 x medium, $365 | 4 x small, $146 | scheduled 2->11 small, $196 |
| Utility-Based | 5 x medium, $365 | 4 x small, $146 | scheduled 2->11 small, $196 |
| Learning | 2 x xlarge, $584 | 2 x large, $292 | scheduled 2->3 large, $347 |
| LLM (qwen2.5:3b) | scheduled 2->2 xlarge, $584, *flagged* | 2 x xlarge, $584, *flagged* | 2 x xlarge, $584, *flagged* |

Costs are per month. Full details are in `test_results/scenario_A.md`, `scenario_B.md`, `scenario_C.md` and `summary.md`.

### Why the answers differ

- **Simple Reflex** only sees the last reading. In C that reading is at night, so it shrinks the servers and then fails when the day's rush hits.
- **Model-Based** sees the whole day and notices C's daytime peak, but keeps just one server at night, which puts availability at risk.
- **Goal-Based** and **Utility-Based** check every option, so they find the cheapest setup that actually works.
- **Learning** sticks with what has worked before. That's safe, but not always the cheapest.
- **LLM** meets the targets every time, but it tends to pick pricier options and doesn't always take the reviewer's hint about cheaper ones.
  So the code marks its answer **Needs human review** instead of trusting it. Its answers also vary a bit from run to run.

---

## How the key parts work

**Fair comparison.** Each agent gets its own copy of the same data. A fingerprint of the data is checked
before and after each agent to prove nobody saw different or changed input. Every answer is then
re-checked at the **busiest hour** using the same maths, so even agents that looked at only one reading are judged fairly.

**How the Learning agent learns.** It has four parts:
1. **Performance element:** recognises the situation (busy, idle or up-and-down) and picks the action with the best track record.
2. **Problem generator:** now and then tries something different, just to learn.
3. **Critic:** judges the result. Were all targets met without wasting money?
4. **Learning element:** records a success or failure so the next decision can improve.

Starting from zero, it gets 1 of 3 scenarios right in round 1 and all 3 from round 6 (see `test_results/learning_curve.md`).

**How the LLM is kept honest.** It has four tools:

| Tool | What it returns |
|---|---|
| `get_resource_metrics()` | The current setup and the 24-hour readings |
| `get_service_level_targets()` | The response-time target and the availability SLA |
| `get_scaling_policy()` | Allowed server sizes, prices and limits |
| `get_cost_estimate(instance_type, count, scheduled)` | Cost and performance of any option at the busiest hour |

It must call at least two tools before answering. The code then checks that every number it quotes came
from a tool, and that its recommendation really meets the targets. A reviewer step also runs `get_cost_estimate`
itself to look for cheaper options that work. If something is wrong, the answer goes back for revision
(up to 2 times). Anything still unresolved is flagged **Needs human review**.

---

## If something goes wrong

| Problem | What to do |
|---|---|
| `ollama` is not recognised | `$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"`. The app itself doesn't need this command; only `ollama pull/list/ps` do |
| `ConnectError ... actively refused it` | Ollama isn't running (common after a restart). Open it from the Start menu and wait for the tray icon |
| The LLM is very slow | Use `qwen2.5:3b`, plug in the charger, close heavy apps, or set `$env:LLM_REFLECTIONS = "1"` |
| It hangs and `ollama ps` shows `Stopping...` or no model | Close the terminal, then run `Get-Process ollama* \| Stop-Process -Force`, reopen Ollama and run again. If it keeps happening, restart the PC. `python diagnose_ollama.py` shows exactly which step hangs |
| Every Ollama call is ~10 seconds slow | `localhost` tries IPv6 first on Windows. The code already uses `127.0.0.1`; if you set `OLLAMA_BASE_URL` yourself, use that too |
| Ctrl+C doesn't stop it | Close the terminal window, or end **Python** in Task Manager |
| `[LLM] step` lines appear twice | Two runs are going at once. Close extra `localhost:8501` tabs and click **Run** only once |
| My code changes keep disappearing | PyCharm's autosave wrote an old copy back. Close the tabs without saving, use **File -> Reload All from Disk**, and turn off *Save files if the IDE is idle* |
| `pip install` went to the wrong place | The `.venv` was copied from another project. Create a new interpreter in PyCharm and install again |
| Ollama installer says the file is in use | Close the old installer, delete `$env:TEMP\OllamaSetup.exe`, and download it again |
| `git push` fails with 403 | Windows saved a different GitHub account. Run `git remote set-url origin https://<your-username>@github.com/<your-username>/Cloud_Advisor.git` and sign in with a personal access token |
| `git push` is rejected (fetch first) | Run `git pull origin main --no-rebase --no-edit`, then push again |

---

## Limitations

- The data, prices and performance formulas are simplified simulations, not real cloud measurements.
- The Learning agent learns from a small history, judged by the same simulator.
- Simple Reflex, Model-Based and Learning change one step at a time, so they can miss the cheapest option.
- The small LLM runs on CPU and doesn't always follow the reviewer's feedback. The review catches this
  but can't force a better answer. A bigger model on a GPU would likely do better.
