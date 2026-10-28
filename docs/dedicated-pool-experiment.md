# Experiment: a dedicated node pool for the heavy team

**Question.** Per-team concurrency caps protected the quiet teams but starved `research`
(see `concurrency-experiment.md`). Does reserving a node for `research` (its own model alias)
protect the quiet teams *without* those costs?

**Short answer.** Yes, in normal operation. `support` waited a median of **1.3 s** during
research bursts (31.9 s with no isolation) and `research` still completed its full workload.
The price is that the heavy team now queues behind itself, and nothing changes once every
primary node is down: the shared fallback is still shared.

> **Correction (cache confound).** The "2 caps" and "3 caps + RPM 200" columns below come from runs that
> started with a warm semantic cache and overstate the caps. Cold re-run of caps (run 11): support during
> a burst 1.2 / 40.2 s, research 23 of 190 ok and 3,834 uncached tokens, 10 timeouts all in phase C. The
> pool run (4) and the baseline (1) were cold, so the pool's results and the comparison with the baseline
> are unaffected, and the conclusion (the pool isolates the quiet team without starving the heavy team)
> is, if anything, stronger. See `fallback-experiment.md`.

## Setup

| | Shared layout (baseline) | Dedicated pool |
|---|---|---|
| `my-educational-model` | node-1, node-2, node-3 | node-1, node-2 |
| `research-model` | n/a | research-node (the old node-3, port 11437) |
| research team may call | `my-educational-model` | `research-model` only |
| other teams may call | `my-educational-model` | `my-educational-model` only |
| fallback | `my-fallback-model` (llama3, one node) | the same, for both aliases |

The research alias falls back to the same shared llama3 node, so the failure phases stay
comparable with the baseline. Phase B stops a **shared** node (node-2) in the pool run, so it is
still a "one shared node down" test; the other phases are unchanged.

Files: `experiments/make_pool_config.py` generates `experiments/litellm_config.pool.yaml` from the
main config; `pool_profile.py on|off` switches `research`'s team and key model access;
`experiments/pool_probes.py` verifies the wiring; `simulate.py --pool` runs the pool layout.

## Verification before the run (`experiments/pool_probes.py`)

- research -> `research-model`: 200, served by `research-node`.
- research -> shared alias: 403; support -> `research-model`: 403.
- 24 shared-alias requests from other teams were served only by node-1 and node-2.
- During a 25-request research burst, `support` latency was a median of 1.2 s (max 1.7 s).

## Results (one full simulation run each, 210 s, same profiles)

| | 1 baseline | 2 caps | 3 caps + RPM 200 | 4 dedicated pool |
|---|---|---|---|---|
| **support** during a research burst, p50 / p95 | 31.9 / 53.2 s | 0.9 / 1.0 s | 1.9 / 8.8 s | **1.3 / 2.4 s** |
| support otherwise, p50 / p95 | 1.4 / 43.6 s | 1.0 / 1.2 s | 1.7 / 3.5 s | 1.3 / 2.0 s |
| search uncached p95 | 49.5 s | 5.0 s | 3.5 s | **1.5 s** |
| **research** ok / sent (429s) | 71 / 188 (109) | 40 / 192 (152) | 41 / 194 (139) | **73 / 187 (108)** |
| research uncached tokens | 9,329 | 1,133 | 5,896 | **9,773** |
| research uncached latency p50 / p95 | 30.9 / 55.0 s | 4.3 / 8.7 s | 5.5 / 44.4 s | 30.4 / 52.2 s |
| client timeouts (by phase started) | 15 (B 2, C 13) | 0 | 16 (C 15, D 1) | 10 (B 2, C 8) |

Run 1 is the second baseline run (the first, before the phase-label fix, gave 37.9 / 39.3 s for the
same support figure). Samples for the burst-window rows are small (4 to 15 uncached requests).

## Findings

1. **The pool isolates without the caps' costs.** `research` kept its full 20 requests per minute and
   about 9,800 uncached tokens, and its 429s (108) are plain RPM rejections: no double charge, no
   starvation. The quiet teams did as well as under caps (support 1.3 s; search uncached p95 down from
   49.5 s to 1.5 s).
2. **The heavy team now pays for its own queue.** `research` latency did not improve (p50 30.4 s) and 6
   of its requests timed out (2 in phase B, 4 in phase C). It completed about 12 uncached requests a
   minute (43 over 3.5 minutes) at roughly 5 s each, which is about 60 s of work in every 60 s: its one
   single-slot node was saturated, so bursts queued. Isolation moves the pain to the team that causes
   it; it does not create capacity. A pool must be sized to the team's quota.
3. **Failover is still the weak spot.** In phase C (all primaries down) 8 requests timed out,
   including `support` 3 and `search` 1, because the shared llama3 node serves everyone. The pool
   gives no protection there. Run 2 had zero timeouts, probably because it had starved `research`
   of the uncached traffic that would otherwise have queued on the fallback (not tested directly).
4. **Capacity cost not stressed.** The shared pool shrank from 3 to 2 nodes with no visible harm at
   this load (most shared traffic is cached), but this run does not show where it breaks.
5. **A hint on an open question.** The fallback answered 13 uncached requests in phase B of the second
   baseline run while two shared nodes were healthy; in the pool run it answered none in phase B.
   Consistent with overloaded shared nodes pushing requests to the fallback, but not proven.

## Trade-offs

| | Caps | Dedicated pool |
|---|---|---|
| Quiet team latency in normal operation | excellent | excellent |
| Heavy team throughput | starved unless RPM is sized for 2x rejections | full |
| Holds during failover | no (bypassed) | no (shared fallback) |
| Capacity | unchanged | partitioned (heavy team's node idle when it is quiet) |
| Operational cost | per-key setting, client backoff | extra alias, model access per team |

## Recommendation

Use a dedicated pool for a team whose workload is known to be heavy or bursty. Then fix the
shared failure path, which neither approach covers. Candidates, untested: a concurrency limit on the
fallback deployment, and a second fallback node. Keep RPM/TPM/quota limits for fairness and cost,
and client-side backoff for rejections.

## Current state and reproduce

The environment is back on the shared layout (research on `my-educational-model`, no caps, main config).

```bash
gateway-env/bin/python experiments/make_pool_config.py
gateway-env/bin/python pool_profile.py on
CONFIG=experiments/litellm_config.pool.yaml ./restart_gateway.sh --reset
gateway-env/bin/python experiments/pool_probes.py
gateway-env/bin/python simulate.py --pool --label "4 pool"
# back to normal:
gateway-env/bin/python pool_profile.py off && ./restart_gateway.sh --reset
gateway-env/bin/python compare_runs.py sim_results/run-20261026-220320.json sim_results/run-20261026-221035.json \
    sim_results/run-20261026-221852.json sim_results/run-20261026-224208.json
```
