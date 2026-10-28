# Graph Report - llm-gateway  (2026-10-28)

## Corpus Check
- 33 files · ~26,663 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 317 nodes · 565 edges · 20 communities (16 shown, 4 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- seed_teams.py
- simulate.py
- test_tokens.py
- test_observability.py
- Command log
- test_gateway.py
- pathlib
- compare_runs.py
- test_teams.py
- test_cache.py
- test_failover.py
- Experiment: a concurrency limit and a second node for the shared fallback
- Experiment: per-team concurrency caps
- Experiment: a dedicated node pool for the heavy team
- LLM Gateway Production Simulation: Roadmap
- Traffic simulation report
- start_nodes.sh
- stop_nodes.sh
- init_grafana_db_role.sh
- restart_gateway.sh

## God Nodes (most connected - your core abstractions)
1. `master_key()` - 22 edges
2. `Command log` - 15 edges
3. `run()` - 11 edges
4. `new_key()` - 10 edges
5. `stop_nodes()` - 10 edges
6. `main()` - 9 edges
7. `Experiment: a concurrency limit and a second node for the shared fallback` - 9 edges
8. `ask()` - 8 edges
9. `new_team()` - 8 edges
10. `temp_team()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Run-to-run variance experiment (2026-10-27/28)` --references--> `preflight_cache()`  [INFERRED]
  docs/commands.md → simulate.py
- `What went wrong first (read this before the numbers)` --references--> `preflight_cache()`  [INFERRED]
  docs/variance-experiment.md → simulate.py
- `one()` --indirect_call--> `client()`  [INFERRED]
  simulate.py → test_gateway.py
- `run()` --indirect_call--> `client()`  [INFERRED]
  simulate.py → test_gateway.py
- `main()` --calls--> `master_key()`  [EXTRACTED]
  concurrency_profile.py → seed_teams.py

## Import Cycles
- None detected.

## Communities (20 total, 4 thin omitted)

### Community 0 - "seed_teams.py"
Cohesion: 0.09
Nodes (32): main(), Apply per-team concurrency caps (max_parallel_requests) to the seeded teams'…, concurrent_futures, ask(), new_key(), nodes(), probe_cap(), probe_failover() (+24 more)

### Community 1 - "simulate.py"
Cohesion: 0.08
Nodes (33): asyncio, datetime, Random, checks(), controller(), cross_check_database(), current_caps(), discover_models() (+25 more)

### Community 2 - "test_tokens.py"
Cohesion: 0.13
Nodes (25): psycopg, main(), Reset the spend counters of the 5 seeded teams (and their keys) to zero.…, admin(), ask(), db(), log_rows(), new_team() (+17 more)

### Community 3 - "test_observability.py"
Cohesion: 0.14
Nodes (24): admin(), ask(), dashboard_panels(), env_value(), grafana_query(), new_team(), prom(), prom_value() (+16 more)

### Community 4 - "Command log"
Cohesion: 0.08
Nodes (24): Command log, Experiment: capacity-matched fallback and shorter cooldown, Experiment: dedicated node pool for research, Experiment: fallback concurrency limit and second fallback node, Experiment: per-team concurrency caps, Increment 0: Single-model gateway, Increment 1: PostgreSQL in Docker, Increment 2: Five teams, keys, limits, budgets (+16 more)

### Community 5 - "test_gateway.py"
Cohesion: 0.15
Nodes (11): pytest, assert_rejected(), auth(), chat(), client(), fixture, Sunny (happy path) and rainy (failure path) tests for the LiteLLM gateway.…, test_rainy_missing_api_key() (+3 more)

### Community 6 - "pathlib"
Cohesion: 0.17
Nodes (13): argparse, Generate a config variant that hardens the shared llama3 fallback. gateway-…, Generate experiments/litellm_config.pool.yaml from litellm_config.yaml.…, pathlib, subprocess, fallbacks(), generate(), The experiment config generators produce what their docs claim (no gateway… (+5 more)

### Community 7 - "compare_runs.py"
Cohesion: 0.16
Nodes (14): collections, fmt(), main(), metrics(), near_burst(), pct(), Compare saved simulation runs side by side. gateway-env/bin/python…, json (+6 more)

### Community 8 - "test_teams.py"
Cohesion: 0.21
Nodes (15): admin(), ask(), fixture, parametrize, Increment 2: per-team keys, limits and budgets. Destructive checks (RPM / TPM /…, Factory for a throwaway team + key; cleaned up after the test., team_keys(), temp_team() (+7 more)

### Community 9 - "test_cache.py"
Cohesion: 0.29
Nodes (13): admin(), ask(), new_key(), fixture, parametrize, Increment 5: Redis semantic cache. A cache hit is marked by the x-litellm-…, test_rainy_another_teams_cache_is_never_served(), test_rainy_cache_hits_still_count_toward_rpm() (+5 more)

### Community 10 - "test_failover.py"
Cohesion: 0.28
Nodes (14): ask(), key(), fixture, Increment 4: node failure, retries, model fallback and recovery. Stops and…, Poll until all three primaries answer again (cooldown is 30s)., Call stop_nodes([ports]); everything is restarted afterwards., run_script(), stop_nodes() (+6 more)

### Community 11 - "Experiment: a concurrency limit and a second node for the shared fallback"
Cohesion: 0.17
Nodes (11): Corrections to earlier experiments, Experiment: a concurrency limit and a second node for the shared fallback, Findings, Follow-up: capacity-matched fallback and a shorter cooldown, Follow-up caveats, Follow-up findings, Method, Recommendation (+3 more)

### Community 12 - "Experiment: per-team concurrency caps"
Cohesion: 0.22
Nodes (8): Current state and recommendations, Experiment: per-team concurrency caps, Findings, Measurement corrections made along the way, Method, Open observations, Reproduce, Results

### Community 13 - "Experiment: a dedicated node pool for the heavy team"
Cohesion: 0.22
Nodes (8): Current state and reproduce, Experiment: a dedicated node pool for the heavy team, Findings, Recommendation, Results (one full simulation run each, 210 s, same profiles), Setup, Trade-offs, Verification before the run (`experiments/pool_probes.py`)

### Community 14 - "LLM Gateway Production Simulation: Roadmap"
Cohesion: 0.25
Nodes (7): Environment (measured 2026-10-26), Increments, Known limits to keep in mind, LLM Gateway Production Simulation: Roadmap, Ollama cluster: feasibility, Open issues, Teams

### Community 15 - "Traffic simulation report"
Cohesion: 0.29
Nodes (6): Caveats, Findings, Reproduce, Results, Setup, Traffic simulation report

## Knowledge Gaps
- **56 isolated node(s):** `start_nodes.sh script`, `stop_nodes.sh script`, `init_grafana_db_role.sh script`, `restart_gateway.sh script`, `Environment (measured 2026-10-26)` (+51 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 136 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `preflight_cache()` connect `Command log` to `simulate.py`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Why does `master_key()` connect `seed_teams.py` to `simulate.py`, `test_tokens.py`, `test_observability.py`, `test_teams.py`, `test_cache.py`, `test_failover.py`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `run()` (e.g. with `nodes()` and `client()`) actually correct?**
  _`run()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `start_nodes.sh script`, `stop_nodes.sh script`, `init_grafana_db_role.sh script` to the rest of the system?**
  _56 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `seed_teams.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08846153846153847 - nodes in this community are weakly interconnected._
- **Should `simulate.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08408408408408409 - nodes in this community are weakly interconnected._
- **Should `test_tokens.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._