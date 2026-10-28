"""Segment 5: summarise a saved simulation run (no gateway needed). Default: data/baseline-run.json."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import compare_runs as cr  # noqa: E402
import simulate  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "data" / "baseline-run.json")
m = cr.metrics(path)
print("  phases:", "  ".join(f"{n} {s}s" for n, s, _ in simulate.PHASES))
print(f"\n  {'team':<16}{'sent':>6}{'ok':>5}{'429':>5}{'422':>5}")
for t in ("search", "support", "analytics", "research", "intern-sandbox"):
    x = m[t]
    print(f"  {t:<16}{x['sent']:>6}{x['ok']:>5}{x['429']:>5}{x['422']:>5}")
n1, p50d, p95d = m["support_during"]
n2, p50q, p95q = m["support_quiet"]
print(f"\n  support, uncached latency (median / p95)")
print(f"    during a research burst   {p50d:5.1f} s / {p95d:5.1f} s   (n={n1})")
print(f"    otherwise                 {p50q:5.1f} s / {p95q:5.1f} s   (n={n2})")
print(f"\n  all primaries down (phase C): {m['C']['ok']} of {m['C']['sent']} answered, "
      f"{m['C']['hits']} from cache, {m['C']['fallback']} by the fallback node")
print(f"  cache hit rate of successes: {m['hit_rate']:.0%}")
