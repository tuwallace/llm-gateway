#!/bin/sh
# Create (or update) the read-only Postgres role Grafana uses for quota panels.
# It can read four columns of one table and nothing else. Idempotent.
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a
docker exec -i llmgw-postgres psql -v ON_ERROR_STOP=1 -U llmgw -d litellm <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
    CREATE ROLE grafana_ro LOGIN;
  END IF;
END \$\$;
ALTER ROLE grafana_ro WITH PASSWORD '${GRAFANA_DB_PASSWORD}';
GRANT CONNECT ON DATABASE litellm TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM grafana_ro;
GRANT SELECT (team_id, team_alias, spend, max_budget) ON "LiteLLM_TeamTable" TO grafana_ro;
SQL
echo "grafana_ro ready"
