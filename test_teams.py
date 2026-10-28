"""Increment 2: per-team keys, limits and budgets.

Destructive checks (RPM / TPM / budget exhaustion) run against throwaway teams
so the seeded teams' budgets are untouched. Run seed_teams.py first.
"""
import json
import time
import uuid

import httpx
import pytest

from seed_teams import BASE_URL, KEYS_FILE, MODELS, TEAMS, master_key

MODEL = MODELS[0]


@pytest.fixture(scope="module")
def admin():
    with httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {master_key()}"},
        timeout=120,
    ) as c:
        try:
            c.get("/health/liveliness")
        except httpx.ConnectError:
            pytest.skip("gateway not reachable")
        yield c


@pytest.fixture(scope="module")
def team_keys():
    if not KEYS_FILE.exists():
        pytest.skip("run seed_teams.py first")
    return json.loads(KEYS_FILE.read_text())


@pytest.fixture
def temp_team(admin):
    """Factory for a throwaway team + key; cleaned up after the test."""
    created = []

    def make(**limits):
        r = admin.post(
            "/team/new",
            json={"team_alias": f"tmp-{uuid.uuid4().hex[:8]}", "models": MODELS, **limits},
        )
        r.raise_for_status()
        team_id = r.json()["team_id"]
        k = admin.post("/key/generate", json={"team_id": team_id, "models": MODELS})
        k.raise_for_status()
        created.append(team_id)
        return k.json()["key"]

    yield make
    if created:
        admin.post("/team/delete", json={"team_ids": created})


def ask(key, model=MODEL, max_tokens=5):
    return httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        # no-cache: the semantic cache would answer repeats without spending budget
        json={"model": model, "max_tokens": max_tokens, "cache": {"no-cache": True},
              "messages": [{"role": "user", "content": "hi"}]},
        timeout=120,
    )


# ---------- sunny ----------

@pytest.mark.parametrize("alias", list(TEAMS))
def test_sunny_team_limits_are_stored(admin, team_keys, alias):
    info = admin.get("/team/info", params={"team_id": team_keys[alias]["team_id"]}).json()["team_info"]
    want = TEAMS[alias]
    assert info["rpm_limit"] == want["rpm_limit"]
    assert info["tpm_limit"] == want["tpm_limit"]
    assert info["max_budget"] == pytest.approx(want["max_budget"])


@pytest.mark.parametrize("alias", ["search", "support", "analytics", "research"])
def test_sunny_team_key_gets_completion(team_keys, alias):
    r = ask(team_keys[alias]["key"])
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"]


def test_sunny_spend_is_tracked_against_team(admin, temp_team):
    key = temp_team(max_budget=1.0, rpm_limit=10)
    assert ask(key).status_code == 200
    # Spend is written asynchronously in batches.
    for _ in range(15):
        spend = admin.get("/key/info", params={"key": key}).json()["info"]["spend"]
        if spend > 0:
            break
        time.sleep(2)
    assert spend > 0


# ---------- rainy ----------

def test_rainy_rpm_limit_returns_429(temp_team):
    key = temp_team(rpm_limit=2)
    codes = [ask(key).status_code for _ in range(5)]
    assert codes[:2] == [200, 200], codes
    assert 429 in codes[2:], codes


def test_rainy_tpm_limit_returns_429(temp_team):
    key = temp_team(tpm_limit=20, rpm_limit=100)
    codes = [ask(key).status_code for _ in range(4)]
    assert 429 in codes, codes


def test_rainy_budget_exhaustion_blocks_requests(temp_team):
    # ~27 tokens/request at $0.00001/token ~= $0.00027, so $0.0003 lasts ~1 request.
    key = temp_team(max_budget=0.0003, rpm_limit=100)
    last = None
    for _ in range(12):
        last = ask(key)
        if last.status_code != 200:
            break
        time.sleep(2)  # let the async spend update land
    assert last.status_code != 200
    assert "budget" in last.text.lower()


def test_rainy_model_not_allowed_for_team_key(team_keys):
    r = ask(team_keys["search"]["key"], model="some-other-model")
    assert r.status_code in (401, 403)
