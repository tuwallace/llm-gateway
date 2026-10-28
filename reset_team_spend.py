"""Reset the spend counters of the 5 seeded teams (and their keys) to zero.

LiteLLM has no API for this. Only the counters used for budget enforcement are
reset; the spend-log history (what usage_report.py reads) is left untouched.
The gateway caches spend in memory, so it must be restarted afterwards.

    gateway-env/bin/python reset_team_spend.py
"""
import psycopg

from seed_teams import TOKEN_QUOTAS
from usage_report import database_url


def main() -> None:
    aliases = list(TOKEN_QUOTAS)
    with psycopg.connect(database_url()) as conn:
        before = conn.execute(
            'SELECT team_alias, spend FROM "LiteLLM_TeamTable" WHERE team_alias = ANY(%s) ORDER BY 1', (aliases,)
        ).fetchall()
        ids = [r[0] for r in conn.execute(
            'SELECT team_id FROM "LiteLLM_TeamTable" WHERE team_alias = ANY(%s)', (aliases,)).fetchall()]
        conn.execute('UPDATE "LiteLLM_TeamTable" SET spend = 0 WHERE team_id = ANY(%s)', (ids,))
        keys = conn.execute('UPDATE "LiteLLM_VerificationToken" SET spend = 0 WHERE team_id = ANY(%s)', (ids,)).rowcount
    for alias, spend in before:
        print(f"{alias:<16} spend {spend:.6f} -> 0")
    print(f"reset {len(ids)} teams and {keys} keys; restart the gateway to clear its in-memory cache")


if __name__ == "__main__":
    main()
