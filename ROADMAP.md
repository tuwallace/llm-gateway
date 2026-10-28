# LLM Gateway Production Simulation: Roadmap

Goal: simulate a shared production gateway used by 5 teams, with authentication,
budgets, rate limits, caching, load balancing, fallbacks and central observability.
Built in increments; each one ends with a verification step.

## Environment (measured 2026-10-26)

| Item | Value |
|---|---|
| Host | Apple Silicon (arm64), 12 cores, 32 GB RAM |
| Docker VM | 8 GB RAM, 12 CPUs |
| Ollama | 0.40.11, native on macOS (Metal GPU) |
| Local models | phi3 (2.2 GB), llama3 (4.7 GB), qwen3:8b (5.2 GB), nomic-embed-text (274 MB), plus larger ones |
| Gateway | LiteLLM 1.106.4 in `gateway-env`, port 4000 |
| Port clash | 5432 is used by another project's container (`sfk-dev-pg`), so this stack uses **5433** |

## Ollama cluster: feasibility

**Feasible, with two constraints.**

1. **Run the instances natively, not in Docker.** Docker on macOS cannot reach the
   GPU, so a containerised Ollama runs CPU-only and is several times slower. Native
   instances use Metal.
2. **Cap the context window on every node.** Measured: with the current default,
   Ollama loads phi3 (2.2 GB of weights) with a 32k context and reports **15.5 GB
   resident**, almost all KV cache. Three nodes at that default need about 46 GB and
   will not fit in 32 GB. With `OLLAMA_CONTEXT_LENGTH=4096` each phi3 node should
   drop to roughly 3 GB. Measured in increment 3: **3.84 GB per node**, about 11.5 GB
   for three. The cluster runs on ports 11435-11437; the desktop app on 11434 is
   left alone (it still holds its own 32k-context copy until its keep-alive expires). Use small models for the
   cluster: three 8B models at about 6 GB each is possible but leaves little for
   Docker and the OS, and the GPU is shared, so throughput will not scale linearly.

Plan: three `ollama serve` processes on ports 11434, 11435 and 11436
(`OLLAMA_HOST=127.0.0.1:<port>`, `OLLAMA_CONTEXT_LENGTH=4096`), sharing one model
directory. They are logical nodes on one machine. That is enough to exercise load
balancing, health checks and failover (kill a node mid-run), but not to measure real
horizontal scaling.

**Cost caveat:** local models cost $0, and LiteLLM budgets are in dollars. To make
budgets and token quotas bite, the model entries get an artificial
`input_cost_per_token` / `output_cost_per_token`, so spend becomes a proxy for tokens.

## Teams

| Team | Profile | Intent |
|---|---|---|
| `search` | high volume, short prompts | stress RPM |
| `support` | steady, medium prompts | typical user |
| `analytics` | few requests, long prompts | stress TPM |
| `research` | bursty, large outputs | stress budget |
| `intern-sandbox` | tiny limits | prove limits actually deny |

## Increments

| # | Increment | Verify by | Status |
|---|---|---|---|
| 0 | Single-model gateway, master key, sunny/rainy tests | `pytest test_gateway.py` | done |
| 1 | **PostgreSQL in Docker**, gateway on DB, virtual keys | `/health/readiness` shows `db: connected`; bad key returns 401 | done |
| 2 | **5 teams and virtual keys**: team records, per-team keys, per-team model access, RPM/TPM limits, `max_budget` with `budget_duration` | each team's key works; over-limit gets 429; over-budget gets 400/429 | done (`seed_teams.py`, `test_teams.py`) |
| 3 | **Ollama cluster and load balancing**: 3 nodes, one `model_name` with 3 deployments, `routing_strategy` | requests spread across nodes (per-node counts) | done (`cluster/start_nodes.sh`, `test_cluster.py`) |
| 4 | **Fallbacks and resilience**: fallback chain (e.g. phi3 to llama3), cooldowns, retries | kill a node or model; requests still succeed | done (`test_failover.py`) |
| 5 | **Semantic caching**: Redis container, embeddings via `nomic-embed-text`, similarity threshold | repeat and paraphrased prompt returns a cache hit with lower latency | done (`test_cache.py`) |
| 6 | **Token tracking and quotas**: spend logs, per-team token counts, artificial per-token pricing so budgets act as token quotas | spend per team matches token usage; quota exhaustion blocks | done (`usage_report.py`, `test_tokens.py`) |
| 7 | **Centralized observability**: Prometheus and Grafana containers, LiteLLM metrics, per-team dashboards | dashboard shows per-team RPM, tokens, latency, errors, cache hit rate | done (`observability/`, `test_observability.py`) |
| 8 | **Traffic simulation**: scripted load per team profile, then failure injection | run report: 429 counts, budget exhaustion, failover timing, cache hit rate | done (`simulate.py`, `docs/simulation-report.md`) |

