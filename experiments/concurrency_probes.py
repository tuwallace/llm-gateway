"""Probes behind the per-team concurrency-cap findings (docs/concurrency-experiment.md).

    gateway-env/bin/python experiments/concurrency_probes.py

Takes about 4 minutes. Stops and restarts the Ollama nodes (11435-11438) and always
restores them. Uses throwaway teams only.

  1. cap: a key with max_parallel_requests=2 admits 2 of 6 simultaneous requests
  2. cost: every request the cap rejects is charged 2 units of the team's RPM budget
  3. failover: with the primaries down, a cap-1 key admits staggered requests anyway
"""
import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from seed_teams import BASE_URL, MODELS, master_key  # noqa: E402

admin = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=60)


def nodes(script, ports):
    subprocess.run([str(ROOT / "cluster" / script)], env={**os.environ, "NODE_PORTS": " ".join(map(str, ports))},
                   check=True, capture_output=True, timeout=90)


def new_key(rpm=1000, cap=None):
    team = admin.post("/team/new", json={"team_alias": f"tmp-{uuid.uuid4().hex[:8]}", "models": MODELS, "rpm_limit": rpm}).json()["team_id"]
    body = {"team_id": team, "models": MODELS, **({"max_parallel_requests": cap} if cap else {})}
    return team, admin.post("/key/generate", json=body).json()["key"]


def ask(key, tokens, text=None):
    body = {"model": MODELS[0], "max_tokens": tokens, "cache": {"no-cache": True},
            "messages": [{"role": "user", "content": text or f"Write about {uuid.uuid4().hex[:6]} in detail."}]}
    return httpx.post(f"{BASE_URL}/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120).status_code


def probe_cap():
    team, key = new_key(cap=2)
    with ThreadPoolExecutor(6) as p:
        codes = list(p.map(lambda _: ask(key, 150), range(6)))
    admin.post("/team/delete", json={"team_ids": [team]})
    print(f"1. cap 2, 6 simultaneous requests: admitted {codes.count(200)}, rejected {codes.count(429)}")
    assert codes.count(200) == 2


def probe_rpm_cost():
    print("2. RPM 20, cap 1: one slow request admitted, K rejected by the cap, then count what is accepted")
    for k in (1, 3, 6):
        team, key = new_key(rpm=20, cap=1)
        slow = threading.Thread(target=lambda: ask(key, 200, "Write a long essay about rivers."))
        slow.start(); time.sleep(0.3)
        rejected = sum(ask(key, 3, "hi") == 429 for _ in range(k))
        slow.join()
        accepted = 0
        while ask(key, 3, "hi") == 200 and accepted < 25:
            accepted += 1
        admin.post("/team/delete", json={"team_ids": [team]})
        cost = (20 - accepted - 1) / rejected
        print(f"   K={rejected}: accepted afterwards {accepted} -> {cost:.1f} RPM units per rejected request")
        assert cost == 2.0


def staggered(label, n=6, gap=0.4):
    team, key = new_key(cap=1)
    out = [None] * n
    threads = []
    for i in range(n):
        t = threading.Thread(target=lambda i=i: out.__setitem__(i, ask(key, 120))); t.start(); threads.append(t); time.sleep(gap)
    [t.join() for t in threads]
    admin.post("/team/delete", json={"team_ids": [team]})
    print(f"   {label:<48} admitted {out.count(200)} of {n}")
    return out.count(200)


def probe_failover():
    print("3. cap 1, six requests 0.4 s apart:")
    up = staggered("all nodes up (control)")
    try:
        nodes("stop_nodes.sh", [11435, 11436, 11437]); time.sleep(1)
        down = staggered("primaries just stopped")
        time.sleep(16)
        noticed = staggered("primaries stopped 16 s (health checks noticed)")
    finally:
        nodes("start_nodes.sh", [11435, 11436, 11437, 11438])
    assert up <= 3 and down == 6 and noticed == 6, "expected the cap to hold normally and be bypassed during failover"


if __name__ == "__main__":
    probe_cap()
    probe_rpm_cost()
    probe_failover()
    print("all probes behaved as documented")
