# Demo scripts for the LIVE segments

Run from the project root with `gateway-env/bin/python`. None of them prints a key or reads `.env` aloud.

| Script | Segment | Needs gateway | Shows |
|---|---|---|---|
| `seg3_teams.py` | 3 keys, limits, quotas | no | the five teams' RPM, TPM, token quota and the budget it becomes |
| `seg4_cache.py` | 4 semantic cache | yes (cache and embedding node up) | a repeat and a paraphrase hit; a same-shape question about another fact misses |
| `seg5_simulation.py [run.json]` | 5 simulation | no | per-team outcome, support latency during bursts, the outage phase; defaults to `data/baseline-run.json` |

`data/baseline-run.json` is the run quoted in `docs/simulation-report.md` (support 37.9 s during bursts against 1.1 s otherwise).
Check the cache preflight first (`simulate.py` aborts if the embedding node on port 11438 is broken); `seg4_cache.py` will
show all misses if it is.

Measured output of `seg4_cache.py`: miss 0.54 s, HIT 0.05 s, miss 0.54 s, HIT 0.03 s. Times vary; the pattern matters.
