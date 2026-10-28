# Command log

Commands run while building the gateway simulation, grouped by increment, each with
a short summary. This file is updated at the end of every increment.

Conventions:
- Run from the project root (`llm-gateway/`) unless stated.
- Secrets (`LITELLM_MASTER_KEY`, `POSTGRES_PASSWORD`, team keys) live in `.env` and
  `teams_keys.json`. They are never printed or recorded here.
- `$GW_LOG` is the scratchpad log file the gateway writes to; any path works.

## Increment 0: Single-model gateway

| Command | Summary |
|---|---|
| `python -m venv gateway-env` | Failed: pyenv had no global Python (`python: command not found`). |
| `PYENV_VERSION=3.11.9 python -m venv gateway-env` | Worked. Creates the virtualenv with Python 3.11.9. Fix for the failure above: `pyenv local 3.11.9` makes plain `python` work. |
| `source gateway-env/bin/activate` | Activates the venv in the terminal pane. |
| `gateway-env/bin/litellm --config litellm_config.yaml --port 4000` | First start. Failed with `UnsafeMasterKeyError`: LiteLLM refuses to run with no master key. |
| `echo "LITELLM_MASTER_KEY=sk-$(openssl rand -hex 32)" > .env` (then `chmod 600 .env`) | Generates the master key into a new `.env`. LiteLLM loads `.env` from the working directory. |
| `gateway-env/bin/litellm --config litellm_config.yaml --port 4000` | Second start. Worked; serves `my-educational-model` on port 4000. |
| `curl localhost:4000/health/liveliness` | Liveness check; returns 200 when the proxy is up. |
| `set -a; source .env; set +a; curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" -d '{"model":"my-educational-model","messages":[{"role":"user","content":"hi"}]}'` | End-to-end test: auth, route to Ollama phi3, completion returned. |
| `gateway-env/bin/pip install -q pytest` | Installed pytest into the venv. |
| `gateway-env/bin/python -m pytest test_gateway.py -v` | Runs the sunny/rainy gateway tests (`test_gateway.py`). |

## Increment 1: PostgreSQL in Docker

| Command | Summary |
|---|---|
| `docker --version`, `docker compose version`, `docker info` | Confirmed Docker 29.9, Compose v5.6, 8 GB VM. |
| `sysctl -n hw.memsize hw.ncpu; uname -m` | Host check: 32 GB RAM, 12 cores, arm64. |
| `ollama --version; ollama list; curl -s localhost:11434/api/ps` | Inventory of Ollama version and pulled models. |
| `lsof -nP -iTCP:5432 -sTCP:LISTEN` | Found 5432 already taken by another project's container, so this stack uses 5433. |
| `PW=$(openssl rand -hex 16); printf 'POSTGRES_PASSWORD=%s\nDATABASE_URL=postgresql://llmgw:%s@localhost:5433/litellm\n' "$PW" "$PW" >> .env` | Appends the DB credentials to `.env` without printing them. |
| `docker compose up -d` | Starts `llmgw-postgres` (postgres:16-alpine, host port 5433) from `docker-compose.yml`. |
| `docker inspect -f '{{.State.Health.Status}}' llmgw-postgres` | Polls the healthcheck until `healthy`. |
| `docker exec llmgw-postgres psql -U llmgw -d litellm -tc "select version()"` | Confirms the database answers (PostgreSQL 16.15). |
| `gateway-env/bin/pip install -q prisma` | LiteLLM needs the Prisma client to use a database. |
| `pkill -f "litellm --config"` | Stops the running gateway before a restart. |
| `gateway-env/bin/litellm ...` (with the DB) | Failed: "Prisma client hasn't been generated yet". |
| `PATH="$PWD/gateway-env/bin:$PATH" prisma generate --schema gateway-env/lib/python3.11/site-packages/litellm/proxy/schema.prisma` | Generates the Prisma client. Needs the venv on `PATH` or it fails with `prisma-client-py: command not found`. |
| `PATH="$PWD/gateway-env/bin:$PATH" nohup gateway-env/bin/litellm --config litellm_config.yaml --port 4000 > $GW_LOG 2>&1 &` | Starts the gateway detached, with the DB. This is the standard start command from here on. |
| `curl localhost:4000/health/readiness` | Returns `{"status":"healthy","db":"connected"}`. |
| `curl localhost:4000/key/generate ...` then `curl localhost:4000/key/delete -d '{"key_aliases":["smoke-test"]}'` | Created and deleted a throwaway virtual key to prove the DB path works. |

