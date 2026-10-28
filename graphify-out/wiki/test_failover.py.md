# test_failover.py

> 15 nodes

## Key Concepts

- **test_failover.py** (19 connections) — `test_failover.py`
- **stop_nodes()** (10 connections) — `test_failover.py`
- **ask()** (6 connections) — `test_failover.py`
- **test_sunny_primaries_recover_after_restart()** (5 connections) — `test_failover.py`
- **wait_all_primaries_serving()** (5 connections) — `test_failover.py`
- **run_script()** (4 connections) — `test_failover.py`
- **key()** (3 connections) — `test_failover.py`
- **test_rainy_everything_down_returns_error_quickly()** (3 connections) — `test_failover.py`
- **test_sunny_all_primaries_down_falls_back_to_other_model()** (3 connections) — `test_failover.py`
- **test_sunny_one_node_down_requests_still_succeed()** (3 connections) — `test_failover.py`
- **stop()** (2 connections) — `test_failover.py`
- **fixture** (2 connections)
- **Increment 4: node failure, retries, model fallback and recovery. Stops and…** (1 connections) — `test_failover.py`
- **Poll until all three primaries answer again (cooldown is 30s).** (1 connections) — `test_failover.py`
- **Call stop_nodes([ports]); everything is restarted afterwards.** (1 connections) — `test_failover.py`

## Relationships

- [seed_teams.py](seed_teams.py.md) (7 shared connections)
- [pathlib](pathlib.md) (2 shared connections)
- [test_gateway.py](test_gateway.py.md) (1 shared connections)

## Source Files

- `test_failover.py`

## Audit Trail

- EXTRACTED: 39 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*