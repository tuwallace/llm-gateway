"""Sunny (happy path) and rainy (failure path) tests for the LiteLLM gateway.

Requires the gateway running on localhost:4000 and LITELLM_MASTER_KEY set
(loaded from .env if present).
"""
import os
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("GATEWAY_URL", "http://localhost:4000")
MODEL = "my-educational-model"


def _load_master_key() -> str | None:
    key = os.environ.get("LITELLM_MASTER_KEY")
    if key:
        return key
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LITELLM_MASTER_KEY="):
                return line.split("=", 1)[1].strip()
    return None


MASTER_KEY = _load_master_key()


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=120) as c:
        try:
            c.get("/health/liveliness")
        except httpx.ConnectError:
            pytest.skip(f"gateway not reachable at {BASE_URL}")
        yield c


@pytest.fixture
def auth():
    if not MASTER_KEY:
        pytest.skip("LITELLM_MASTER_KEY not set")
    return {"Authorization": f"Bearer {MASTER_KEY}"}


def chat(client, headers, **overrides):
    body = {"model": MODEL, "messages": [{"role": "user", "content": "hi"}]}
    body.update(overrides)
    return client.post("/v1/chat/completions", headers=headers, json=body)


# ---------- sunny ----------

def test_sunny_liveliness(client):
    assert client.get("/health/liveliness").status_code == 200


def test_sunny_lists_configured_model(client, auth):
    r = client.get("/v1/models", headers=auth)
    assert r.status_code == 200
    assert MODEL in [m["id"] for m in r.json()["data"]]


def test_sunny_chat_completion(client, auth):
    r = chat(client, auth)
    assert r.status_code == 200
    data = r.json()
    assert data["model"] == MODEL
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"].strip()
    assert data["usage"]["total_tokens"] > 0


def test_sunny_streaming(client, auth):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "say hi"}],
        "stream": True,
    }
    with client.stream("POST", "/v1/chat/completions", headers=auth, json=body) as r:
        assert r.status_code == 200
        lines = [l for l in r.iter_lines() if l.startswith("data:")]
    assert lines and lines[-1].strip() == "data: [DONE]"


# ---------- rainy ----------

def assert_rejected(r):
    # Needs the Postgres-backed gateway; without a DB LiteLLM answers 400/500.
    assert r.status_code == 401
    assert "choices" not in r.text


def test_rainy_missing_api_key(client):
    assert_rejected(chat(client, headers={}))


def test_rainy_wrong_api_key(client):
    assert_rejected(chat(client, headers={"Authorization": "Bearer sk-not-the-key"}))


def test_rainy_unknown_model(client, auth):
    r = chat(client, auth, model="no-such-model")
    assert r.status_code in (400, 404)


def test_rainy_missing_messages(client, auth):
    r = client.post("/v1/chat/completions", headers=auth, json={"model": MODEL})
    assert r.status_code >= 400


def test_rainy_malformed_json(client, auth):
    r = client.post(
        "/v1/chat/completions",
        headers={**auth, "Content-Type": "application/json"},
        content="{not json",
    )
    assert r.status_code >= 400


def test_rainy_unknown_route(client, auth):
    assert client.get("/v1/does-not-exist", headers=auth).status_code == 404