## Increment 2: Five teams, keys, limits, budgets

| Command | Summary |
|---|---|
| `gateway-env/bin/python seed_teams.py` | Idempotently creates the 5 teams and one key each via `/team/new` and `/key/generate`; writes `teams_keys.json` (mode 600). |
| `curl localhost:4000/team/list -H "Authorization: Bearer $LITELLM_MASTER_KEY"` | Lists teams with limits and spend. |
| `gateway-env/bin/python -u -m pytest test_teams.py -v` | Verifies stored limits, key access, spend tracking, 429 on RPM/TPM, budget exhaustion, model access. Uses throwaway teams for destructive checks. |

Config change: artificial per-token price of $0.00001 added to `litellm_config.yaml`.

## Increment 3: Three-node Ollama cluster

| Command | Summary |
|---|---|
| `cluster/start_nodes.sh` | Starts native Ollama nodes on 11435-11437 (`OLLAMA_CONTEXT_LENGTH=4096`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_NUM_PARALLEL=1`). Leaves the desktop app on 11434 alone. |
| `cluster/stop_nodes.sh` | Stops only those three nodes. |
| `curl localhost:<port>/api/generate -d '{"model":"phi3","prompt":"hi","stream":false,"options":{"num_predict":3}}'` | Loads phi3 on a node. |
| `curl localhost:<port>/api/ps` | Reports resident memory and context per node (measured 3.84 GB, ctx 4096). |
| `gateway-env/bin/python -u -m pytest test_cluster.py -v` | Load-balancing tests: 36 concurrent requests spread over all 3 nodes. |
| `gateway-env/bin/python -u -m pytest test_gateway.py test_teams.py test_cluster.py -q` | Full suite (28 tests). |

Notes:
- A piped run (`pytest ... | tail`) hung once and could not be reproduced; redirecting
  pytest output to a file works reliably.
- The system `python3` has no `httpx`; use `gateway-env/bin/python` for scripts.

## Increment 4: Node failure, fallbacks, health-check routing

| Command | Summary |
|---|---|
| `cluster/start_nodes.sh` | Now also starts a 4th node on 11438 (the fallback; serves `llama3`, loaded on first use). `NODE_PORTS="11437 11438" cluster/start_nodes.sh` starts only the listed ports; already-running nodes are skipped. |
| `NODE_PORTS=11437 cluster/stop_nodes.sh` | Kills one node to simulate a failure. With no `NODE_PORTS` it stops all four (never the desktop app on 11434). |
| `curl localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"` | Lists the models; now `my-educational-model` and `my-fallback-model`. |
| `gateway-env/bin/python - <<'EOF' ... EOF` (20 to 40 requests, tally `x-litellm-model-id`, `x-litellm-attempted-retries`, `x-litellm-attempted-fallbacks`) | Manual failover experiments; the three response headers show which node served a request, how many retries it took, and whether the fallback model was used. |
| `grep -iE "cooldown" $GW_LOG` and reading `litellm/router_utils/cooldown_handlers.py` | Diagnosed why a dead node kept receiving traffic: LiteLLM excludes `APIConnectionError` from cooldown (`_is_cooldown_required`). |
| `grep -rnE "enable_health_check_routing\|background_health_checks" gateway-env/lib/python3.11/site-packages/litellm/...` | Found the active health-check settings that fix it. |
| `gateway-env/bin/python -u -m pytest test_failover.py -v > $OUT 2>&1` | Failover tests: one node down, all primaries down (fallback), recovery, everything down. Takes about 50 s. Fixtures restart the nodes afterwards. |
| `gateway-env/bin/python -u -m pytest test_gateway.py test_teams.py test_cluster.py test_failover.py -q > $OUT 2>&1` | Full suite: 32 tests, about 70 s. |
| `curl localhost:<port>/api/ps` (ports 11435-11438) and `vm_stat` | End-of-increment check that all nodes are up and memory is healthy. |

Config changes: `my-fallback-model` (llama3 on 11438), `router_settings` fallbacks,
`num_retries: 3`, `allowed_fails: 1`, `enable_health_check_routing: true`, and
`general_settings` background health checks every 10 s on the primary group only.

Findings (increment 4):
- Passive cooldown does not help with a hard-down node. Before health checks, about a
  third of requests hit the dead node and needed a retry, and roughly 1% exhausted
  all four attempts and were silently served by the fallback model (llama3).
- With health-check routing on, a dead node is skipped after at most one probe
  interval (10 s); 40 requests showed zero retries.

## Increment 5: Redis and semantic caching

| Command | Summary |
|---|---|
| `lsof -nP -iTCP:6379 -sTCP:LISTEN` (and 6380) | Checked the Redis ports were free; this stack uses host port 6380. |
| `printf 'REDIS_PASSWORD=%s\n' "$(openssl rand -hex 16)" >> .env` | Adds the Redis password to `.env` without printing it. |
| `docker compose up -d redis` | Starts `llmgw-redis` (`redis/redis-stack-server`, 7.4.7) from `docker-compose.yml`. Redis Stack is needed because plain Redis has no vector search. |
| `docker inspect -f '{{.State.Health.Status}}' llmgw-redis` | Waits for the healthcheck. |
| `docker exec llmgw-redis redis-cli --no-auth-warning -a "$REDIS_PASSWORD" MODULE LIST` | Confirmed the `search` module (RediSearch) is loaded. |
| `gateway-env/bin/pip install -q redisvl` | LiteLLM's `redis-semantic` cache needs `redisvl`. |
| `curl localhost:11438/api/embed -d '{"model":"nomic-embed-text","input":"..."}'` (cosine in Python) | Measured similarity between prompts to choose the threshold (see findings). |
| `gateway-env/bin/python - <<'EOF' ... EOF` (identical, paraphrased, unrelated prompts; print `x-litellm-cache-key`) | Manual probe. A cache hit is marked by the `x-litellm-cache-key` header; misses don't have it. |
| `docker stop llmgw-redis` / `docker start llmgw-redis` | Resilience check: with Redis down, requests return 200 uncached; caching resumes when Redis is back. |
| `gateway-env/bin/python -u -m pytest test_cache.py -v > $OUT 2>&1` | Cache tests (9): repeat hit, paraphrase hit, no extra spend on hits, unrelated miss, lookalike miss, per-team isolation, RPM still applies. |
| `gateway-env/bin/python -u -m pytest test_gateway.py test_teams.py test_cluster.py test_failover.py test_cache.py -q > $OUT 2>&1` | Full suite: 41 tests, about 95 s. |

Config changes: `ollama-embed` model (nomic-embed-text on 11438), `litellm_settings.cache`
with `type: redis-semantic`, host localhost:6380, `similarity_threshold: 0.9`, `ttl: 600`.
Earlier tests (`test_teams.py`, `test_cluster.py`, `test_failover.py`) now send
`"cache": {"no-cache": true}` so repeated prompts reach a node and spend budget.

Findings (increment 5):
- Similarity to "What is the capital of France?" (nomic-embed-text, cosine):
  paraphrases 0.94-0.98, "capital of Germany" 0.77, "population of France" 0.70,
  unrelated 0.34. At the first threshold of 0.8 the Germany prompt was only 0.03 from
  returning France's answer, so the threshold is 0.9.
- Cache hits cost nothing (no spend, no node), but still count toward RPM.
- Entries are bucketed per key/team/org, so one team never receives another's answer.
- A cache hit's `x-litellm-model-id` header is not meaningful; use `x-litellm-cache-key`
  to detect hits.

## Increment 6: Token tracking and quotas

| Command | Summary |
|---|---|
| `docker exec llmgw-postgres psql -U llmgw -d litellm -c 'select ... from "LiteLLM_SpendLogs" ...'` | Inspected the spend-log table: one row per request with tokens, team, model, node (`model_id`), cache hit and status. Grouped by call type / team to find noise. |
| `curl "localhost:4000/global/spend/report?start_date=...&end_date=...&group_by=team" -H "Authorization: Bearer $LITELLM_MASTER_KEY"` | Tried LiteLLM's built-in report. Enterprise-only (returns a licence error), so `usage_report.py` reads Postgres instead. |
| `gateway-env/bin/python seed_teams.py` | Quotas are now defined in tokens (`token_quota`) and converted to a dollar budget with `PRICE_PER_TOKEN`. Existing teams are reconciled with `/team/update`, so editing the table and re-running applies the change. |
| `gateway-env/bin/python usage_report.py [--days N] [--all] [--by-node]` | Per-team report from the spend logs: requests, cache hits, failures, prompt/completion tokens, tokens saved by the cache, quota, quota used. Also shows platform overhead (health checks, cache embeddings) and, with `--by-node`, requests per node. |
| Inline Python probes (rapid, paced and concurrent requests against a 200-token quota team) | Measured quota overshoot: 5-6 requests served (215-258 tokens) before the block, regardless of pause or worker count. |
| `gateway-env/bin/python -u -m pytest test_tokens.py -v --tb=short > $OUT 2>&1` | Token tests (11): logged tokens equal API `usage`, spend = tokens x price, cache hits logged free, report rows match, quota blocks, blocked requests aren't billed. |
| `gateway-env/bin/python -u -m pytest test_gateway.py test_teams.py test_cluster.py test_failover.py test_cache.py test_tokens.py -q > $OUT 2>&1` | Full suite: 52 tests, about 2 min 10 s. |

Findings (increment 6):
- A token quota is a dollar budget in disguise: 1 token = $0.00001. `litellm_config.yaml`
  and `seed_teams.py` must use the same price (a test checks this).
- Enforcement is per response: the request that crosses the quota is served, then the
  team is blocked. Measured overshoot was one to two requests (up to 58 tokens on a
  200-token quota), independent of concurrency. Negligible for real quotas.
- Blocked requests are not billed.
- Every request writes a free 9-token embedding row under the team's id (the cache
  stores answers even for `no-cache` requests). The report counts these as platform
  overhead, not team usage; queries on the raw table must filter `call_type = 'acompletion'`.
