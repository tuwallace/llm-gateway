#!/bin/sh
# Restart the LiteLLM gateway (detached) and wait until it is live.
#   ./restart_gateway.sh            restart
#   ./restart_gateway.sh --reset    zero the seeded teams' spend first (clean quotas for a run)
#   CONFIG=path ./restart_gateway.sh   use another config file (default litellm_config.yaml)
# The gateway keeps spend counters in memory, so a database reset only takes effect
# after a restart; this script does both in the right order.
cd "$(dirname "$0")" || exit 1
LOG="${GATEWAY_LOG:-gateway.log}"
[ "$1" = "--reset" ] && gateway-env/bin/python reset_team_spend.py | tail -1
pkill -f "litellm --config" 2>/dev/null; sleep 2
PATH="$PWD/gateway-env/bin:$PATH" nohup gateway-env/bin/litellm --config "${CONFIG:-litellm_config.yaml}" --port 4000 > "$LOG" 2>&1 &
for i in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:4000/health/liveliness)" = 200 ] && { echo "gateway up (log: $LOG)"; exit 0; }
  sleep 2
done
echo "gateway did not come up; see $LOG" >&2; exit 1
