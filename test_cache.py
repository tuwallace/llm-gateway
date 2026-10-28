"""Increment 5: Redis semantic cache.

A cache hit is marked by the x-litellm-cache-key response header (misses don't
carry it). Each test uses a fresh throwaway team: the cache is bucketed per
key/team, so tests never see each other's entries.
"""
import time
import uuid

import httpx
import pytest

from seed_teams import BASE_URL, MODELS, master_key

PROMPT = "What is the capital of France?"
PARAPHRASES = ["Tell me the capital city of France", "Which city is the capital of France?"]
UNRELATED = "How do I bake sourdough bread?"


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


@pytest.fixture
def new_key(admin):
    teams = []

    def make(**limits):
        team = admin.post(
            "/team/new",
            json={"team_alias": f"tmp-{uuid.uuid4().hex[:8]}", "models": MODELS,
                  "rpm_limit": limits.pop("rpm_limit", 1000), **limits},
        ).json()["team_id"]
        teams.append(team)
        return admin.post("/key/generate", json={"team_id": team, "models": MODELS}).json()["key"]

    yield make
    if teams:
        admin.post("/team/delete", json={"team_ids": teams})


def ask(key, prompt=PROMPT, max_tokens=30):
    start = time.time()
    r = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": MODELS[0], "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.elapsed_s = time.time() - start
    r.hit = "x-litellm-cache-key" in r.headers
    return r


# ---------- sunny ----------

def test_sunny_repeat_prompt_is_a_cache_hit(new_key):
    key = new_key()
    first, second = ask(key), ask(key)
    assert first.status_code == second.status_code == 200
    assert not first.hit and second.hit
    assert second.json()["choices"][0]["message"]["content"] == first.json()["choices"][0]["message"]["content"]
    assert second.elapsed_s < first.elapsed_s


@pytest.mark.parametrize("paraphrase", PARAPHRASES)
def test_sunny_paraphrase_is_a_semantic_hit(new_key, paraphrase):
    key = new_key()
    assert not ask(key).hit
    r = ask(key, paraphrase)
    assert r.status_code == 200 and r.hit


def test_sunny_cache_hit_does_not_add_spend(admin, new_key):
    key = new_key()
    miss = ask(key)
    cost = miss.json()["usage"]["total_tokens"] * 0.00001
    assert all(ask(key).hit for _ in range(5))
    for _ in range(15):  # spend is written asynchronously
        if admin.get("/key/info", params={"key": key}).json()["info"]["spend"] > 0:
            break
        time.sleep(2)
    time.sleep(4)  # let any late writes from the hits land too
    spend = admin.get("/key/info", params={"key": key}).json()["info"]["spend"]
    assert spend == pytest.approx(cost, rel=0.25), (spend, cost)


# ---------- rainy ----------

def test_rainy_unrelated_prompt_is_a_miss(new_key):
    key = new_key()
    ask(key)
    r = ask(key, UNRELATED)
    assert r.status_code == 200 and not r.hit


@pytest.mark.parametrize("lookalike", ["What is the capital of Germany?", "What is the population of France?"])
def test_rainy_same_shape_different_fact_is_a_miss(new_key, lookalike):
    # The classic semantic-cache failure: a similar-looking question must not be
    # answered with the cached answer to a different one.
    key = new_key()
    ask(key)
    assert not ask(key, lookalike).hit


def test_rainy_another_teams_cache_is_never_served(new_key):
    key_a, key_b = new_key(), new_key()
    assert not ask(key_a).hit
    assert ask(key_a).hit  # A's own repeat is cached...
    assert not ask(key_b).hit  # ...but B asking the same thing is not served A's answer
    assert ask(key_b).hit  # and B builds its own entry


def test_rainy_cache_hits_still_count_toward_rpm(new_key):
    # A cache must not let a team bypass its request-rate limit.
    key = new_key(rpm_limit=3)
    codes = [ask(key).status_code for _ in range(6)]
    assert codes[:3] == [200, 200, 200], codes
    assert 429 in codes[3:], codes