- Health probes are logged under the pseudo-team `litellm-internal-health-check`
  (about 500 rows and 19k phantom tokens per day at a 10 s interval). They never touch
  a team's budget and the report excludes them.
- Cache hits are logged with their tokens but zero spend; the report shows them as
  "saved".

## Increment 7: Prometheus and Grafana observability

| Command | Summary |
|---|---|
| `grep -rn "enterprise" gateway-env/.../litellm/integrations/prometheus.py` | Checked licensing: the Prometheus callback is in the open-source package. (`/global/spend/report` is not.) |
| `gateway-env/bin/pip install -q prometheus_client` | The `prometheus` callback needs this package. Add `callbacks: ["prometheus"]` under `litellm_settings`. |
| `curl localhost:4000/metrics/ -H "Authorization: Bearer $KEY"` | Fetch metrics. Needs a key (401 without one). Use the trailing slash: `/metrics` answers with a 307 redirect. |
| `curl localhost:4000/user/new -d '{"user_alias":"prometheus-scraper","user_role":"proxy_admin_viewer","auto_create_key":false}'` then `curl localhost:4000/key/generate -d '{"user_id":...,"key_alias":"prometheus-scraper-key","models":["no-model-access"],"allowed_routes":["/metrics","/metrics/"]}'` | Creates a read-only scraper identity. A bare `proxy_admin_viewer` key can still call models; `models` + `allowed_routes` limit it to metrics (chat, `/team/list`, `/key/list` return 403). The key is saved to `observability/scraper.key` (mode 600). |
| `printf 'GRAFANA_PASSWORD=%s\n' "$(openssl rand -hex 12)" >> .env` (and `GRAFANA_DB_PASSWORD`) | Passwords for Grafana's admin user and its database role, written to `.env` without printing. |
| `docker compose up -d prometheus grafana` | Starts `llmgw-prometheus` (prom/prometheus 2.55.1, port 9090) and `llmgw-grafana` (11.3.1, port 3000). Prometheus scrapes `host.docker.internal:4000/metrics/` every 5 s using `scraper.key`. |
| `observability/init_grafana_db_role.sh` | Idempotent. Creates Postgres role `grafana_ro`, which can read four columns of `LiteLLM_TeamTable` and nothing else. Re-run after recreating the database. |
| `gateway-env/bin/python observability/build_dashboard.py` | Regenerates `observability/grafana/dashboards/llm-gateway.json` (15 panels). Grafana picks up the file within about 30 s. |
| `curl -u admin:$GRAFANA_PASSWORD localhost:3000/api/datasources` and `.../api/datasources/uid/postgres/health` | Confirms both datasources are provisioned and the Postgres one connects. |
| `curl localhost:9090/api/v1/targets` | Confirms the `litellm` target is `up`. |
| Inline Python running every panel query via `curl localhost:9090/api/v1/query` | Validated each dashboard query against live data. |
| `gateway-env/bin/python reset_team_spend.py` (then restart the gateway) | Resets the seeded teams' spend counters to zero after test traffic exhausted `intern-sandbox`. LiteLLM has no API for this; spend logs are untouched. |
| `gateway-env/bin/python -u -m pytest test_observability.py -v --tb=short > $OUT 2>&1` | Observability tests (12). |
| `docker exec -e REDISCLI_AUTH="$REDIS_PASSWORD" llmgw-redis redis-cli ...` | The safe way to run `redis-cli` with the password; never put it on the command line. |

