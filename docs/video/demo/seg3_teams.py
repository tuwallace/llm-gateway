"""Segment 3: the five teams, their limits and token quotas. Prints no keys."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import seed_teams as s  # noqa: E402

print(f"  price per token: ${s.PRICE_PER_TOKEN:.5f}  (budget = token quota x price)\n")
print(f"  {'team':<16}{'RPM':>5}{'TPM':>8}{'token quota':>13}{'budget $':>10}")
for team, t in s.TEAMS.items():
    print(f"  {team:<16}{t['rpm_limit']:>5}{t['tpm_limit']:>8}{s.TOKEN_QUOTAS[team]:>13,}{t['max_budget']:>10.4f}")
