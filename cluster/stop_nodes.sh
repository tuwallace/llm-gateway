#!/bin/sh
# Stop only the nodes started by start_nodes.sh (never the desktop app on 11434).
for port in ${NODE_PORTS:-11435 11436 11437 11438 11439 11440 11441}; do
  pid=$(lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>/dev/null)
  [ -n "$pid" ] && kill $pid && echo "node $port: stopped (pid $pid)"
done