URLs: Grafana http://localhost:3000 (user `admin`, password `GRAFANA_PASSWORD` in `.env`),
dashboard "LLM Gateway: teams". Prometheus http://localhost:9090.

Findings (increment 7):
- **Noise in the raw metrics.** The counters include `/metrics` scrapes, the cache
  embedding calls (`requested_model="ollama-embed"`) and the health-check pseudo-team.
  Every dashboard query filters to `route="/v1/chat/completions"`,
  `requested_model="my-educational-model"` and real teams.
- **Cache hits carry a node id.** A hit reports `model_id="node-2"` although no node did
  work, so the per-node panel subtracts `litellm_cache_hits_metric_total`.
- **`litellm_remaining_team_budget_metric` goes stale.** It is computed from a cached team
  record: it stayed at the full budget for 140 s after requests, then updated only when a
  request arrived after the cache expired, and then showed the state from before that
  request (930 against a true 905). The quota panels therefore read
  `LiteLLM_TeamTable` through the read-only `grafana_ro` role instead.
- **New series show no rate on their first burst.** A counter series that first appears
  already holding its final value has one sample, so `rate()`/`increase()` return 0.
  Steady traffic registers normally. Warm each team with one request before a burst.
- **Status codes:** rate limit = 429; exhausted token quota = **422** (not 400).
- A `proxy_admin_viewer` key is not read-only for models; restrict it explicitly.

