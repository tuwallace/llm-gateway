"""Compare saved simulation runs side by side.

    gateway-env/bin/python compare_runs.py sim_results/run-A.json sim_results/run-B.json ...

The question these answer: do quiet teams wait less when a noisy team bursts, and
what does the noisy team pay for it?
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

BURST_STARTS = (30, 60, 90, 120, 150, 180, 210)  # research bursts, seconds into the run
NEAR = 20  # seconds after a burst starts that count as "during the burst"


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(q * len(values)) - 1)] if values else None


def fmt(v, spec=".1f"):
    return "-" if v is None else format(v, spec)


def near_burst(t):
    return any(0 <= t - b <= NEAR for b in BURST_STARTS)


def metrics(path):
    data = json.loads(Path(path).read_text())
    rows = data["requests"]
    by = lambda team: [r for r in rows if r["team"] == team]
    ok = lambda rs: [r for r in rs if r["status"] == 200]
    uncached = lambda rs: [r["latency"] for r in ok(rs) if not r["hit"]]
    out = {"label": data.get("label") or Path(path).stem, "total": len(rows)}
    for team in ("search", "support", "analytics", "research", "intern-sandbox"):
        rs = by(team)
        c = Counter(str(r["status"]) for r in rs)
        out[team] = {"sent": len(rs), "ok": c["200"], "429": c["429"], "422": c["422"],
                     "bad": sum(v for k, v in c.items() if k not in ("200", "429", "422")),
                     "p50": pct(uncached(rs), 0.5), "p95": pct(uncached(rs), 0.95), "n_uncached": len(uncached(rs))}
    sup = [r for r in by("support") if r["status"] == 200 and not r["hit"]]
    during = [r["latency"] for r in sup if near_burst(r["t"])]
    quiet = [r["latency"] for r in sup if not near_burst(r["t"])]
    out["support_during"] = (len(during), pct(during, 0.5), pct(during, 0.95))
    out["support_quiet"] = (len(quiet), pct(quiet, 0.5), pct(quiet, 0.95))
    c_rows = [r for r in rows if 120 - 0.5 <= r["t"] < 150 - 0.5]  # phase C: all primaries down
    c_ok = [r for r in c_rows if r["status"] == 200]
    out["C"] = {"sent": len(c_rows), "ok": len(c_ok), "hits": sum(r["hit"] for r in c_ok),
                "429": sum(r["status"] == 429 for r in c_rows), "5xx": sum(isinstance(r["status"], int) and r["status"] >= 500 for r in c_rows),
                "timeout": sum(r["status"] == "timeout" for r in c_rows),
                "p50": pct([r["latency"] for r in c_ok if not r["hit"]], 0.5), "p95": pct([r["latency"] for r in c_ok if not r["hit"]], 0.95),
                "fallback": sum(1 for r in c_ok if not r["hit"] and str(r["node"]).startswith("fallback-node"))}
    res = ok(by("research"))
    out["research_done_tokens"] = sum(r["tokens"] for r in res if not r["hit"])
    allok = ok(rows)
    out["hit_rate"] = sum(r["hit"] for r in allok) / max(len(allok), 1)
    out["flushed"] = data.get("cache_flushed", "n/a")
    out["nodes"] = dict(Counter(r["node"] for r in rows if r["status"] == 200 and not r["hit"]))
    return out


def main(paths):
    runs = [metrics(p) for p in paths]
    width = 16
    head = f"{'':<34}" + "".join(f"{r['label'][:width - 1]:>{width}}" for r in runs)
    print(head)
    print("-" * len(head))

    def line(name, fn):
        print(f"{name:<34}" + "".join(f"{fn(r):>{width}}" for r in runs))

    print("Quiet team (support), uncached request latency")
    line("  during a research burst: n", lambda r: r["support_during"][0])
    line("  during a research burst: p50 s", lambda r: fmt(r["support_during"][1]))
    line("  during a research burst: p95 s", lambda r: fmt(r["support_during"][2]))
    line("  otherwise: p50 s", lambda r: fmt(r["support_quiet"][1]))
    line("  otherwise: p95 s", lambda r: fmt(r["support_quiet"][2]))
    line("  support ok / sent", lambda r: f"{r['support']['ok']}/{r['support']['sent']}")
    line("  support rejected (429)", lambda r: r["support"]["429"])
    print("Noisy team (research)")
    line("  ok / sent", lambda r: f"{r['research']['ok']}/{r['research']['sent']}")
    line("  rejected (429)", lambda r: r["research"]["429"])
    line("  uncached latency p50 s", lambda r: fmt(r["research"]["p50"]))
    line("  uncached latency p95 s", lambda r: fmt(r["research"]["p95"]))
    line("  tokens generated (uncached)", lambda r: r["research_done_tokens"])
    print("Other teams")
    for team in ("search", "analytics"):
        line(f"  {team} ok / sent / 429", lambda r, t=team: f"{r[t]['ok']}/{r[t]['sent']}/{r[t]['429']}")
        line(f"  {team} uncached p95 s", lambda r, t=team: fmt(r[t]["p95"]))
    line("  intern-sandbox ok/429/422", lambda r: f"{r['intern-sandbox']['ok']}/{r['intern-sandbox']['429']}/{r['intern-sandbox']['422']}")
    print("Whole run")
    line("  cache hit rate (of ok)", lambda r: f"{r['hit_rate']:.0%}")
    line("  cache flushed before run", lambda r: "n/a (old run)" if r["flushed"] == "n/a" else ("no" if r["flushed"] is None else f"yes ({r['flushed']})"))
    line("  requests", lambda r: r["total"])
    line("  server errors / timeouts", lambda r: sum(r[t]["bad"] for t in ("search", "support", "analytics", "research", "intern-sandbox")))
    print("Phase C (all primaries down), all teams")
    line("  requests sent", lambda r: r["C"]["sent"])
    line("  ok (of which cache hits)", lambda r: f"{r['C']['ok']} ({r['C']['hits']})")
    line("  uncached answered by fallback", lambda r: r["C"]["fallback"])
    line("  rejected 429", lambda r: r["C"]["429"])
    line("  server errors (5xx)", lambda r: r["C"]["5xx"])
    line("  client timeouts", lambda r: r["C"]["timeout"])
    line("  uncached latency p50 s", lambda r: fmt(r["C"]["p50"]))
    line("  uncached latency p95 s", lambda r: fmt(r["C"]["p95"]))
    print("\nuncached 200s by node:")
    for r in runs:
        print(f"  {r['label']:<14}", dict(sorted(r["nodes"].items(), key=lambda kv: str(kv[0]))))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
