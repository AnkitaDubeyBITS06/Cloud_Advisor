# Summary - all scenarios

## A - Sustained high CPU, response time above target

| Agent | Action | Config | Cost (USD/mo) | Agent's own est. response (ms) | Peak response (ms) | Peak CPU (%) | Availability (%) | Meets all targets at peak | Needs human review |
|---|---|---|---|---|---|---|---|---|---|
| Simple Reflex | scale_up | 2 x xlarge | 584.0 | 55 | 57 | 47.5 | 99.997 | yes | no |
| Model-Based Reflex | scale_up | 2 x xlarge | 584.0 | 55 | 57 | 47.5 | 99.997 | yes | no |
| Goal-Based | scale_out | 5 x medium | 365.0 | 125 | 125 | 76.0 | 100.0 | yes | no |
| Utility-Based | scale_out | 5 x medium | 365.0 | 125 | 125 | 76.0 | 100.0 | yes | no |
| Learning | scale_up | 2 x xlarge | 584.0 | 57 | 57 | 47.5 | 99.997 | yes | no |

## B - Low utilisation, expensive instance

| Agent | Action | Config | Cost (USD/mo) | Agent's own est. response (ms) | Peak response (ms) | Peak CPU (%) | Availability (%) | Meets all targets at peak | Needs human review |
|---|---|---|---|---|---|---|---|---|---|
| Simple Reflex | scale_down | 2 x large | 292.0 | 37 | 42 | 28.0 | 99.997 | yes | no |
| Model-Based Reflex | scale_down | 2 x large | 292.0 | 37 | 42 | 28.0 | 99.997 | yes | no |
| Goal-Based | scale_down | 4 x small | 146.0 | 68 | 68 | 56.0 | 100.0 | yes | no |
| Utility-Based | scale_down | 4 x small | 146.0 | 68 | 68 | 56.0 | 100.0 | yes | no |
| Learning | scale_down | 2 x large | 292.0 | 42 | 42 | 28.0 | 99.997 | yes | no |

## C - Sharp peak / off-peak swings

| Agent | Action | Config | Cost (USD/mo) | Agent's own est. response (ms) | Peak response (ms) | Peak CPU (%) | Availability (%) | Meets all targets at peak | Needs human review |
|---|---|---|---|---|---|---|---|---|---|
| Simple Reflex | scale_down | 2 x medium | 146.0 | 42 | 3000 | 99.0 | 99.697 | no | no |
| Model-Based Reflex | scheduled_scaling | 1->3 x large (scheduled) | 255.5 | 78 | 78 | 61.3 | 99.5 | no | no |
| Goal-Based | scheduled_scaling | 2->11 x small (scheduled) | 196.19 | 91 | 91 | 66.9 | 99.997 | yes | no |
| Utility-Based | scheduled_scaling | 2->11 x small (scheduled) | 196.19 | 91 | 91 | 66.9 | 99.997 | yes | no |
| Learning | scheduled_scaling | 2->3 x large (scheduled) | 346.75 | 78 | 78 | 61.3 | 99.997 | yes | no |
