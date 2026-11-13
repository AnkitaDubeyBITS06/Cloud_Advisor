# Summary - all scenarios

## A - Sustained high CPU, response time above target

| Agent | Action | Config | Cost (USD/mo) | Agent's own est. response (ms) | Peak response (ms) | Peak CPU (%) | Availability (%) | Meets all targets at peak |
|---|---|---|---|---|---|---|---|---|
| Simple Reflex | scale_up | 2 x xlarge | 584.0 | 55 | 57 | 47.5 | 99.997 | yes |
| Model-Based Reflex | scale_up | 2 x xlarge | 584.0 | 55 | 57 | 47.5 | 99.997 | yes |
| Goal-Based | scale_out | 5 x medium | 365.0 | 125 | 125 | 76.0 | 100.0 | yes |
| Utility-Based | scale_out | 5 x medium | 365.0 | 125 | 125 | 76.0 | 100.0 | yes |
| Learning | scale_up | 2 x xlarge | 584.0 | 57 | 57 | 47.5 | 99.997 | yes |
| LLM (Ollama) | scale_up | 2 x xlarge | 584.0 | 57 | 57 | 47.5 | 99.997 | yes |

## B - Low utilisation, expensive instance

| Agent | Action | Config | Cost (USD/mo) | Agent's own est. response (ms) | Peak response (ms) | Peak CPU (%) | Availability (%) | Meets all targets at peak |
|---|---|---|---|---|---|---|---|---|
| Simple Reflex | scale_down | 2 x large | 292.0 | 37 | 42 | 28.0 | 99.997 | yes |
| Model-Based Reflex | scale_down | 2 x large | 292.0 | 37 | 42 | 28.0 | 99.997 | yes |
| Goal-Based | scale_down | 4 x small | 146.0 | 68 | 68 | 56.0 | 100.0 | yes |
| Utility-Based | scale_down | 4 x small | 146.0 | 68 | 68 | 56.0 | 100.0 | yes |
| Learning | scale_down | 2 x large | 292.0 | 42 | 42 | 28.0 | 99.997 | yes |
| LLM (Ollama) | keep | 2 x xlarge | 584.0 | 35 | 35 | 14.0 | 99.997 | yes |

## C - Sharp peak / off-peak swings

| Agent | Action | Config | Cost (USD/mo) | Agent's own est. response (ms) | Peak response (ms) | Peak CPU (%) | Availability (%) | Meets all targets at peak |
|---|---|---|---|---|---|---|---|---|
| Simple Reflex | scale_down | 2 x medium | 146.0 | 42 | 3000 | 99.0 | 99.697 | no |
| Model-Based Reflex | scheduled_scaling | 1->3 x large (scheduled) | 255.5 | 78 | 78 | 61.3 | 99.5 | no |
| Goal-Based | scheduled_scaling | 2->11 x small (scheduled) | 196.19 | 91 | 91 | 66.9 | 99.997 | yes |
| Utility-Based | scheduled_scaling | 2->11 x small (scheduled) | 196.19 | 91 | 91 | 66.9 | 99.997 | yes |
| Learning | scheduled_scaling | 2->3 x large (scheduled) | 346.75 | 78 | 78 | 61.3 | 99.997 | yes |
| LLM (Ollama) | scale_up | 2 x large | 292.0 | 375 | 375 | 92.0 | 99.697 | no |
