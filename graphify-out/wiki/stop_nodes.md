# stop_nodes()

> God node · 10 connections · `test_failover.py`

**Community:** [test_failover.py](test_failover.py.md)

## Connections by Relation

### calls
- wait_all_primaries_serving() `EXTRACTED`
- test_sunny_primaries_recover_after_restart() `EXTRACTED`
- run_script() `EXTRACTED`
- test_rainy_everything_down_returns_error_quickly() `EXTRACTED`
- test_sunny_all_primaries_down_falls_back_to_other_model() `EXTRACTED`
- test_sunny_one_node_down_requests_still_succeed() `EXTRACTED`

### contains
- [test_failover.py](test_failover.py.md) `EXTRACTED`
- stop() `EXTRACTED`

### rationale_for
- Call stop_nodes(\[ports\]); everything is restarted afterwards. `EXTRACTED`

### references
- fixture `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*