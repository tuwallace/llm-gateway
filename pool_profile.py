"""Switch the research team between the shared model alias and its dedicated pool.

    gateway-env/bin/python pool_profile.py on     # research may use only `research-model`
    gateway-env/bin/python pool_profile.py off    # back to the shared `my-educational-model`
    gateway-env/bin/python pool_profile.py show

`on` needs the pool config running:
    CONFIG=experiments/litellm_config.pool.yaml ./restart_gateway.sh --reset
Team and key are both updated (a request must pass both). Other teams are untouched.
"""
import json
import sys

import httpx

from seed_teams import BASE_URL, KEYS_FILE, MODELS, master_key

POOL_MODEL = "research-model"


def main(mode: str) -> None:
    entry = json.loads(KEYS_FILE.read_text())["research"]
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=30) as c:
        if mode != "show":
            models = [POOL_MODEL] if mode == "on" else MODELS
            c.post("/team/update", json={"team_id": entry["team_id"], "models": models}).raise_for_status()
            c.post("/key/update", json={"key": entry["key"], "models": models}).raise_for_status()
        team = c.get("/team/info", params={"team_id": entry["team_id"]}).json()["team_info"]
        key = c.get("/key/info", params={"key": entry["key"]}).json()["info"]
        print(f"research team models: {team['models']}   key models: {key['models']}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("on", "off", "show"):
        raise SystemExit(__doc__)
    main(sys.argv[1])
