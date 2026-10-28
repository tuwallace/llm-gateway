"""Increment 4: node failure, retries, model fallback and recovery.

Stops and restarts Ollama nodes 11435-11438 (never the desktop app on 11434).
Fixtures always restore the cluster, even when a test fails.
"""
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from seed_teams import BASE_URL, MODELS, master_key

ROOT = Path(__file__).parent
PRIMARY = {"node-1": 11435, "node-2": 11436, "node-3": 11437}
FALLBACK_PORT = 11438


def run_script(name, ports):
    subprocess.run(
        [str(ROOT / "cluster" / name)],
        env={**os.environ, "NODE_PORTS": " ".join(str(p) for p in ports)},
        check=True, capture_output=True, timeout=60,
    )


def ask(key, **kw):
    return httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        # no-cache: cached answers would never reach a node
        json={"model": MODELS[0], "max_tokens": 3, "cache": {"no-cache": True},
              "messages": [{"role": "user", "content": "hi"}]},
        timeout=kw.get("timeout", 120),
    )


def wait_all_primaries_serving(key, deadline_s=120):
    """Poll until all three primaries answer again (cooldown is 30s)."""
    end = time.time() + deadline_s
    seen = set()
    while time.time() < end:
        seen |= {ask(key).headers.get("x-litellm-model-id") for _ in range(12)}
        if set(PRIMARY) <= seen:
            return
        time.sleep(3)
    raise AssertionError(f"primaries not all serving after {deadline_s}s: {seen}")


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


@pytest.fixture
def stop_nodes(key):
    """Call stop_nodes([ports]); everything is restarted afterwards."""
    stopped = set()

    def stop(ports):
        stopped.update(ports)
        run_script("stop_nodes.sh", ports)
        time.sleep(1)

    yield stop
    if stopped:
        run_script("start_nodes.sh", sorted(stopped))
        wait_all_primaries_serving(key)


# ---------- sunny ----------

def test_sunny_one_node_down_requests_still_succeed(key, stop_nodes):
    stop_nodes([PRIMARY["node-3"]])
    # Before the next health probe, retries mask the dead node. LiteLLM never
    # cools a node down on connection errors, so this window can cost retries.
    assert all(ask(key).status_code == 200 for _ in range(10))

    # After one probe interval (10s) health-check routing skips the node entirely.
    time.sleep(13)
    responses = [ask(key) for _ in range(20)]
    assert [r.status_code for r in responses] == [200] * 20
    assert {r.headers["x-litellm-model-id"] for r in responses} == {"node-1", "node-2"}
    assert {r.headers["x-litellm-attempted-retries"] for r in responses} == {"0"}


def test_sunny_all_primaries_down_falls_back_to_other_model(key, stop_nodes):
    stop_nodes(list(PRIMARY.values()))
    r = ask(key)
    assert r.status_code == 200, r.text
    assert r.headers["x-litellm-model-id"] == "fallback-node"
    assert r.headers["x-litellm-attempted-fallbacks"] == "1"
    assert r.json()["model"] == "ollama/llama3"


def test_sunny_primaries_recover_after_restart(key, stop_nodes):
    stop_nodes([PRIMARY["node-2"]])
    assert all(ask(key).status_code == 200 for _ in range(6))
    # Fixture teardown restarts the node and waits for it to rejoin; check it
    # explicitly here too so the assertion lives in a test.
    run_script("start_nodes.sh", [PRIMARY["node-2"]])
    wait_all_primaries_serving(key)


# ---------- rainy ----------

def test_rainy_everything_down_returns_error_quickly(key, stop_nodes):
    stop_nodes([*PRIMARY.values(), FALLBACK_PORT])
    start = time.time()
    r = ask(key, timeout=60)
    assert r.status_code >= 500, r.text
    assert "choices" not in r.text
    assert time.time() - start < 30  # fails fast, does not hang
