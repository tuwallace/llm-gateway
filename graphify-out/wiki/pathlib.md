# pathlib

> 18 nodes

## Key Concepts

- **pathlib** (14 connections)
- **test_experiment_configs.py** (11 connections) — `test_experiment_configs.py`
- **generate()** (5 connections) — `test_experiment_configs.py`
- **make_fallback_config.py** (5 connections) — `experiments/make_fallback_config.py`
- **fallbacks()** (4 connections) — `test_experiment_configs.py`
- **make_pool_config.py** (4 connections) — `experiments/make_pool_config.py`
- **subprocess** (4 connections)
- **yaml** (4 connections)
- **test_limit_and_cooldown_are_applied()** (3 connections) — `test_experiment_configs.py`
- **test_second_node_adds_one_llama3_deployment()** (3 connections) — `test_experiment_configs.py`
- **test_standby_pool_replaces_llama3_with_three_phi3_nodes()** (3 connections) — `test_experiment_configs.py`
- **argparse** (3 connections)
- **test_primaries_and_embeddings_are_untouched()** (2 connections) — `test_experiment_configs.py`
- **main()** (1 connections) — `experiments/make_fallback_config.py`
- **main()** (1 connections) — `experiments/make_pool_config.py`
- **Generate a config variant that hardens the shared llama3 fallback. gateway-…** (1 connections) — `experiments/make_fallback_config.py`
- **Generate experiments/litellm_config.pool.yaml from litellm_config.yaml.…** (1 connections) — `experiments/make_pool_config.py`
- **The experiment config generators produce what their docs claim (no gateway…** (1 connections) — `test_experiment_configs.py`

## Relationships

- [test_tokens.py](test_tokens.py.md) (4 shared connections)
- [seed_teams.py](seed_teams.py.md) (4 shared connections)
- [compare_runs.py](compare_runs.py.md) (3 shared connections)
- [simulate.py](simulate.py.md) (3 shared connections)
- [test_failover.py](test_failover.py.md) (2 shared connections)
- [test_gateway.py](test_gateway.py.md) (1 shared connections)
- [test_observability.py](test_observability.py.md) (1 shared connections)

## Source Files

- `experiments/make_fallback_config.py`
- `experiments/make_pool_config.py`
- `test_experiment_configs.py`

## Audit Trail

- EXTRACTED: 44 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*