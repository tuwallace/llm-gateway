# Traffic simulation report

Run: 2026-10-26, 210 s of traffic, 625 requests, `simulate.py` (raw data:
`sim_results/run-20261026-211805.json`). Single machine: 3 phi3 nodes + 1 llama3
fallback node, each Ollama node handling one request at a time.

> **Correction (added after the concurrency experiment).** The simulator originally stamped each
> request with the phase it *finished* in, not the one it started in, so slow requests were credited
> to later phases. Re-analysed by start time: 20 of 21 checks pass for this run, not 21 of 21. The
> "all three phi3 nodes serve again within 20 s" check **fails** for this run (node-3 received 1
> uncached request in the window; 11 in total, a small sample) while it passed in two later runs
> (node-3 received 8 and 9), so recovery timing is sample-dependent rather than confirmed. A
> second baseline run also had client timeouts starting in phases B and C (15 in total) that this
> run did not, and its fallback node answered requests while healthy primaries existed. The
> headline finding (limits do not isolate latency) and the Postgres cross-check hold. Details in
> `concurrency-experiment.md`. This run also followed a quarter-length dry run by 6 minutes, so its
> semantic cache was partly warm (hit rate 81% against 75-78% for cold runs): a mild inflation that does
> not change the conclusions. The simulator now flushes the cache before every run.

## Setup

Open-loop load (random arrivals at each team's rate, regardless of whether earlier
requests finished), four phases:

| Phase | Length | What happens |
|---|---|---|
| A baseline | 60 s | all nodes up |
| B node down | 60 s | node-3 stopped |
| C primaries down | 30 s | all three phi3 nodes stopped; only the llama3 fallback is left |
| D recovery | 60 s | nodes restarted |

| Team | Offered load | Limits | Purpose |
|---|---|---|---|
| search | ~90 req/min, short repeated prompts | RPM 60 | exceed RPM; cache-heavy |
| support | ~20 req/min, medium prompts | RPM 30 | well-behaved baseline |
| analytics | ~8 req/min, ~1,500-token prompts | RPM 10, TPM 50k | long prompts under the limits |
| research | 4 req/min plus a burst of 25 every 30 s, 200-token answers | RPM 20 | bursts and large outputs |
| intern-sandbox | ~10 req/min | RPM 3, 50-token quota | prove a tiny allowance actually denies |

## Results

**Outcome mix:** 625 requests: 387 succeeded, 203 rate-limited (429), 35 over quota
(422), **0 server errors or timeouts**. 81% of the successful requests were cache hits.

| Team | Sent | OK | 429 | 422 | Cache hits |
|---|---|---|---|---|---|
| search | 306 | 218 | 88 | 0 | 206 |
| support | 61 | 61 | 0 | 0 | 42 |
| analytics | 30 | 29 | 1 | 0 | 29 |
| research | 193 | 79 | 114 | 0 | 35 |
| intern-sandbox | 35 | 0 | 0 | 35 | 0 |

**Limits.** 21 of 21 checks pass (see `python simulate.py --analyze <file>`).
Successes stayed within each team's RPM (search 218 over 3.5 minutes against a limit of 60
per minute), and every one of the 203 rate-limit rejections was justified: the team had
already been admitted at least its limit in the previous 60 seconds, so there were no
premature 429s. `support` never saw a rejection. `intern-sandbox` started the run with its
quota already exhausted by earlier tests, so it saw only 422s; its 3 RPM limit is covered by
`test_teams.py`.

**Failure injection.**
- *One node down (B):* no client-visible failure. After one health-probe interval (10 s)
  node-3 received no traffic; node-1 and node-2 served all uncached requests.
- *All primaries down (C):* the llama3 fallback served the uncached requests (6), and 0
  of 84 requests failed. 92% of the successful requests in this phase were cache hits, so the
  cache absorbed most of the outage on its own.
- *Recovery (D):* all three phi3 nodes were serving again within 20 s of the restart, and
  the 187 requests after that point had no failures or timeouts.

**Cross-checks (three independent sources).**
- Postgres spend logs match the client exactly: successes, cache hits, failures and billed
  tokens per team (search 218 / 206 hits / 88 failures; research 79 / 35 / 114).
- Prometheus counter deltas over the exact run window match the client to within 1 request per
  team once fallback traffic is included (see finding 3).

## Findings

1. **Limits do not isolate latency.** All limits held and `support` never exceeded any of
   its own, yet its uncached requests waited a median of **38 s** during the 20 seconds after
   a `research` burst, against **1.1 s** otherwise. Each Ollama node serves one request at a
   time, so a burst of 25 large answers queues in front of everyone. RPM, TPM and quotas
   cap *how much* a team sends, not *how long others wait*. Overall, uncached requests had
   p50 19 s against 0.04 s for cache hits.
2. **The cache hides outages, and inflates the hit rate.** A baseline hit rate of 78% and 92%
   during the outage reflect a prompt pool of only 46 topics. Real traffic will hit less, so the
   outage would be felt more.
3. **Cross-checking found a dashboard bug.** Requests answered by the fallback carry
   `requested_model="my-fallback-model"`, and my dashboard filters named only the primary
   model, so during an outage the panels would have shown traffic dropping while the fallback
   carried it. Fixed in `observability/build_dashboard.py`, with a regression test.
4. **Recovery is not instant for heavy users.** In the first minute after nodes came back,
   3 of the 15 uncached requests in phase D were still answered by the fallback, probably
   because health checks (10 s interval) had not yet marked the restarted nodes healthy, and
   `research` latencies stayed high (p50 14 s, p95 29 s).
5. **RPM enforcement held under this load**, including with nodes being killed (see the
   open issue in `ROADMAP.md`: it failed once earlier and was not reproduced).

## Caveats

- One machine, one GPU shared by four Ollama processes: latencies are indicative only.
- Small samples per cell (5 to 20 uncached requests); the latency findings are directional.
- Arrivals are random, so a team can exceed its average rate in a given minute.
- `intern-sandbox` began exhausted (a database reset was not visible to the running gateway,
  which keeps spend counters in memory); the gateway was restarted afterwards.

## Reproduce

```bash
gateway-env/bin/python simulate.py                       # ~4 minutes, restarts nodes at the end
gateway-env/bin/python simulate.py --scale 0.5           # shorter
gateway-env/bin/python simulate.py --analyze sim_results/run-20261026-211805.json
```

Watch it live in Grafana (http://localhost:3000, "LLM Gateway: teams"). For a clean start
reset the counters first: `python reset_team_spend.py`, then **restart the gateway**.
