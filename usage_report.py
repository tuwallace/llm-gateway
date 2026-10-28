"""Per-team token usage report, straight from the gateway's Postgres spend logs.

LiteLLM's own /global/spend/report is enterprise-only, so this reads
"LiteLLM_SpendLogs" directly. Usage:

    gateway-env/bin/python usage_report.py            # last 30 days, seeded teams
    gateway-env/bin/python usage_report.py --days 1 --by-node
"""
import argparse
import os
from pathlib import Path

import psycopg

from seed_teams import PRICE_PER_TOKEN, TOKEN_QUOTAS

ROOT = Path(__file__).parent
HEALTH_TEAM = "litellm-internal-health-check"


def database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("DATABASE_URL not found")


# cache_hit is stored as text ('True' / 'False' / 'None').
TEAM_SQL = """
SELECT
  s.team_id,
  coalesce(t.team_alias, s.team_id)                                              AS team,
  count(*) FILTER (WHERE s.status = 'success')                                   AS requests,
  count(*) FILTER (WHERE s.status = 'success' AND s.cache_hit = 'True')          AS cache_hits,
  count(*) FILTER (WHERE s.status = 'failure')                                   AS failures,
  coalesce(sum(s.prompt_tokens)     FILTER (WHERE s.status = 'success' AND s.cache_hit IS DISTINCT FROM 'True'), 0) AS prompt_tokens,
  coalesce(sum(s.completion_tokens) FILTER (WHERE s.status = 'success' AND s.cache_hit IS DISTINCT FROM 'True'), 0) AS completion_tokens,
  coalesce(sum(s.total_tokens)      FILTER (WHERE s.status = 'success' AND s.cache_hit = 'True'), 0)                AS tokens_saved,
  coalesce(sum(s.spend), 0)                                                      AS spend
FROM "LiteLLM_SpendLogs" s
LEFT JOIN "LiteLLM_TeamTable" t ON t.team_id = s.team_id
WHERE s."startTime" >= now() - make_interval(days => %(days)s)
  AND s.team_id <> ''
  AND s.team_id <> %(health)s
  AND (%(all)s OR t.team_alias = ANY(%(aliases)s))
  AND s.call_type <> 'aembedding'
GROUP BY s.team_id, t.team_alias
ORDER BY 3 DESC
"""

NODE_SQL = """
SELECT coalesce(nullif(model_id, ''), '<none>') AS node,
       count(*) FILTER (WHERE status = 'success' AND cache_hit IS DISTINCT FROM 'True') AS requests,
       coalesce(sum(total_tokens) FILTER (WHERE status = 'success' AND cache_hit IS DISTINCT FROM 'True'), 0) AS tokens
FROM "LiteLLM_SpendLogs"
WHERE "startTime" >= now() - make_interval(days => %(days)s)
  AND team_id <> '' AND team_id <> %(health)s AND call_type <> 'aembedding'
GROUP BY 1 ORDER BY 2 DESC
"""

PLATFORM_SQL = """
SELECT CASE WHEN team_id = %(health)s THEN 'health checks'
            WHEN call_type = 'aembedding' THEN 'cache embeddings' END AS what,
       count(*) AS calls, coalesce(sum(total_tokens), 0) AS tokens
FROM "LiteLLM_SpendLogs"
WHERE "startTime" >= now() - make_interval(days => %(days)s)
  AND (team_id = %(health)s OR call_type = 'aembedding')
GROUP BY 1 ORDER BY 1
"""


def team_usage(conn, days: int = 30, include_all: bool = False) -> list[dict]:
    """One dict per team. Quota fields come from the gateway's own team spend."""
    params = {"days": days, "health": HEALTH_TEAM, "all": include_all, "aliases": list(TOKEN_QUOTAS)}
    with conn.cursor() as cur:
        cur.execute(TEAM_SQL, params)
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for row in rows:
            cur.execute('SELECT spend, max_budget FROM "LiteLLM_TeamTable" WHERE team_id = %s', (row["team_id"],))
            team = cur.fetchone()
            row["billed_tokens"] = row["prompt_tokens"] + row["completion_tokens"]
            row["quota"] = TOKEN_QUOTAS.get(row["team"])
            row["quota_used"] = round(team[0] / PRICE_PER_TOKEN) if team else None
        if not include_all:  # seeded teams with no traffic yet still get a row
            seen = {r["team"] for r in rows}
            cur.execute('SELECT team_id, team_alias, spend FROM "LiteLLM_TeamTable" WHERE team_alias = ANY(%s)',
                        (list(TOKEN_QUOTAS),))
            for team_id, alias, spend in cur.fetchall():
                if alias not in seen:
                    rows.append({"team_id": team_id, "team": alias, "requests": 0, "cache_hits": 0,
                                 "failures": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                 "tokens_saved": 0, "spend": 0, "billed_tokens": 0,
                                 "quota": TOKEN_QUOTAS[alias], "quota_used": round(spend / PRICE_PER_TOKEN)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--all", action="store_true", help="include teams not in seed_teams.py")
    ap.add_argument("--by-node", action="store_true", help="add per-node request counts")
    args = ap.parse_args()

    with psycopg.connect(database_url()) as conn:
        rows = team_usage(conn, args.days, args.all)
        print(f"Token usage, last {args.days} day(s)  (quota used = enforced team spend / ${PRICE_PER_TOKEN:.5f} per token)\n")
        head = f"{'team':<16}{'reqs':>6}{'hits':>6}{'fail':>6}{'prompt':>9}{'compl.':>8}{'billed':>9}{'saved':>8}{'quota':>9}{'used':>9}{'used%':>7}"
        print(head)
        print("-" * len(head))
        for r in rows:
            quota, used = r["quota"], r["quota_used"]
            pct = f"{used / quota:.1%}" if quota and used is not None else "-"
            print(f"{r['team']:<16}{r['requests']:>6}{r['cache_hits']:>6}{r['failures']:>6}"
                  f"{r['prompt_tokens']:>9}{r['completion_tokens']:>8}{r['billed_tokens']:>9}{r['tokens_saved']:>8}"
                  f"{quota if quota is not None else '-':>9}{used if used is not None else '-':>9}{pct:>7}")
        print("\nbilled = prompt + completion tokens actually generated; saved = tokens served from cache")

        with conn.cursor() as cur:
            cur.execute(PLATFORM_SQL, {"days": args.days, "health": HEALTH_TEAM})
            print("\nPlatform overhead (not charged to any team):")
            for what, calls, tokens in cur.fetchall():
                print(f"  {what:<18}{calls:>7} calls{tokens:>9} tokens")
            if args.by_node:
                cur.execute(NODE_SQL, {"days": args.days, "health": HEALTH_TEAM})
                print("\nPer node (all teams, uncached requests):")
                for node, reqs, tokens in cur.fetchall():
                    if len(node) == 64:  # hashed id from before deployments had explicit ids
                        node = "<legacy-id>"
                    print(f"  {node:<16}{reqs:>7} reqs{tokens:>9} tokens")


if __name__ == "__main__":
    main()
