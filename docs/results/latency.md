# Grading latency

Time to grade one correct submission, per tier. Measured sequentially (no parallel contention) by
`tools/bench_latency.py`: the oracle solution of three tasks, five runs each after one discarded warm-up run
(15 runs per tier), on Docker Desktop (Windows 11, 12 logical CPUs, 3.7 GB VM memory).

| Tier | Median (s) | p95 (s) | Mean (s) | Runs |
|---|---|---|---|---|
| T0 naive | 2.02 | 2.36 | 2.07 | 15 |
| T1 typical | 3.19 | 3.83 | 3.27 | 15 |
| T2 compat | 3.12 | 8.06 | 4.39 | 15 |
| T3 strict | 3.39 | 9.24 | 4.86 | 15 |

The strict tier starts three throw-away containers (agent, candidate execution, judge) and audits each one's
effective configuration before starting it, and it costs about **1.4 seconds more per grade (median)** than the
naive single-container tier. The p95 on T2 and T3 is dominated by occasional slow container starts on a small
local VM, not by the grading logic. Numbers will differ on other machines; the weekly workflow publishes a
Linux-runner measurement as a build artifact.
