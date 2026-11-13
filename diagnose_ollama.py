"""Diagnose why the LLM agent hangs. Run:  python diagnose_ollama.py
Each test has a time limit, so this script never hangs. Send a screenshot of the output."""
import concurrent.futures as cf
import json
import os
import sys
import time

URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
LIMIT = 120  # seconds per test
pool = cf.ThreadPoolExecutor(max_workers=1)


def run(name, fn):
    print(f"\n--- {name}", flush=True)
    t0 = time.time()
    fut = pool.submit(fn)
    try:
        out = fut.result(timeout=LIMIT)
        print(f"OK in {time.time() - t0:.0f}s -> {out}", flush=True)
        return True
    except cf.TimeoutError:
        print(f"TIMED OUT after {LIMIT}s (this step hangs)", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR after {time.time() - t0:.0f}s -> {type(e).__name__}: {e}", flush=True)
    return False


print("Python:", sys.version.split()[0], "| model:", MODEL, "| url:", URL)
print("Proxy / Ollama settings:", {k: v for k, v in os.environ.items()
                                   if "proxy" in k.lower() or k.upper().startswith("OLLAMA")} or "none")

import httpx  # noqa: E402

run("1. Ollama server answers", lambda: httpx.get(f"{URL}/api/version", timeout=10).json())
run("2. Model is downloaded", lambda: [m["name"] for m in httpx.get(f"{URL}/api/tags", timeout=10).json()["models"]])
run("3. Models loaded right now", lambda: [(m["name"], m.get("expires_at")) for m in
                                           httpx.get(f"{URL}/api/ps", timeout=10).json()["models"]])
run("4. Plain chat (no tools)", lambda: httpx.post(f"{URL}/api/chat", timeout=LIMIT, json={
    "model": MODEL, "stream": False, "keep_alive": "30m", "options": {"num_ctx": 4096},
    "messages": [{"role": "user", "content": "Say OK"}]}).json()["message"]["content"])
run("5. Chat with a tool (like the agent)", lambda: httpx.post(f"{URL}/api/chat", timeout=LIMIT, json={
    "model": MODEL, "stream": False, "keep_alive": "30m", "options": {"num_ctx": 4096},
    "messages": [{"role": "user", "content": "Call the tool get_targets."}],
    "tools": [{"type": "function", "function": {"name": "get_targets", "description": "Get targets",
                                                "parameters": {"type": "object", "properties": {}}}}]}
).json()["message"])


def lc():
    from agents.llm_agent import make_ollama
    return make_ollama(MODEL, URL).invoke("Say OK").content


run("6. LangChain ChatOllama (exact settings the agent uses)", lc)


def agent_step():
    from scenarios import SCENARIOS
    from agents.llm_agent import LLMAgent
    a = LLMAgent(MODEL, URL, max_steps=1, verbose=False)
    r = a.decide(SCENARIOS["A"])
    return r.get("error") or [t["name"] for t in r.get("tool_log", [])]


run("7. One step of the real LLM agent (scenario A)", agent_step)
print("\nDone. Send a screenshot of everything above.")
os._exit(0)
