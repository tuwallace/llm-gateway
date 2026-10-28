"""Increment 3: load balancing across the 3-node Ollama cluster.

Needs the nodes (cluster/start_nodes.sh) and the gateway running.
"""
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from seed_teams import BASE_URL, MODELS, master_key

NODES = {"node-1": 11435, "node-2": 11436, "node-3": 11437}


@pytest.fixture(scope="module")
def key():
    admin = httpx.Client(
        base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=60
    )
    try:
        admin.get("/health/liveliness")
    except httpx.ConnectError:
        pytest.skip("gateway not reachable")
    team = admin.post(
        "/team/new",
        json={"team_alias": f"tmp-{uuid.uuid4().hex[:8]}", "models": MODELS, "rpm_limit": 1000},
    ).json()["team_id"]
    k = admin.post("/key/generate", json={"team_id": team, "models": MODELS}).json()["key"]
    yield k
    admin.post("/team/delete", json={"team_ids": [team]})


def ask(key):
    return httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        # no-cache: cached answers would never reach a node
        json={"model": MODELS[0], "max_tokens": 3, "cache": {"no-cache": True},
              "messages": [{"role": "user", "content": "hi"}]},
        timeout=120,
    )


# ---------- sunny ----------

def test_sunny_all_nodes_are_up():
    for name, port in NODES.items():
        r = httpx.get(f"http://127.0.0.1:{port}/api/version", timeout=5)
        assert r.status_code == 200, name


def test_sunny_traffic_spreads_across_all_nodes(key):
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: ask(key), range(36)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses if r.status_code != 200][:1]
    served = Counter(r.headers.get("x-litellm-model-id") for r in responses)
    assert set(served) == set(NODES), served
    # Random shuffle, so only guard against a badly lopsided split.
    assert min(served.values()) >= 3, served


def test_sunny_each_node_has_model_loaded_with_small_context():
    for name, port in NODES.items():
        models = httpx.get(f"http://127.0.0.1:{port}/api/ps", timeout=5).json()["models"]
        assert models, f"{name} has nothing loaded"
        assert models[0]["context_length"] == 4096, name


# ---------- rainy ----------

def test_sunny_response_names_the_serving_node(key):
    # Needed later for per-node observability.
    assert ask(key).headers.get("x-litellm-model-id") in NODES
