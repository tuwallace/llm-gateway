#!/bin/sh
# Start native Ollama nodes with a small context window:
#   11435-11437  primary phi3 cluster
#   11438        fallback node (serves llama3, loaded on first use; also the embedding node)
#   11439-11441  standby/fallback nodes used only by the fallback experiments (llama3 or phi3 depending on
#                the config); they unload after 20 s idle so six models are never resident together
# Port 11434 (the Ollama desktop app) is left alone.
LOGDIR="$(cd "$(dirname "$0")" && pwd)/logs"
mkdir -p "$LOGDIR"
for port in ${NODE_PORTS:-11435 11436 11437 11438 11439 11440 11441}; do
  if curl -s -m 2 "http://127.0.0.1:$port/api/version" >/dev/null; then
    echo "node $port: already running"; continue
  fi
  keep=30m; case "$port" in 11439|11440|11441) keep=20s;; esac
  OLLAMA_HOST="127.0.0.1:$port" OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_KEEP_ALIVE=$keep OLLAMA_NUM_PARALLEL=1 \
    nohup ollama serve > "$LOGDIR/node-$port.log" 2>&1 &
  echo "node $port: started (pid $!)"
done
