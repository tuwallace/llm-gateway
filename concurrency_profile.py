"""Apply per-team concurrency caps (max_parallel_requests) to the seeded teams' keys.

LiteLLM attaches this limit to API keys, not teams, so the cap is set on each
team's key (each team has one). Excess concurrent requests are rejected with a
429, not queued.

    gateway-env/bin/python concurrency_profile.py caps    # apply CAPS
    gateway-env/bin/python concurrency_profile.py off     # remove all caps
    gateway-env/bin/python concurrency_profile.py show
"""
import json
import sys

import httpx

from seed_teams import BASE_URL, KEYS_FILE, master_key

# Three single-slot phi3 nodes, so three requests can run at once. A heavy team
# (research: 200-token answers) gets one slot's worth; short-answer teams get more.
CAPS = {"search": 3, "support": 3, "analytics": 2, "research": 1, "intern-sandbox": 1}


def main(mode: str) -> None:
    keys = json.loads(KEYS_FILE.read_text())
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=30) as c:
        for team, entry in keys.items():
            if mode != "show":
                value = CAPS[team] if mode == "caps" else None
                c.post("/key/update", json={"key": entry["key"], "max_parallel_requests": value}).raise_for_status()
            info = c.get("/key/info", params={"key": entry["key"]}).json()["info"]
            print(f"{team:<16} max_parallel_requests = {info.get('max_parallel_requests')}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("caps", "off", "show"):
        raise SystemExit(__doc__)
    main(sys.argv[1])
