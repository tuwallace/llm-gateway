"""Idempotently create the 5 simulated teams and one virtual key per team.

Keys are written to teams_keys.json (mode 600), never printed.
Usage: gateway-env/bin/python seed_teams.py
"""
import json
import os
import stat
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
BASE_URL = os.environ.get("GATEWAY_URL", "http://localhost:4000")
KEYS_FILE = ROOT / "teams_keys.json"

# LiteLLM budgets are dollars, so a token quota is expressed through an artificial
# price. This must match input/output_cost_per_token in litellm_config.yaml
# (test_tokens.py checks that they agree).
PRICE_PER_TOKEN = 0.00001

# Monthly token quota per team (30 days), plus rate limits.
_QUOTAS = {
    "search":         dict(rpm_limit=60, tpm_limit=20000, token_quota=500_000),
    "support":        dict(rpm_limit=30, tpm_limit=20000, token_quota=200_000),
    "analytics":      dict(rpm_limit=10, tpm_limit=50000, token_quota=500_000),
    "research":       dict(rpm_limit=20, tpm_limit=30000, token_quota=300_000),
    "intern-sandbox": dict(rpm_limit=3,  tpm_limit=500,   token_quota=50),
}
TEAMS = {
    alias: dict(
        rpm_limit=q["rpm_limit"],
        tpm_limit=q["tpm_limit"],
        max_budget=round(q["token_quota"] * PRICE_PER_TOKEN, 8),
        budget_duration="30d",
    )
    for alias, q in _QUOTAS.items()
}
TOKEN_QUOTAS = {alias: q["token_quota"] for alias, q in _QUOTAS.items()}
MODELS = ["my-educational-model"]


def master_key() -> str:
    if os.environ.get("LITELLM_MASTER_KEY"):
        return os.environ["LITELLM_MASTER_KEY"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("LITELLM_MASTER_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("LITELLM_MASTER_KEY not found")


def main() -> None:
    http = httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {master_key()}"},
        timeout=30,
    )
    existing = {t["team_alias"]: t for t in http.get("/team/list").json() if t.get("team_alias")}
    keys = json.loads(KEYS_FILE.read_text()) if KEYS_FILE.exists() else {}

    for alias, limits in TEAMS.items():
        if alias in existing:
            team_id = existing[alias]["team_id"]
            # Reconcile limits so editing TEAMS above and re-running takes effect.
            r = http.post("/team/update", json={"team_id": team_id, "models": MODELS, **limits})
            r.raise_for_status()
            print(f"team {alias}: exists, limits reconciled")
        else:
            r = http.post("/team/new", json={"team_alias": alias, "models": MODELS, **limits})
            r.raise_for_status()
            team_id = r.json()["team_id"]
            print(f"team {alias}: created")

        if alias in keys:
            print(f"  key {alias}: already saved")
            continue
        r = http.post(
            "/key/generate",
            json={"team_id": team_id, "key_alias": f"{alias}-key", "models": MODELS},
        )
        r.raise_for_status()
        keys[alias] = {"team_id": team_id, "key": r.json()["key"]}
        print(f"  key {alias}: created")

    KEYS_FILE.write_text(json.dumps(keys, indent=2))
    KEYS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"wrote {KEYS_FILE.name} ({len(keys)} keys)")


if __name__ == "__main__":
    main()
