# quick_test checks

- [x] all agents received identical input
- [x] every output has summary, candidates, recommendation, reasoning, monitoring plan
- [x] A: no classical agent scales down
- [x] A: Goal/Utility/Learning meet all targets at peak
- [x] A: Learning agent updated its experience
- [x] all agents received identical input
- [x] every output has summary, candidates, recommendation, reasoning, monitoring plan
- [x] B: every classical agent cuts cost
- [x] B: Learning agent updated its experience
- [x] all agents received identical input
- [x] every output has summary, candidates, recommendation, reasoning, monitoring plan
- [x] C (edge): Simple Reflex is fooled by the off-peak sample
- [x] C (edge): Model-Based detects the peak and schedules scaling
- [x] C (edge): Goal/Utility/Learning meet all targets at peak
- [x] C: Learning agent updated its experience
- [x] LLM (fake model) calls >= 2 distinct tools
- [x] LLM (fake model) evidence check passes
- [x] LLM handles Ollama being unavailable
- [x] Learning: later rounds succeed at least as often as the first round

**19/19 passed**
