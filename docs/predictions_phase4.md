# Phase 4 predictions (written before the experiments)
Policy v2 = v1 + approval for every write_note and every shell command that is not a plain read.

| Approver | Oracle attacks that succeed (of 29) | Benign replay utility (of 70) | Benign runs with at least one prompt |
|---|---|---|---|
| allow (always yes) | 10 | 69 | 55% |
| deny (always no) | 0 | 29 | same |
| task (simulated human) | 0 | 69 | same |

