# Experiment: run-to-run variance of baseline, big fallback and dedicated pool

**Question.** Earlier comparisons used one run per configuration. Which differences survive repetition?

**Setup.** Three cold-cache runs each of: baseline (`litellm_config.yaml`), big fallback
(`experiments/litellm_config.fb-big.yaml`: 3 standby phi3 nodes) and dedicated pool (pool config, `--pool`).
Same simulator, same seed, cache flushed before every run, configurations interleaved.

## What went wrong first (read this before the numbers)

The first attempt (9 runs) was **invalid for 5 of them**. The embedding runner on port 11438 (the llama3
fallback node, which also serves `nomic-embed-text`) crashed with Metal `Insufficient Memory`
(`decode() failed: Compute error`). Every cache lookup then returned 500, the hit rate fell from ~74% to 0%
and the system was overloaded (68-282 timeouts per run). It happened twice. The second time (during round 3 of
the reruns, with the big-fallback config, which keeps six phi3 models plus llama3 and embeddings loaded) is the
likely trigger: a GPU memory budget of ~24.5 GiB. This is a probable cause, not a proven one. Consequences:

- `simulate.py` now runs a pre-run check (`preflight_cache`): the same prompt twice, the second must be a cache
  hit, otherwise it aborts. It caught the second crash after 19 s.
- The five invalid runs are kept in `sim_results/invalid-cache-broken/` and excluded.
- **Rep 3 big fallback is only partly valid**: its hit rate was 52% (others 72-76%), so the cache died
  during the run. Its numbers are shown in brackets and not used for conclusions.
- Everything in `docs/fallback-experiment.md` that ran with the big fallback config may have lost its cache late
  in a run; hit rates in those runs were normal (73-76%) except where noted.

## Results (3 runs each; values are run 1 / run 2 / run 3)

| Metric | baseline | big fallback | dedicated pool |
|---|---|---|---|
| support during research burst, p50 (s) | 27.0 / 25.1 / 15.1 | 13.3 / 32.9 / (20.9) | **1.5 / 1.4 / 1.4** |
| support during burst, p95 (s) | 47 / 60 / 44 | 39 / 54 / (45) | 3.9 / 26.5 / 6.9 |
| search uncached p95 (s) | 48 / 53 / 47 | 35 / 39 / (44) | 32 / 2.3 / 4.3 |
| phase C (primaries down) uncached p50 (s) | 31 / 39 / 32 | **6.2 / 16.0** / (15.9) | 32 / 27 / 39 |
| phase C uncached p95 (s) | 48 / 60 / 54 | **15 / 31** / (28) | 54 / 54 / 57 |
| research tokens, uncached | 10.9k / 11.4k / 11.1k | 10.9k / 12.3k / (12.4k) | 10.0k / 10.9k / 9.3k |
| research ok of ~190 sent | 79 / 79 / 79 | 79 / 79 / (79) | 77 / 78 / 67 |
| timeouts + 5xx, whole run | 0 / 0 / 0 | 0 / 0 / (0) | 2 / 1 / 12 |

## Which differences are real

- **Dedicated pool protects the quiet team: real.** Support's p50 during bursts was 1.4-1.5 s in all three
  runs against 15-27 s for the baseline. The ranges do not overlap. The p95 is less stable (3.9 to 26.5 s).
- **Dedicated pool does not help in a total outage: real.** Phase C latency is the same as the baseline
  (27-39 s against 31-39 s), because the shared llama3 fallback is still the only capacity. Its failures are
  also not zero (rep 3: 8 client timeouts in phase C).
- **Big fallback shortens the outage latency: probably real.** Phase C p50 was 6-16 s against 31-39 s for
  the baseline in every valid run, p95 15-31 s against 48-60 s. Two clean runs plus one partial, all on one side.
- **Big fallback does not fix the quiet-team burst latency: real.** Support during bursts is 13-33 s, the
  same as the baseline.
- **Big fallback "removes failures": NOT reproduced.** The earlier comparison (0 failures against 15 and 17
  for the baselines) does not hold: all three new baseline runs had **0 timeouts and 0 errors**. The earlier
  baselines ran at 4.6 of 6 GB swap and may have been degraded, but that is unconfirmed. Failure counts in this
  setup vary between 0 and 17 for the same configuration, so a single run cannot establish it. The latency
  improvement (above) is the supported claim. Correction applied to `fallback-experiment.md` and the roadmap.
- **Research throughput is the same in all configurations** (about 79 ok, 10-12k tokens). The pool runs vary
  most (9.3k in run 3).

## The search-429 check failures: resolved (checker bug)

Search's "every 429 is justified (RPM 60)" check failed in all six runs started on 2026-10-28 (18-30 unjustified of
59-104) and in none from 2026-10-27. The unjustified 429s were all in the first minute (t = 30-53 s) with 57-58
admitted requests seen against 59 needed. Cause: the cache preflight added on the 28th sends 2 search requests,
and the warm-up sends 1 more, before t0; they use up the gateway's RPM window but the checker did not count them.
`simulate.py` now records every pre-run request time (`pre_run` in the saved run) and counts it. A fresh run
(label "429 probe baseline") passed with 0 unjustified of 112 search 429s, with the pre-run requests at
t = -9.9 to -3.5 s. The gateway's RPM enforcement was not at fault. Old saved runs from the 28th still show the
failure when re-analysed, since they lack `pre_run`.

## Caveats

- Three runs per configuration (two for the big fallback); ranges, not confidence intervals.
- One machine; swap was 5.6-14 GB during the work. Latencies are indicative.
- Run 3 of the pool had 12 errors/timeouts, 8 in phase C; the pool run before had 1.

## Reproduce

```bash
gateway-env/bin/python simulate.py --label "x"            # runs the cache preflight first
gateway-env/bin/python compare_runs.py sim_results/run-*.json
```
