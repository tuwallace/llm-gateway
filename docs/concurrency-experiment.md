# Experiment: per-team concurrency caps

**Question.** The simulation showed that RPM, TPM and quotas do not protect a quiet team's
latency from a noisy one (a `research` burst made `support` wait a median of 32-38 s). Does a
per-team `max_parallel_requests` cap fix that, and what does it cost?

**Short answer.** In normal operation the cap works very well for the quiet team
(32 s down to 1-2 s median). But it rejects rather than queues, every rejection is charged
**twice** against the team's RPM budget, and **the cap is bypassed during failover**, the one
time the fallback node is weakest. Use it as one layer, not as the isolation mechanism.

> **Correction (cache confound).** Runs 2 and 3 started 7 and 8 minutes after the previous run, inside the
> semantic cache's 10-minute lifetime, so they ran with a warm cache (hit rate 89% and 83% against 75-78%
> cold) and look better than they should. Re-run cold (run 11): support during a burst p50 / p95 **1.2 /
> 40.2 s** (not 0.9 / 1.0), research 23 of 190 ok and 3,834 uncached tokens (not 1,133), and **10
> timeouts, all in phase C** (not 0). The conclusions stand: the cap protects the quiet team in normal
> operation, starves the noisy team, and is bypassed during failover (the 10 timeouts are that bypass).
> The figures in the tables below for runs 2 and 3 are the warm ones. Details in `fallback-experiment.md`.

## Method

Three full simulation runs (`simulate.py`, 210 s each, same profiles and seed), each from a clean
start (`./restart_gateway.sh --reset`). Compare with `compare_runs.py`.

| Run | Configuration |
|---|---|
| 1 baseline | no caps |
| 2 caps | research 1, search 3, support 3, analytics 2, intern 1 in flight (`concurrency_profile.py caps`) |
| 3 caps + RPM 200 | same caps, `research` RPM raised from 20 to 200 for this run only, to separate the cap's own cost from the RPM charge in finding 2 |

Where the cap lives: LiteLLM attaches `max_parallel_requests` to **API keys** (and organisations),
not teams. Setting it when creating a team is silently ignored (the field came back `None`).
Each of our teams has exactly one key, so a key-level cap behaves as a team cap here; a second
key would double it.

## Results

| | 1 baseline | 2 caps | 3 caps + RPM 200 |
|---|---|---|---|
| **support**, uncached latency during a research burst: p50 / p95 | 31.9 s / 53.2 s | **0.9 s / 1.0 s** | **1.9 s / 8.8 s** |
| support, otherwise: p50 / p95 | 1.4 s / 43.6 s | 1.0 s / 1.2 s | 1.7 s / 3.5 s |
| **research** ok / sent (429s) | 71 / 188 (109) | 40 / 192 (152) | 41 / 194 (139) |
| research uncached tokens generated | 9,329 | **1,133** | 5,896 |
| search ok / sent (429s) | 235 / 306 (67) | 215 / 293 (78) | 220 / 325 (105) |
| client timeouts (by phase started) | 15 (B 2, C 13) | **0** | 16 (C 15, D 1) |

Run-to-run noise: the first baseline run (before the phase-label fix) had 37.9 s / 39.3 s for the
same support figure, so the baseline effect is stable at 30+ s; the cap effect (1-2 s) is far outside
that. Tail figures (p95) rest on small samples (4 to 15 requests) and are directional.

## Findings

1. **The cap protects the quiet team in normal operation.** `support` stayed at 1-2 s through every
   research burst. Run 2 had no timeouts at all; run 3's 16 all started in phase C or at its edge
   (15 in C, 1 at the C/D boundary), none during normal operation.
2. **Rejections cost twice.** Every request the cap rejects is charged **2 units of RPM budget**
   (measured: with RPM 20 and K rejections, 19, 17, 15, 13, 11, 7 requests were accepted afterwards for
   K = 0, 1, 2, 3, 4, 6). A `research` burst of 25 against a cap of 1 rejects 24 requests, charging 48
   against an RPM of 20, so the team is locked out for the rest of the minute even though it was
   admitted almost nothing. This is why run 2 starved `research` (88% fewer uncached tokens) and why
   run 3, with RPM out of the way, recovered part of it (5,896 tokens). Size RPM for at least twice the
   expected rejections, or avoid combining a low RPM with a tight cap for bursty clients.
3. **The cap is bypassed during failover.** With all primaries down, a cap-1 key admitted 6 of 6
   requests spaced 0.4 s apart (1 to 2 of 6 with all nodes up, across repeated probes; 1 of 6 for a
   simultaneous burst even with the primaries down), both
   immediately after the nodes stopped and after health checks had noticed. In run 3, `research`
   (cap 1) had **18 requests in flight at once** in phase C, all queued on the single llama3 node with
   latencies climbing from 15 s to 56 s, until 14 of them timed out. The probable mechanism, not
   confirmed, is that a request that falls back releases its slot when the primary attempt fails.
4. **The cap rejects, it does not queue.** Excess requests get an immediate 429, so clients need
   retry with backoff, and each retry pays the double charge in finding 2.
5. **Abandoned requests are still completed and billed.** In run 1 the spend logs held exactly 15
   more completions than the client saw, matching its 15 timeouts. Giving up does not cancel the
   upstream call or its cost.

## Open observations

- In phase B (one node down, both other nodes marked healthy by the health-check metrics) the fallback
  served 13 uncached requests in the second baseline run (2 in the first), silently answering with
  llama3 while healthy phi3 nodes existed. Not a health-check false positive. Untested hypothesis: a
  router cooldown after failures such as abandoned requests (`allowed_fails: 1`, `cooldown_time: 30`).
  The gateway log from that run was not kept.
- One run per configuration; arrivals are random. The direction and size of the main effect are clear,
  the exact numbers are not.

## Measurement corrections made along the way

- `simulate.py` stamped each request with the phase it **finished** in. It now uses the phase it
  **started** in, and `--analyze` re-derives phases for saved runs. Latency-versus-burst figures use
  start times and were unaffected; per-phase tables and checks were. See the correction in
  `simulation-report.md`.
- The "every 429 is justified" check now also accepts the concurrency rule (cap requests in flight).
  Its client-side in-flight estimate cannot see slot holds, so for run 2 it flags `research` 429s that
  are really RPM lockouts from finding 2; that run is read through the comparison table, not the checks.
- The cross-check against Postgres now allows the database to exceed the client by exactly the number
  of client timeouts (finding 5).

## Current state and recommendations

Caps are **off** (`concurrency_profile.py off`); `research` RPM is back to 20. To try them:
`gateway-env/bin/python concurrency_profile.py caps`, then `./restart_gateway.sh --reset`.

Options that would address what the caps do not (the first was tested afterwards: see
`dedicated-pool-experiment.md`):
- **Dedicated pool for the heavy team:** a separate model alias served by one reserved node, so
  `research` can never queue in front of anyone. Deterministic isolation, at the cost of capacity.
- **Limit concurrency on the fallback deployment itself**, so failover cannot be flooded.
- **Client-side backoff and fewer, smaller bursts** (a platform rule, not a gateway setting).

## Reproduce

```bash
gateway-env/bin/python experiments/concurrency_probes.py   # findings 2 and 3, ~4 minutes
gateway-env/bin/python compare_runs.py sim_results/run-20261026-220320.json \
    sim_results/run-20261026-221035.json sim_results/run-20261026-221852.json
```