## Increment 8: Traffic simulation

| Command | Summary |
|---|---|
| `gateway-env/bin/python simulate.py [--scale 0.5]` | Runs the simulation: 5 team profiles with open-loop random arrivals, four phases (baseline, one node down, all primaries down, recovery), then checks and cross-checks. About 4 minutes at scale 1.0, plus up to 2 minutes waiting for spend logs. Always restarts the nodes at the end. Writes `sim_results/run-<time>.json`; exits 1 if any check fails. |
| `gateway-env/bin/python simulate.py --analyze sim_results/run-<time>.json` | Re-evaluates a saved run with the current checks without sending traffic. |
| `gateway-env/bin/python reset_team_spend.py` then restart the gateway | Clean quotas before a run. The restart is required: the gateway keeps spend counters in memory and does not see a database reset (probed for 2 minutes). |
| `curl localhost:9090/api/v1/query --data-urlencode 'query=...' --data-urlencode "time=<epoch>"` (two calls, end minus start) | Compared Prometheus counter deltas over the exact run window with the client's counts. A `[15m]` `increase()` is contaminated by earlier runs inside the window. |
| `docker exec llmgw-postgres psql -U llmgw -d litellm -c 'SELECT ... FROM "LiteLLM_SpendLogs" ...'` | Counted completion rows per team, status and cache hit for the run window; matched the client exactly. |
| `$SCRATCH/rpm_monitor.sh` (background) | Every 90 s: creates a throwaway team with RPM 2, sends 5 requests, expects `[200, 200, 429, 429, 429]`, and logs the gateway's RSS and open files. Watches for the RPM-enforcement failure seen once in increment 7. |
| `gateway-env/bin/python -u -m pytest test_gateway.py test_teams.py test_cluster.py test_failover.py test_cache.py test_tokens.py test_observability.py -q > $OUT 2>&1` | Full suite: 65 tests, about 2 min 40 s. |

Findings (increment 8): see `docs/simulation-report.md`. In short: every limit held and
every 429 was justified; failure handling lost no requests; Postgres matched the client
exactly; limits do not isolate latency (a `research` burst made `support` wait 38 s at the
median); cross-checking exposed a dashboard filter that hid fallback traffic (fixed).

