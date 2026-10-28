# LLM gateway simulation

A simulated production LLM gateway shared by five teams, built and measured in increments on one Mac:
[LiteLLM](https://github.com/BerriAI/litellm) in front of a cluster of local Ollama nodes, with API-key auth,
per-team RPM/TPM limits and token quotas, semantic caching, load balancing, automated fallbacks and
Prometheus/Grafana observability. A traffic simulator then exercises it with failure injection, and a series of
experiments tests what protects a quiet team from a noisy one.

**Video walkthrough:** [One LLM gateway, five teams: what I measured, and what I got wrong](https://youtu.be/xRIkIDjeMyI)

The project is as much about **how to measure** as what was measured: several early conclusions were corrected by later
runs, and those corrections are kept in the docs.

## What is in the stack

| Layer | What | Where |
|---|---|---|
| Gateway | LiteLLM 1.106.4 proxy, port 4000, virtual keys and teams | [litellm_config.yaml](litellm_config.yaml) |
| Database | Postgres 5433 (spend logs, keys, teams) | [docker-compose.yml](docker-compose.yml) |
| Models | 3 phi3 primaries (11435-11437), llama3 fallback + `nomic-embed-text` (11438), 3 standby nodes (11439-11441) | [cluster/start_nodes.sh](cluster/start_nodes.sh) |
| Cache | Redis Stack, semantic cache, threshold 0.9, TTL 600 s | [litellm_config.yaml:70-82](litellm_config.yaml) |
| Resilience | retries, cooldown, health-check routing, `my-educational-model` to `my-fallback-model` | [litellm_config.yaml:48-64](litellm_config.yaml) |
| Observability | Prometheus (9090), Grafana (3000), generated dashboard | [observability/](observability/) |
| Load | Open-loop traffic simulator with four failure phases | [simulate.py](simulate.py) |

Ollama runs natively (Docker on macOS has no GPU access) with `OLLAMA_CONTEXT_LENGTH=4096`, which cuts a phi3 node from
15.5 GB to about 3.8 GB resident. See [ROADMAP.md](ROADMAP.md#ollama-cluster-feasibility).

## The five teams

| Team | Profile | Limits |
|---|---|---|
| `search` | high volume, short repeated prompts | RPM 60, TPM 20k, 500k-token quota |
| `support` | steady, medium prompts | RPM 30, 200k tokens |
| `analytics` | few requests, ~1,500-token prompts | RPM 10, TPM 50k, 500k tokens |
| `research` | bursts of 25, 200-token answers | RPM 20, 300k tokens |
| `intern-sandbox` | tiny allowance | RPM 3, 50 tokens |

Local models cost nothing, so a token quota is expressed as dollars with an artificial price of $0.00001 per token
([seed_teams.py:20](seed_teams.py), [seed_teams.py:30](seed_teams.py)).

## Key findings

Each finding links to the document and, where it applies, the code that backs it.

1. **Limits cap volume, not latency.** All limits held and `support` never exceeded its own, yet its uncached requests
   waited a median 38 s after a `research` burst against 1.1 s otherwise, because each node serves one request at a time.
   [docs/simulation-report.md](docs/simulation-report.md) (Findings 1)
2. **Per-team concurrency caps isolate, with three costs.** Quiet-team latency fell from ~32 s to 1-2 s, but every
   rejection is charged 2 RPM units, the cap rejects instead of queueing, and it is bypassed during failover.
   [docs/concurrency-experiment.md](docs/concurrency-experiment.md) (Findings 1-4), [experiments/concurrency_probes.py](experiments/concurrency_probes.py)
3. **A dedicated node pool isolates without those costs.** `support` waited 1.3 s during bursts and `research` kept its
   full throughput, but the heavy team queues behind itself and the shared fallback is unchanged.
   [docs/dedicated-pool-experiment.md](docs/dedicated-pool-experiment.md), [experiments/make_pool_config.py](experiments/make_pool_config.py), [experiments/pool_probes.py](experiments/pool_probes.py)
4. **Total primary failure: capacity helps, a limit alone does not.** A fallback limit trades timeouts for 500s and makes
   the fallback shut itself off for the 30 s cooldown; a second node alone changed nothing; a standby pool the size of the
   primaries cut outage latency (phase C uncached p50 6-16 s against 31-39 s).
   [docs/fallback-experiment.md](docs/fallback-experiment.md), [experiments/make_fallback_config.py](experiments/make_fallback_config.py)
5. **Repeating the runs overturned a claim.** The first comparison said the big fallback removed failures (0 against 15
   and 17); three further baseline runs also had 0. Only the latency result held. The dedicated pool's isolation (support
   p50 1.4-1.5 s against 15-27 s) held in all three runs.
   [docs/variance-experiment.md](docs/variance-experiment.md) (Which differences are real)
6. **The cache hides outages, and can hide its own failure.** Hit rate was 73-76% (92% during an outage) on a 46-topic prompt
   pool. When the embedding runner crashed (Metal out of memory) the hit rate fell to 0% and runs became meaningless.
   [docs/simulation-report.md](docs/simulation-report.md) (Findings 2), [docs/variance-experiment.md](docs/variance-experiment.md) (What went wrong first), [simulate.py:172](simulate.py) (`preflight_cache`)

## Measurement lessons

Each of these changed a result and is recorded with its correction.

| Problem | Effect | Fix | Where |
|---|---|---|---|
| Requests labelled by the phase they finished in | slow requests credited to the wrong phase | label by start time | [simulation-report.md](docs/simulation-report.md) (Correction) |
| Warm semantic cache across back-to-back runs | hit rate 83-90% against 75-78% cold | flush before each run | [simulate.py:156](simulate.py), [concurrency-experiment.md](docs/concurrency-experiment.md) |
| Spend counters live in gateway memory | DB reset not seen | restart after reset | [restart_gateway.sh](restart_gateway.sh), [reset_team_spend.py](reset_team_spend.py) |
| Dashboard filters named only the primary model | fallback traffic invisible | include fallback and research models | [observability/build_dashboard.py](observability/build_dashboard.py) |
| Embedding node crashed silently | cache stopped, runs invalid | cache preflight | [variance-experiment.md](docs/variance-experiment.md) |
| Preflight and warm-up requests used RPM the checker ignored | false "unjustified 429" failures | record `pre_run` times | [variance-experiment.md](docs/variance-experiment.md) (search-429 section) |

## Run it

Requirements: macOS with Docker and Ollama, Python 3.11. Copy `.env.example` to `.env` and fill every value
(`LITELLM_MASTER_KEY` must be set or LiteLLM will not start).

```bash
python -m venv gateway-env && gateway-env/bin/pip install 'litellm[proxy]' prisma redis httpx pytest 'psycopg[binary]' pyyaml
ollama pull phi3 && ollama pull llama3 && ollama pull nomic-embed-text
docker compose up -d                       # postgres, redis-stack, prometheus, grafana
sh cluster/start_nodes.sh                  # 7 native Ollama nodes on 11435-11441
./restart_gateway.sh                       # gateway on :4000 with litellm_config.yaml
gateway-env/bin/python seed_teams.py       # teams, keys, limits, quotas (writes teams_keys.json)
gateway-env/bin/python -m pytest -q        # baseline suite (69 tests at last count)
gateway-env/bin/python simulate.py --label "baseline"   # ~4 minutes, cold cache, injects failures
```

Dependencies are not pinned in the repo; the list above is what the code imports. Dashboards:
Grafana at http://localhost:3000 ("LLM Gateway: teams"). `docs/commands.md` lists every command run during the build.

Reproduce an experiment (details in each doc's *Reproduce* section):

```bash
gateway-env/bin/python experiments/make_fallback_config.py --standby 3 --out experiments/litellm_config.fb-big.yaml
CONFIG=experiments/litellm_config.fb-big.yaml ./restart_gateway.sh --reset
gateway-env/bin/python simulate.py --label "big fallback"
gateway-env/bin/python compare_runs.py sim_results/run-*.json
```

## Repository map

| Path | Purpose |
|---|---|
| [ROADMAP.md](ROADMAP.md) | the 8 increments, open issues, known limits |
| [docs/](docs/) | experiment write-ups and the command log |
| [experiments/](experiments/) | config generators, probes and generated config variants |
| [simulate.py](simulate.py), [compare_runs.py](compare_runs.py) | traffic simulator and side-by-side comparison |
| [seed_teams.py](seed_teams.py), [usage_report.py](usage_report.py), [reset_team_spend.py](reset_team_spend.py) | teams, spend reports |
| `test_*.py` | pytest suites per increment (gateway, teams, cluster, failover, cache, tokens, observability, experiment configs) |
| [observability/](observability/) | Prometheus config, Grafana provisioning, dashboard generator |
| `graphify-out/` | generated code graph and wiki (see `graphify-out/GRAPH_REPORT.md`) |

## Documentation index

| Document | Question it answers |
|---|---|
| [ROADMAP.md](ROADMAP.md) | what was built, what is open |
| [docs/simulation-report.md](docs/simulation-report.md) | how does the gateway behave under load and failure? |
| [docs/concurrency-experiment.md](docs/concurrency-experiment.md) | do per-team caps protect quiet teams? |
| [docs/dedicated-pool-experiment.md](docs/dedicated-pool-experiment.md) | does a reserved node pool do better? |
| [docs/fallback-experiment.md](docs/fallback-experiment.md) | how do we survive losing every primary? |
| [docs/variance-experiment.md](docs/variance-experiment.md) | which differences are real across repeated runs? |
| [docs/commands.md](docs/commands.md) | every command run, with a summary |
| [docs/video/storyboard.md](docs/video/storyboard.md) | storyboard for the YouTube walkthrough |

## Limits to keep in mind

- One machine, one shared GPU: latencies are indicative, not capacity numbers. Swap was 5-14 GB during some runs.
- Most experiments are single runs; only three configurations have three repeats each ([variance-experiment.md](docs/variance-experiment.md)).
- The standby fallback uses phi3, not llama3, because a llama3 pool of primary size needs about 30 GB.
- Open: cause of the one-off RPM enforcement failure, why the fallback sometimes serves while healthy primaries exist,
  and the cap-bypass mechanism ([ROADMAP.md](ROADMAP.md#open-issues)).
- Secrets (`.env`, `teams_keys.json`, `observability/scraper.key`) are git-ignored; use `.env.example` as the template.
