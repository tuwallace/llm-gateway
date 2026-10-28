"""Generate the Grafana dashboard JSON (observability/grafana/dashboards/).

Re-run after editing: gateway-env/bin/python observability/build_dashboard.py

Filters keep platform noise out of the numbers:
  CHAT  - user-facing completions only (no /metrics scrapes, no cache-embedding calls)
  TEAM  - real teams only (no health-check pseudo-team, no unauthenticated requests)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from seed_teams import PRICE_PER_TOKEN, TOKEN_QUOTAS  # noqa: E402

OUT = Path(__file__).parent / "grafana" / "dashboards" / "llm-gateway.json"
DS = {"type": "prometheus", "uid": "prometheus"}

# User-facing models only: the shared pool, the fallback (requests served by it carry
# requested_model="my-fallback-model") and the dedicated research pool (experiments/), never ollama-embed.
MODELS_RE = "my-educational-model|my-fallback-model|research-model"
CHAT = f'route="/v1/chat/completions",requested_model=~"{MODELS_RE}"'
TEAM = 'team_alias!~"litellm-internal-health-check|None"'
REQS = "litellm_proxy_total_requests_metric_total"
HITS = "litellm_cache_hits_metric_total"
TOKENS = f'litellm_total_tokens_metric_total{{requested_model=~"{MODELS_RE}",' + TEAM + "}"
LAT = "litellm_request_total_latency_metric_bucket"
PRICE = PRICE_PER_TOKEN

PG = {"type": "grafana-postgresql-datasource", "uid": "postgres"}
SEEDED = ", ".join(f"'{alias}'" for alias in TOKEN_QUOTAS)


def sql(query):
    return {"datasource": PG, "refId": "A", "format": "table", "rawQuery": True, "editorMode": "code", "rawSql": query}


_next_id = [0]


def panel(kind, title, targets, x, y, w, h, unit=None, description=None, **extra):
    _next_id[0] += 1
    p = {
        "id": _next_id[0], "type": kind, "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [
            t if isinstance(t, dict) else {"datasource": DS, "refId": chr(65 + i), "expr": t[0], "legendFormat": t[1]}
            for i, t in enumerate(targets)
        ],
        "fieldConfig": {"defaults": {"unit": unit} if unit else {}, "overrides": []},
        "options": {},
    }
    if description:
        p["description"] = description
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(p.get(key), dict):
            p[key].update(value)
        else:
            p[key] = value
    return p


def stat(title, expr, x, w=6, unit=None, description=None, thresholds=None):
    fc = {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "blue", "value": None}]}}, "overrides": []}
    return panel("stat", title, [(expr, "")], x, 0, w, 4, description=description, fieldConfig=fc,
                 options={"colorMode": "value", "graphMode": "area", "reduceOptions": {"calcs": ["lastNotNull"]}})


def series(title, expr, x, y, w=12, h=8, unit=None, legend="{{team_alias}}", description=None, **extra):
    return panel("timeseries", title, [(expr, legend)], x, y, w, h, unit=unit, description=description, **extra)


# Request rate per team (per minute) and the pieces the stat tiles reuse.
ok_rate = f'sum(rate({REQS}{{{CHAT},{TEAM},status_code="200"}}[$__rate_interval]))'
all_rate = f"sum(rate({REQS}{{{CHAT},{TEAM}}}[$__rate_interval]))"
hit_rate = f"sum(rate({HITS}{{{TEAM}}}[$__rate_interval]))"

panels = [
    stat("Requests / min", f"{all_rate} * 60", 0, unit="reqpm"),
    stat("Tokens / min", f"sum(rate({TOKENS}[$__rate_interval])) * 60", 6, unit="short",
         description="Prompt + completion tokens, all teams."),
    stat("Error rate (non-2xx)",
         f'(sum(rate({REQS}{{{CHAT},{TEAM},status_code!~"2.."}}[$__rate_interval])) / {all_rate}) or vector(0)',
         12, unit="percentunit", thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 0.05}, {"color": "red", "value": 0.2}],
         description="429 rate limits, exhausted budgets and upstream errors, as a share of all requests."),
    stat("Cache hit rate", f"({hit_rate} / {ok_rate}) or vector(0)", 18, unit="percentunit",
         description="Share of successful requests answered from the semantic cache."),

    series("Requests / min by team", f"sum by (team_alias) (rate({REQS}{{{CHAT},{TEAM}}}[$__rate_interval])) * 60", 0, 4, unit="reqpm"),
    series("Tokens / min by team", f"sum by (team_alias) (rate({TOKENS}[$__rate_interval])) * 60", 12, 4, unit="short"),

    series("p95 latency by team",
           f'histogram_quantile(0.95, sum by (le, team_alias) (rate({LAT}{{requested_model=~"{MODELS_RE}",{TEAM}}}[$__rate_interval])))',
           0, 12, unit="s", description="Includes cache hits, which are fast; watch it rise when the cache is cold."),
    series("Non-2xx responses by team and status",
           f'sum by (team_alias, status_code) (rate({REQS}{{{CHAT},{TEAM},status_code!~"2.."}}[$__rate_interval])) * 60',
           12, 12, unit="reqpm", legend="{{team_alias}} {{status_code}}",
           description="429 = RPM/TPM limit, 422 = token quota (budget) exhausted."),

    series("Cache hit rate by team",
           f'sum by (team_alias) (rate({HITS}{{{TEAM}}}[$__rate_interval])) / sum by (team_alias) (rate({REQS}{{{CHAT},{TEAM},status_code="200"}}[$__rate_interval]))',
           0, 20, unit="percentunit"),
    series("Uncached requests / min by node",
           f'(sum by (model_id) (rate({REQS}{{{CHAT},{TEAM},model_id=~"node-.*|fallback-node.*|research-node"}}[$__rate_interval])) '
           f'- (sum by (model_id) (rate({HITS}{{{TEAM},model_id=~"node-.*|fallback-node.*|research-node"}}[$__rate_interval])) or (0 * sum by (model_id) (rate({REQS}{{{CHAT},{TEAM},model_id=~"node-.*|fallback-node.*|research-node"}}[$__rate_interval]))))) * 60',
           12, 20, unit="reqpm", legend="{{model_id}}",
           description="Cache hits carry a node id but no node did any work, so they are subtracted. fallback-node is the llama3 fallback."),

    panel("bargauge", "Token quota remaining",
          [sql(f'SELECT team_alias, GREATEST(1 - spend / NULLIF(max_budget, 0), 0) AS remaining FROM "LiteLLM_TeamTable" WHERE team_alias IN ({SEEDED}) ORDER BY team_alias')],
          0, 28, 12, 8, unit="percentunit",
          description=f"1 - spend / max budget, from the enforced team spend in Postgres (read-only role). 1 token = ${PRICE:.5f}. "
                      "Not taken from LiteLLM's remaining-budget gauge, which goes stale.",
          fieldConfig={"defaults": {"min": 0, "max": 1, "unit": "percentunit", "thresholds": {"mode": "absolute", "steps": [
              {"color": "red", "value": None}, {"color": "orange", "value": 0.1}, {"color": "green", "value": 0.3}]}}, "overrides": []},
          options={"displayMode": "gradient", "orientation": "horizontal", "reduceOptions": {"values": True, "calcs": [], "fields": "/^remaining$/"}}),
    panel("bargauge", "Tokens remaining",
          [sql(f'SELECT team_alias, GREATEST(max_budget - spend, 0) / {PRICE} AS tokens FROM "LiteLLM_TeamTable" WHERE team_alias IN ({SEEDED}) ORDER BY team_alias')],
          12, 28, 6, 8, unit="short",
          fieldConfig={"defaults": {"min": 0, "unit": "short"}, "overrides": []},
          options={"displayMode": "basic", "orientation": "horizontal", "reduceOptions": {"values": True, "calcs": [], "fields": "/^tokens$/"}}),
    panel("stat", "Node health",
          [('litellm_deployment_state{api_base=~"http://localhost:1143.*"}', "{{api_base}}")],
          18, 28, 6, 8,
          description="0 = healthy, 1 = partial outage, 2 = outage.",
          fieldConfig={"defaults": {"mappings": [{"type": "value", "options": {
              "0": {"text": "healthy", "color": "green"}, "1": {"text": "degraded", "color": "orange"}, "2": {"text": "down", "color": "red"}}}],
              "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}}, "overrides": []},
          options={"colorMode": "background", "reduceOptions": {"calcs": ["lastNotNull"]}, "textMode": "value_and_name"}),

    series("Rate limit used (per window) by team",
           'litellm_team_rate_limit_used_metric{' + TEAM + '}',
           0, 36, legend="{{team_alias}} {{rate_limit_type}}",
           description="Requests and tokens counted in the current rate-limit window."),
    series("Rejected requests (all routes, incl. unauthenticated)",
           'sum by (status_code) (rate(litellm_proxy_total_requests_metric_total{route="/v1/chat/completions",status_code!~"2.."}[$__rate_interval])) * 60',
           12, 36, unit="reqpm", legend="{{status_code}}",
           description="Includes 401/403 from callers without a valid team key, which the team panels cannot show."),
]

dashboard = {
    "uid": "llm-gateway",
    "title": "LLM Gateway: teams",
    "tags": ["llm-gateway"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "10s",
    "time": {"from": "now-30m", "to": "now"},
    "panels": panels,
}

if __name__ == "__main__":
    OUT.write_text(json.dumps(dashboard, indent=2))
    print(f"wrote {OUT.relative_to(OUT.parents[3])} ({len(panels)} panels)")