## Experiment: per-team concurrency caps

| Command | Summary |
|---|---|
| `gateway-env/bin/python concurrency_profile.py caps` / `off` / `show` | Sets (or clears) `max_parallel_requests` on each team's key via `/key/update`. LiteLLM supports the cap on keys, not teams; a team-level value is silently ignored. Caps: research 1, search 3, support 3, analytics 2, intern 1. |
| `./restart_gateway.sh [--reset]` | Restarts the gateway detached and waits until it is live. `--reset` zeroes the seeded teams' spend first (the gateway keeps spend in memory, so reset and restart go together). `GATEWAY_LOG=<path>` sets the log file. |
| `gateway-env/bin/python simulate.py --label "2 caps"` | Runs the simulation and stores the label and the caps in effect with the results. |
| `gateway-env/bin/python compare_runs.py run-A.json run-B.json ...` | Side-by-side table: quiet team's latency during research bursts, the noisy team's cost, rejections, timeouts. |
| `gateway-env/bin/python experiments/concurrency_probes.py` | Reproduces the three cap findings (cap behaviour, 2x RPM charge, bypass during failover). About 4 minutes; stops and restores the Ollama nodes. |
| `curl localhost:9090/api/v1/query_range --data-urlencode 'query=litellm_deployment_state{...}' ...` | Charted each node's health state across a run; showed the nodes the fallback bypassed were healthy. |
| `POST /team/update {"team_id":..., "rpm_limit":200}` then `python seed_teams.py` | Temporarily raised `research` RPM for run 3, then restored it (seed_teams reconciles limits). |

Findings: see `docs/concurrency-experiment.md`. Notes:
- `max_parallel_requests` on `/team/new` is accepted and dropped without an error.
- Concurrency-rejected requests are charged 2 RPM units each.
- A simulator bug (phase stamped at finish time) was found and fixed; `--analyze` re-derives phases.

## Experiment: dedicated node pool for research

| Command | Summary |
|---|---|
| `gateway-env/bin/python experiments/make_pool_config.py` | Generates `experiments/litellm_config.pool.yaml` from the main config: node-3 becomes `research-node` behind a new `research-model` alias; the research alias falls back to `my-fallback-model`; both aliases are health-checked. |
| `gateway-env/bin/python pool_profile.py on` / `off` / `show` | Sets research's team and key `models` to `["research-model"]` (or back to the shared alias). Other teams are untouched. |
| `CONFIG=experiments/litellm_config.pool.yaml ./restart_gateway.sh --reset` | Restarts the gateway on the pool config. `CONFIG` selects the config file. |
| `gateway-env/bin/python experiments/pool_probes.py` | Verifies routing and access (403 both ways, shared traffic never reaches `research-node`) and the burst scenario. |
| `gateway-env/bin/python simulate.py --pool --label "4 pool"` | Runs the simulation with the pool layout: each team uses the model its key allows, phase B stops shared node-2, phase C stops the other two primaries. |
| `gateway-env/bin/python compare_runs.py <run files>` | Compares any number of saved runs side by side. |
| `gateway-env/bin/python pool_profile.py off && ./restart_gateway.sh --reset` | Back to the shared layout. |

Notes: requests served by the pool carry `requested_model="research-model"`; the dashboard filters
now include it (same label-filter mistake as the fallback model earlier, caught in advance), with the
regression test extended. Findings: `docs/dedicated-pool-experiment.md`.

## Experiment: fallback concurrency limit and second fallback node

