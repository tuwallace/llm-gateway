"""Increment 6: token tracking and token quotas.

Compares what the API returned (usage.*) with what the gateway recorded in the
Postgres spend logs and in usage_report.py. Uses throwaway teams.
"""
import json
import time
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
import yaml

from seed_teams import BASE_URL, KEYS_FILE, MODELS, PRICE_PER_TOKEN, TEAMS, TOKEN_QUOTAS, master_key
from usage_report import HEALTH_TEAM, database_url, team_usage

PROMPT = "Write one sentence about the sea."


@pytest.fixture(scope="module")
def admin():
    with httpx.Client(
        base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=60
    ) as c:
        try:
            c.get("/health/liveliness")
        except httpx.ConnectError:
            pytest.skip("gateway not reachable")
        yield c


@pytest.fixture(scope="module")
def db():
    with psycopg.connect(database_url(), autocommit=True) as conn:
        yield conn


@pytest.fixture
def new_team(admin):
    """Factory returning (team_id, key). Teams are deleted afterwards."""
    teams = []

    def make(token_quota=None):
        body = {"team_alias": f"tmp-{uuid.uuid4().hex[:8]}", "models": MODELS, "rpm_limit": 1000}
        if token_quota is not None:
            body["max_budget"] = token_quota * PRICE_PER_TOKEN
        team = admin.post("/team/new", json=body).json()["team_id"]
        teams.append(team)
        key = admin.post("/key/generate", json={"team_id": team, "models": MODELS}).json()["key"]
        return team, key

    yield make
    if teams:
        admin.post("/team/delete", json={"team_ids": teams})


def ask(key, prompt=PROMPT, cache=False):
    body = {"model": MODELS[0], "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}]}
    if not cache:
        body["cache"] = {"no-cache": True}
    return httpx.post(f"{BASE_URL}/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)


def log_rows(db, team_id, expected, timeout=90):
    """Spend logs are written in batches: wait until `expected` rows exist.

    Completions only: every request also logs a free 9-token cache-embedding
    call under the team's id, which usage_report.py counts as platform overhead.
    """
    end = time.time() + timeout
    rows = []
    while time.time() < end:
        rows = db.execute(
            'SELECT status, cache_hit, prompt_tokens, completion_tokens, total_tokens, spend '
            'FROM "LiteLLM_SpendLogs" WHERE team_id = %s AND call_type = \'acompletion\'', (team_id,)
        ).fetchall()
        if len(rows) >= expected:
            return rows
        time.sleep(2)
    raise AssertionError(f"only {len(rows)}/{expected} spend-log rows after {timeout}s")


def usage_of(responses):
    u = [r.json()["usage"] for r in responses]
    return (sum(x["prompt_tokens"] for x in u), sum(x["completion_tokens"] for x in u),
            sum(x["total_tokens"] for x in u))


# ---------- sunny ----------

def test_sunny_config_price_matches_seed_price():
    cfg = yaml.safe_load((Path(__file__).parent / "litellm_config.yaml").read_text())
    prices = {(m["litellm_params"].get("input_cost_per_token"), m["litellm_params"].get("output_cost_per_token"))
              for m in cfg["model_list"] if m["model_name"] != "ollama-embed"}
    assert prices == {(PRICE_PER_TOKEN, PRICE_PER_TOKEN)}


@pytest.mark.parametrize("alias", list(TEAMS))
def test_sunny_live_team_budget_equals_token_quota_times_price(admin, alias):
    keys = json.loads(KEYS_FILE.read_text())
    info = admin.get("/team/info", params={"team_id": keys[alias]["team_id"]}).json()["team_info"]
    assert info["max_budget"] == pytest.approx(TOKEN_QUOTAS[alias] * PRICE_PER_TOKEN)


def test_sunny_logged_tokens_match_api_usage(db, new_team):
    team, key = new_team()
    responses = [ask(key) for _ in range(4)]
    assert all(r.status_code == 200 for r in responses)
    prompt, completion, total = usage_of(responses)

    rows = log_rows(db, team, 4)
    assert sum(r[2] for r in rows) == prompt
    assert sum(r[3] for r in rows) == completion
    assert sum(r[4] for r in rows) == total
    assert sum(r[5] for r in rows) == pytest.approx(total * PRICE_PER_TOKEN)


def test_sunny_cache_hit_is_logged_free_and_counted_as_saved(db, new_team):
    team, key = new_team()
    miss, hit = ask(key, cache=True), ask(key, cache=True)
    assert "x-litellm-cache-key" in hit.headers

    rows = log_rows(db, team, 2)
    hit_rows = [r for r in rows if r[1] == "True"]
    assert len(hit_rows) == 1 and hit_rows[0][5] == 0  # logged, but spend is zero

    row = next(r for r in team_usage(db, days=1, include_all=True) if r["team_id"] == team)
    assert row["requests"] == 2 and row["cache_hits"] == 1
    assert row["billed_tokens"] == miss.json()["usage"]["total_tokens"]
    assert row["tokens_saved"] == hit.json()["usage"]["total_tokens"]


def test_sunny_report_row_matches_what_the_team_did(db, new_team):
    (team_a, key_a), (team_b, key_b) = new_team(), new_team()
    a = [ask(key_a) for _ in range(3)]
    b = [ask(key_b)]
    log_rows(db, team_a, 3)
    log_rows(db, team_b, 1)

    rows = {r["team_id"]: r for r in team_usage(db, days=1, include_all=True)}
    assert rows[team_a]["requests"] == 3 and rows[team_a]["billed_tokens"] == usage_of(a)[2]
    assert rows[team_b]["requests"] == 1 and rows[team_b]["billed_tokens"] == usage_of(b)[2]


def test_sunny_report_excludes_platform_traffic(db):
    teams = {r["team"] for r in team_usage(db, days=1, include_all=True)}
    assert HEALTH_TEAM not in teams


# ---------- rainy ----------

def test_rainy_token_quota_blocks_and_blocked_requests_are_not_billed(db, new_team):
    quota = 200
    team, key = new_team(token_quota=quota)
    served, codes = [], []
    for _ in range(20):
        r = ask(key)
        codes.append(r.status_code)
        if r.status_code == 200:
            served.append(r)
        else:
            assert "budget" in r.text.lower()
            break
    assert codes[-1] != 200, "quota never blocked"
    assert served, "nothing served before the quota hit"

    tokens = usage_of(served)[2]
    per_request = tokens / len(served)
    # Spend is recorded after each response, so the request that crosses the
    # line is served (measured: one to two requests of overshoot).
    assert tokens <= quota + 3 * per_request, (tokens, quota)

    # The gateway rejects further requests and bills nothing for them.
    assert ask(key).status_code != 200
    time.sleep(6)
    ok_rows = [r for r in log_rows(db, team, len(served)) if r[0] == "success"]
    assert sum(r[4] for r in ok_rows) == tokens
