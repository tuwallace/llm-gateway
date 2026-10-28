# test_gateway.py

> 19 nodes

## Key Concepts

- **test_gateway.py** (20 connections) — `test_gateway.py`
- **pytest** (7 connections)
- **chat()** (5 connections) — `test_gateway.py`
- **client()** (4 connections) — `test_gateway.py`
- **assert_rejected()** (3 connections) — `test_gateway.py`
- **test_rainy_missing_api_key()** (3 connections) — `test_gateway.py`
- **test_rainy_wrong_api_key()** (3 connections) — `test_gateway.py`
- **auth()** (2 connections) — `test_gateway.py`
- **test_rainy_unknown_model()** (2 connections) — `test_gateway.py`
- **test_sunny_chat_completion()** (2 connections) — `test_gateway.py`
- **fixture** (2 connections)
- **_load_master_key()** (1 connections) — `test_gateway.py`
- **test_rainy_malformed_json()** (1 connections) — `test_gateway.py`
- **test_rainy_missing_messages()** (1 connections) — `test_gateway.py`
- **test_rainy_unknown_route()** (1 connections) — `test_gateway.py`
- **test_sunny_lists_configured_model()** (1 connections) — `test_gateway.py`
- **test_sunny_liveliness()** (1 connections) — `test_gateway.py`
- **test_sunny_streaming()** (1 connections) — `test_gateway.py`
- **Sunny (happy path) and rainy (failure path) tests for the LiteLLM gateway.…** (1 connections) — `test_gateway.py`

## Relationships

- [seed_teams.py](seed_teams.py.md) (3 shared connections)
- [simulate.py](simulate.py.md) (2 shared connections)
- [pathlib](pathlib.md) (1 shared connections)
- [test_cache.py](test_cache.py.md) (1 shared connections)
- [test_failover.py](test_failover.py.md) (1 shared connections)
- [test_observability.py](test_observability.py.md) (1 shared connections)
- [test_teams.py](test_teams.py.md) (1 shared connections)
- [test_tokens.py](test_tokens.py.md) (1 shared connections)

## Source Files

- `test_gateway.py`

## Audit Trail

- EXTRACTED: 34 (94%)
- INFERRED: 2 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*