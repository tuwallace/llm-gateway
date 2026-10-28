"""Verify the dedicated research pool is wired correctly (run with the pool config + `pool_profile.py on`).

    gateway-env/bin/python experiments/pool_probes.py

  1. research can use research-model, served only by research-node
  2. research cannot use the shared alias; other teams cannot use research-model
  3. shared-alias traffic never lands on research-node
  4. the scenario this is for: a 25-request research burst does not slow a quiet team
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from seed_teams import BASE_URL, KEYS_FILE  # noqa: E402

KEYS = json.loads(KEYS_FILE.read_text())


def ask(team, model, tokens=8, text="hi", cache=False):
    body = {"model": model, "max_tokens": tokens, "messages": [{"role": "user", "content": text}]}
    if not cache:
        body["cache"] = {"no-cache": True}
    t = time.time()
    r = httpx.post(f"{BASE_URL}/v1/chat/completions", headers={"Authorization": f"Bearer {KEYS[team]['key']}"}, json=body, timeout=120)
    return r.status_code, r.headers.get("x-litellm-model-id"), time.time() - t


def main() -> None:
    code, node, _ = ask("research", "research-model")
    print(f"1. research -> research-model: {code}, served by {node}")
    assert code == 200 and node == "research-node"

    denied_a = ask("research", "my-educational-model")[0]
    denied_b = ask("support", "research-model")[0]
    print(f"2. research -> shared alias: {denied_a};  support -> research-model: {denied_b}")
    assert denied_a in (401, 403) and denied_b in (401, 403)

    nodes = {ask(team, "my-educational-model")[1] for team in ("support", "search", "analytics") for _ in range(8)}
    print(f"3. shared-alias requests were served by: {sorted(nodes)}")
    assert "research-node" not in nodes and nodes <= {"node-1", "node-2"}

    # 4. burst of 25 research requests (200 tokens each), then support requests during it
    def burst(i):
        return ask("research", "research-model", 200, f"Write a detailed paragraph about topic {i}.")[0]
    with ThreadPoolExecutor(26) as pool:
        futures = [pool.submit(burst, i) for i in range(25)]
        time.sleep(1.5)
        support = [ask("support", "my-educational-model", 40, f"Reply politely, variant {i}.")[2] for i in range(5)]
        codes = [f.result() for f in futures]
    print(f"4. during a 25-request research burst, support latency: median {sorted(support)[2]:.1f}s, max {max(support):.1f}s "
          f"(baseline without isolation: ~32 s median); research burst finished with {codes.count(200)} ok, {codes.count(429)} rejected")
    assert sorted(support)[2] < 6, "support was slowed by the research burst"
    print("pool behaves as designed")


if __name__ == "__main__":
    main()