## Open issues

- **RPM enforcement failed once and was not reproduced.** During increment 7, team and key
  RPM limits stopped rejecting requests (all 200, with `remaining-requests: 0`) until the
  gateway was restarted; the log of that process was lost. A monitor then checked every
  90 s for an hour (40 of 40 checks enforced, across two gateway processes of about 40 and
  20 minutes, including through the full simulation with nodes being killed). Cause unknown; a restart clears it.
  If it recurs, keep the gateway log from that moment.
- **Latency isolation: solved in normal operation, not during failover.** Per-team concurrency caps
  and a dedicated node pool each cut a quiet team's latency during a noisy team's burst from ~20-30 s
  to 1-2 s. Caps reject instead of queueing, charge every rejection 2 RPM units and are bypassed
  during failover (`docs/concurrency-experiment.md`). A dedicated pool keeps the heavy team's full
  throughput but moves the queue onto it (`docs/dedicated-pool-experiment.md`).
- **Total primary failure: capacity shortens the outage latency; "fewer failures" was not reproduced.** A standby pool
  the size of the primaries cut phase C uncached p50 from 31-39 s to 6-16 s in repeated runs. The earlier
  "0 failures against 15-17" did not reproduce: three new baseline runs had 0 timeouts. A concurrency limit on the
  fallback only trades timeouts for 500s and needs a short `cooldown_time`; a second fallback node alone did
  nothing (`docs/fallback-experiment.md`, `docs/variance-experiment.md`). Untested: a llama3 fallback at full capacity.
- **Embedding node can crash under GPU memory pressure.** With six phi3 nodes plus llama3/embeddings loaded, the runner
  on 11438 died (Metal out of memory) and the cache silently stopped working. `simulate.py` now has a cache
  preflight. Not done: monitoring/alerting on cache-hit rate, and a dedicated embedding node.
- ~~Search 429 justification check failing since 2026-10-28~~ **Resolved: checker bug.** The cache preflight (2 requests) and warm-up sent before t0 use up the RPM window but the checker did not count them; `simulate.py` now records them (`pre_run`). Verification run: 0 unjustified of 112 search 429s, all checks pass.
- **Fallback used while healthy primaries existed.** In the second baseline run the llama3 fallback
  answered 13 uncached requests while one node was down and the other two were healthy.
  Cause unknown (hypothesis: router cooldown after failures such as abandoned requests). It recurs
  with one node down (13 and 12 requests in two runs) and is harmless once the fallback has capacity.

## Known limits to keep in mind

- **Back-to-back simulation runs share a warm semantic cache** (answers live 10 minutes). The
  simulator now flushes it before every run; results from before that change that started within
  10 minutes of another run are marked as corrected in the experiment docs.

- LiteLLM does not cool down a node on connection errors, so a hard-down node keeps
  getting traffic until health-check routing (enabled in increment 4, 10 s interval)
  removes it. In that window requests rely on retries, and a small share can reach the
  fallback model.
- LiteLLM's built-in spend report (`/global/spend/report`) is enterprise-only, so
  `usage_report.py` reads the Postgres spend logs instead. Increment 7 must check the
  same for Prometheus before relying on it.
- Prometheus (open-source callback) works. `litellm_remaining_team_budget_metric` is stale,
  so quota panels read Postgres through a read-only role; new counter series show no
  rate on their first burst (warm each team with one request before a simulation).
- A token quota is enforced per response, so a team can overshoot by one or two
  in-flight requests (measured up to 58 tokens on a 200-token quota).
- Semantic cache threshold is 0.9. At 0.8 a same-shape question about a different fact
  ("capital of Germany" vs "capital of France") was only 0.03 below a false hit.
- Cache hits spend nothing and bypass the nodes, so tests and the load simulation must
  send `"cache": {"no-cache": true}` when they need real model traffic.
- The fallback model (llama3 on port 11438) adds about 5-6 GB when it is in use.
- LiteLLM budgets are dollar-based. A hard "N tokens per month" quota is
  approximated with artificial per-token pricing.
- `tpm_limit` and `rpm_limit` are rates over a window, not total quotas.
- Some LiteLLM features (for example parts of the Prometheus integration and SSO) can
  be gated behind an enterprise licence. Increment 7 will check this before relying on it.
- Everything runs on one machine, so latency and throughput numbers are indicative only.
