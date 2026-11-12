# Learning agent - learning curve from EMPTY experience

10 rounds x 3 scenarios, epsilon = 0.2 (* = exploration).

| Round | Successes | Actions |
|---|---|---|
| 1 | 1/3 | A:keep, B:scale_down*, C:keep |
| 2 | 1/3 | A:scale_down, B:scale_down, C:scale_down |
| 3 | 2/3 | A:scale_up, B:scale_down, C:scale_up |
| 4 | 2/3 | A:scale_up, B:scale_down, C:scale_out |
| 5 | 2/3 | A:scale_up, B:scale_down, C:scale_down* |
| 6 | 3/3 | A:scale_up, B:scale_down, C:scheduled_scaling |
| 7 | 3/3 | A:scheduled_scaling*, B:scale_down, C:scheduled_scaling |
| 8 | 3/3 | A:scheduled_scaling*, B:scale_down, C:scheduled_scaling |
| 9 | 3/3 | A:scale_up, B:scale_down, C:scheduled_scaling |
| 10 | 2/3 | A:scale_up, B:scale_up*, C:scheduled_scaling |

## Final experience

| Situation | Action | Success | Failure |
|---|---|---|---|
| high_load | keep | 0 | 1 |
| high_load | scale_down | 0 | 1 |
| high_load | scale_up | 6 | 0 |
| high_load | scale_out | 0 | 0 |
| high_load | scheduled_scaling | 2 | 0 |
| over_provisioned | keep | 0 | 0 |
| over_provisioned | scale_down | 9 | 0 |
| over_provisioned | scale_up | 0 | 1 |
| over_provisioned | scale_out | 0 | 0 |
| over_provisioned | scheduled_scaling | 0 | 0 |
| volatile | keep | 0 | 1 |
| volatile | scale_down | 0 | 2 |
| volatile | scale_up | 0 | 1 |
| volatile | scale_out | 0 | 1 |
| volatile | scheduled_scaling | 5 | 0 |