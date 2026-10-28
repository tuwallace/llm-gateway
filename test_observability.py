"""Increment 7: Prometheus metrics and the Grafana dashboard.

Needs the gateway, Prometheus (:9090) and Grafana (:3000) running. Metrics are
checked against what the API itself returned, using throwaway teams (their
alias becomes the `team_alias` label, so each test reads only its own series).

Prometheus scrapes every 5 s, so counter checks poll for up to 30 s.
"""
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

from seed_teams import BASE_URL, MODELS, PRICE_PER_TOKEN, TOKEN_QUOTAS, master_key
from usage_report import HEALTH_TEAM

ROOT = Path(__file__).parent
PROM = "http://localhost:9090"
GRAFANA = "http://localhost:3000"
CHAT = 'route="/v1/chat/completions",requested_model="my-educational-model"'


def env_value(name):
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise KeyError(name)


SEEDED_LIST = ", ".join(f"'{alias}'" for alias in TOKEN_QUOTAS)


def dashboard_panels():
    return json.loads((ROOT / "observability/grafana/dashboards/llm-gateway.json").read_text())["panels"]


def grafana_query(target):
    """Run one panel target through Grafana; return the last column's values."""
    r = httpx.post(f"{GRAFANA}/api/ds/query", auth=("admin", env_value("GRAFANA_PASSWORD")), timeout=30,
                   json={"queries": [{**target, "intervalMs": 1000, "maxDataPoints": 100}],
                         "from": "now-5m", "to": "now"}).json()
    return r["results"]["A"]["frames"][0]["data"]["values"][-1]


def prom(expr):
    r = httpx.get(f"{PROM}/api/v1/query", params={"query": expr}, timeout=30).json()
    assert r["status"] == "success", (expr, r)
    return r["data"]["result"]


def prom_value(expr):
    result = prom(expr)
    return float(result[0]["value"][1]) if result else 0.0


def wait_for(expr, want, timeout=30):
    """Poll a Prometheus expression until it equals `want` (scrape lag)."""
    end, got = time.time() + timeout, None
    while time.time() < end:
        got = prom_value(expr)
        if got == pytest.approx(want):
            return got
        time.sleep(2)
    raise AssertionError(f"{expr} = {got}, wanted {want} after {timeout}s")


@pytest.fixture(scope="module")
def admin():
    with httpx.Client(
        base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=60
    ) as c:
        try:
            c.get("/health/liveliness")
            httpx.get(f"{PROM}/-/ready", timeout=5)
        except httpx.ConnectError:
            pytest.skip("gateway or Prometheus not reachable")
        yield c


@pytest.fixture
def new_team(admin):
    teams = []

    def make(**limits):
        alias = f"tmp-{uuid.uuid4().hex[:8]}"
        team = admin.post("/team/new", json={"team_alias": alias, "models": MODELS,
                                             "rpm_limit": limits.pop("rpm_limit", 1000), **limits}).json()["team_id"]
        teams.append(team)
        key = admin.post("/key/generate", json={"team_id": team, "models": MODELS}).json()["key"]
        return alias, key

    yield make
    if teams:
        admin.post("/team/delete", json={"team_ids": teams})