| Command | Summary |
|---|---|
| `cluster/start_nodes.sh` | Now also starts a fifth node on 11439 (second llama3 fallback node, idle unless a config uses it). Defaults for `start_nodes.sh` / `stop_nodes.sh` are 11435-11439. After a machine restart the nodes and the gateway are not running: run `cluster/start_nodes.sh` then `./restart_gateway.sh`. |
| `gateway-env/bin/python experiments/make_fallback_config.py [--limit N] [--second-node] [--pool] --out <file>` | Generates a config variant: `max_parallel_requests: N` on every fallback deployment, and/or a second fallback deployment (`fallback-node-2`, port 11439). |
| `CONFIG=experiments/litellm_config.fb-both.yaml ./restart_gateway.sh --reset` | Restart on a variant. Variants used: `fb-limit`, `fb-node2`, `fb-both`. |
| `gateway-env/bin/python simulate.py --label "10 fb both (cold)"` | Runs the simulation. It now **flushes the semantic cache first** (deletes `litellm_semantic_cache_index:*` keys in Redis, no restart needed) and records how many entries it removed. `--keep-cache` opts out. |
| `gateway-env/bin/python compare_runs.py <run files>` | Now also prints the cache hit rate, whether the cache was flushed, and a "phase C (all primaries down)" block (requests, hits, fallback-answered, 429s, 5xx, timeouts, latency). |
| `gateway-env/bin/python concurrency_profile.py off` | Used to make sure caps are removed before and after each batch. |
| `docker exec -e REDISCLI_AUTH="$REDIS_PASSWORD" llmgw-redis redis-cli --scan --pattern 'litellm_semantic_cache_index:*'` | List cached answers (what the simulator flushes). |

Notes:
- **Back-to-back runs share a warm cache.** Answers live in Redis for 10 minutes and the prompt pool is
  small, so a run started within 10 minutes of another saw hit rates of 83-90% (cold: 75-78%) and looked
  faster. This invalidated the "second node helps" result and inflated the earlier caps runs; all
  results used in `docs/fallback-experiment.md` are cold. Corrections are in that file.
- A deployment-level `max_parallel_requests` limit sheds load via `RateLimitError`, which cools the
  deployment down for `cooldown_time` (30 s): the fallback answers 429 for that long.
- Findings: `docs/fallback-experiment.md`.

## Experiment: capacity-matched fallback and shorter cooldown

| Command | Summary |
|---|---|
| `gateway-env/bin/python experiments/make_fallback_config.py --standby 3 [--limit 2] [--cooldown 5] --out <file>` | New options: `--standby N` replaces the llama3 fallback with N phi3 deployments (ids `fallback-node`, `-2`, `-3`, ports 11439-11441); `--cooldown S` sets the router `cooldown_time`. Variants used: `fb-big`, `fb-big-limit-cd5`, `fb-limit-cd5`. |
| `cluster/start_nodes.sh` | Defaults are now 11435-11441. Nodes 11439-11441 start with `OLLAMA_KEEP_ALIVE=20s` so they unload when idle and six phi3 copies are never resident together. |
| `gateway-env/bin/python simulate.py --label "12 big fb"` (per variant, after `CONFIG=... ./restart_gateway.sh --reset`) | The three cold-cache runs (cache flushed by the simulator). |
| capacity probe (inline Python, 12 simultaneous 120-token `no-cache` requests through the primaries, then through the standby pool with the primaries stopped) | Showed parity: 19.6 s against 20.0 s wall time. |
| `sysctl vm.swapusage` | Checked memory pressure after the runs: 4.6 of 6 GB swap in use (not attributable to the runs). |
| `gateway-env/bin/python -m pytest test_experiment_configs.py` | Four tests that the config generators produce the standby pool, limit, cooldown and second node, and leave the primaries untouched. Full suite: 69 tests. |

Findings: `docs/fallback-experiment.md` ("Follow-up" section).

## Run-to-run variance experiment (2026-10-27/28)

| Command | What it did |
|---|---|
| scratchpad `run_repeats.sh` (9 runs: baseline, big fallback, pool x3, cold cache, interleaved) | Five of the nine were invalid: the embedding runner crashed (Metal out of memory), the semantic cache stopped working. |
| `curl localhost:11438/api/embeddings ...` | Reproduced `"Compute error."` on the embedding node. |
| `kill <pid>`; `NODE_PORTS=11438 sh cluster/start_nodes.sh` | Restarted only the node on port 11438; embeddings worked again. |
| `simulate.py` edit: `preflight_cache()` | Aborts a run before traffic if a repeated prompt is not a cache hit. |
| scratchpad `run_reruns.sh` (5 reruns), then one more pool run after a second embedding crash | Valid replacements; invalid runs moved to `sim_results/invalid-cache-broken/`. |
| `compare_runs.py <9 runs>`, `simulate.py --analyze <run>` | Side-by-side table and per-run checks. Written up in `docs/variance-experiment.md`. |
| `simulate.py` edit: record `pre_run` times; `simulate.py --label "429 probe baseline"` | Fixed the RPM-window check to count preflight/warm-up requests; verification run passed with 0 unjustified 429s. |