def ask(key, prompt="Write one sentence about the sea.", cache=False):
    body = {"model": MODELS[0], "max_tokens": 12, "messages": [{"role": "user", "content": prompt}]}
    if not cache:
        body["cache"] = {"no-cache": True}
    return httpx.post(f"{BASE_URL}/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)


def requests_counter(alias, status):
    return (f'sum(litellm_proxy_total_requests_metric_total{{{CHAT},team_alias="{alias}",status_code="{status}"}})')


# ---------- sunny: the stack is wired up ----------

def test_sunny_prometheus_is_scraping_the_gateway(admin):
    targets = httpx.get(f"{PROM}/api/v1/targets", timeout=10).json()["data"]["activeTargets"]
    gateway = [t for t in targets if t["labels"]["job"] == "litellm"]
    assert gateway and gateway[0]["health"] == "up", gateway


def test_sunny_grafana_has_datasource_and_dashboard():
    auth = ("admin", env_value("GRAFANA_PASSWORD"))
    sources = httpx.get(f"{GRAFANA}/api/datasources", auth=auth, timeout=10).json()
    assert {d["uid"] for d in sources} == {"prometheus", "postgres"}
    health = httpx.get(f"{GRAFANA}/api/datasources/uid/postgres/health", auth=auth, timeout=10).json()
    assert health["status"] == "OK", health
    dash = httpx.get(f"{GRAFANA}/api/dashboards/uid/llm-gateway", auth=auth, timeout=10).json()["dashboard"]
    assert len(dash["panels"]) == len(json.loads((ROOT / "observability/grafana/dashboards/llm-gateway.json").read_text())["panels"])


def test_sunny_dashboard_counts_traffic_served_by_the_fallback():
    # Requests answered by the fallback model carry requested_model="my-fallback-model".
    # A primary-only filter made the dashboard show traffic dropping during an outage.
    counted = ("litellm_proxy_total_requests_metric_total", "litellm_total_tokens_metric_total",
               "litellm_request_total_latency_metric_bucket")
    exprs = [t["expr"] for p in dashboard_panels() for t in p["targets"] if "expr" in t]
    for expr in exprs:
        # Panels with no model filter (e.g. rejected requests, which include
        # unauthenticated callers) already count everything; the bug is a filter
        # that names the primary model only.
        if any(m in expr for m in counted) and "requested_model" in expr:
            assert "my-fallback-model" in expr and "research-model" in expr, expr
    node_panel = next(p for p in dashboard_panels() if p["title"].startswith("Uncached requests"))
    assert "fallback-node" in node_panel["targets"][0]["expr"] and "research-node" in node_panel["targets"][0]["expr"]


def test_sunny_dashboard_file_is_up_to_date():
    sys.path.insert(0, str(ROOT / "observability"))
    from build_dashboard import dashboard
    on_disk = json.loads((ROOT / "observability/grafana/dashboards/llm-gateway.json").read_text())
    assert on_disk == json.loads(json.dumps(dashboard)), "run observability/build_dashboard.py"


def test_sunny_every_dashboard_query_is_valid_promql():
    checked = 0
    for p in dashboard_panels():
        for t in p["targets"]:
            if "expr" in t:  # SQL panels are covered by the Grafana quota test
                prom(t["expr"].replace("$__rate_interval", "1m"))  # asserts status == success
                checked += 1
    assert checked >= 12


# ---------- sunny: metrics agree with the API ----------

def test_sunny_request_and_token_counters_match_what_the_api_returned(new_team):
    alias, key = new_team()
    responses = [ask(key) for _ in range(5)]
    assert all(r.status_code == 200 for r in responses)
    tokens = sum(r.json()["usage"]["total_tokens"] for r in responses)

    wait_for(requests_counter(alias, 200), 5)
    wait_for(f'sum(litellm_total_tokens_metric_total{{requested_model="my-educational-model",team_alias="{alias}"}})', tokens)


def test_sunny_cache_hits_are_counted_per_team(new_team):
    alias, key = new_team()
    ask(key, "Name a primary colour.", cache=True)
    hits = [ask(key, "Name a primary colour.", cache=True) for _ in range(3)]
    assert all("x-litellm-cache-key" in r.headers for r in hits)
    wait_for(f'sum(litellm_cache_hits_metric_total{{team_alias="{alias}"}})', 3)


def test_sunny_quota_panels_show_true_tokens_remaining_via_grafana(new_team):
    # Runs the dashboard's own SQL through Grafana (so the datasource and the
    # read-only role are exercised), with the seeded-team list swapped for a
    # throwaway team.
    alias, key = new_team(max_budget=1000 * PRICE_PER_TOKEN)
    used = ask(key).json()["usage"]["total_tokens"]
    panel = next(p for p in dashboard_panels() if p["title"] == "Tokens remaining")
    target = dict(panel["targets"][0])
    target["rawSql"] = target["rawSql"].replace(SEEDED_LIST, f"'{alias}'")
    assert f"'{alias}'" in target["rawSql"], "dashboard SQL no longer has the seeded-team list"

    end, remaining = time.time() + 60, None
    while time.time() < end:  # LiteLLM writes spend to the database in batches
        remaining = grafana_query(target)
        if remaining == [pytest.approx(1000 - used, abs=1)]:
            return
        time.sleep(3)
    pytest.fail(f"Grafana showed {remaining} tokens remaining, wanted {1000 - used}")


def test_rainy_grafana_db_role_is_read_only_and_narrow():
    import psycopg
    dsn = f"postgresql://grafana_ro:{env_value('GRAFANA_DB_PASSWORD')}@localhost:5433/litellm"
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute('SELECT team_alias, spend, max_budget FROM "LiteLLM_TeamTable" LIMIT 1')
        for denied in ('SELECT * FROM "LiteLLM_VerificationToken" LIMIT 1',   # key hashes
                       'SELECT metadata FROM "LiteLLM_TeamTable" LIMIT 1',    # other team columns
                       'SELECT * FROM "LiteLLM_SpendLogs" LIMIT 1',
                       'UPDATE "LiteLLM_TeamTable" SET spend = 0'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(denied)


def test_sunny_platform_noise_is_excluded_from_team_queries():
    # The health-check pseudo-team and unauthenticated callers must never show
    # up in the dashboard's per-team series.
    teams = {r["metric"].get("team_alias") for r in prom(
        f'sum by (team_alias) (litellm_proxy_total_requests_metric_total{{{CHAT},team_alias!~"litellm-internal-health-check|None"}})')}
    assert HEALTH_TEAM not in teams and "None" not in teams


# ---------- rainy: failures are visible ----------

def test_rainy_rate_limited_requests_appear_as_429(new_team):
    alias, key = new_team(rpm_limit=1)
    codes = [ask(key).status_code for _ in range(4)]
    assert codes[0] == 200 and codes.count(429) >= 1, codes
    wait_for(requests_counter(alias, 429), codes.count(429))


def test_rainy_exhausted_quota_appears_as_422(new_team):
    alias, key = new_team(max_budget=30 * PRICE_PER_TOKEN)
    codes = []
    for _ in range(6):
        codes.append(ask(key).status_code)
        if codes[-1] != 200:
            break
        time.sleep(1)
    assert 422 in codes, codes
    wait_for(requests_counter(alias, 422), codes.count(422))


def test_rainy_scraper_key_is_limited_to_metrics(admin):
    key = (ROOT / "observability" / "scraper.key").read_text().strip()
    auth = {"Authorization": f"Bearer {key}"}
    assert httpx.get(f"{BASE_URL}/metrics/", headers=auth, timeout=10).status_code == 200
    assert httpx.get(f"{BASE_URL}/metrics/", timeout=10).status_code == 401  # no key at all
    chat = httpx.post(f"{BASE_URL}/v1/chat/completions", headers=auth, timeout=30,
                      json={"model": MODELS[0], "messages": [{"role": "user", "content": "hi"}]})
    assert chat.status_code == 403
    assert httpx.get(f"{BASE_URL}/team/list", headers=auth, timeout=10).status_code == 403
