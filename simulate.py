"""Traffic simulation: 5 teams, four phases, failure injection, then cross-checks.

    gateway-env/bin/python simulate.py            # ~3.5 minutes
    gateway-env/bin/python simulate.py --scale 0.5

Open-loop load: each team sends requests at its own rate whether or not earlier
ones have finished, like real clients. Phases (default length):

    A baseline        60 s  all nodes up
    B node down       60 s  node-3 stopped
    C primaries down  30 s  every phi3 node stopped, llama3 fallback only
    D recovery        60 s  nodes restarted

Results go to sim_results/run-<time>.json. Nodes are always restarted afterwards.
"""
import argparse
import asyncio
import json
import math
import os
import random
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg

from seed_teams import BASE_URL, MODELS, TEAMS, master_key
from usage_report import database_url

ROOT = Path(__file__).parent
KEYS = json.loads((ROOT / "teams_keys.json").read_text())
MODEL = MODELS[0]  # default; each team actually uses the first model its key allows (TEAM_MODEL)
TEAM_MODEL = {}
CACHE_FLUSHED = [None]
PRE_RUN = []  # (team, absolute time) of requests sent before t0 (preflight, warm-up): they still use up RPM
CLIENT_TIMEOUT = 60

PHASES = [("A baseline", 60, []), ("B node down", 60, [11437]),
          ("C primaries down", 30, [11435, 11436]), ("D recovery", 60, None)]
PRIMARY_PORTS = [11435, 11436, 11437]
# Node ids as configured: shared pool node-1/2/3, or in the dedicated-pool config node-1/2 + research-node.
B_NODE_ID, EXPECTED_NODES = "node-3", {"node-1", "node-2", "node-3"}


def use_pool_layout():
    """Dedicated-pool config: node-3 is research-node. Phase B stops shared node-2 (11436) so it
    stays a 'one shared node down' test; phase C stops the other two primaries."""
    global B_NODE_ID, EXPECTED_NODES
    PHASES[1] = ("B node down", 60, [11436])
    PHASES[2] = ("C primaries down", 30, [11435, 11437])
    B_NODE_ID, EXPECTED_NODES = "node-2", {"node-1", "node-2", "research-node"}

TOPICS = ["tides", "volcanoes", "the printing press", "photosynthesis", "inflation", "jazz", "glaciers", "the Roman roads",
          "vaccines", "semiconductors", "coral reefs", "the telegraph", "monsoons", "bridges", "bread fermentation",
          "plate tectonics", "the Silk Road", "antibiotics", "lighthouses", "satellites", "honeybees", "the abacus",
          "tornadoes", "canals", "clock escapements", "wind turbines", "the water cycle", "origami", "sonar", "tea ceremonies",
          "deserts", "the compass", "mangroves", "typography", "rainbows", "railways", "fossils", "aqueducts", "cartography",
          "pottery", "magnetism", "migration of birds", "lenses", "salt mines", "the metric system", "eclipses"]
FILLER = ("The quarterly report covers shipping volumes, regional demand, supplier lead times and inventory turnover "
          "across twelve warehouses, with notes on seasonal variance and exceptions requiring review. ")


def prompt_for(team: str, n: int, rng: random.Random):
    """Returns (prompt, max_tokens). Shapes mirror what each team would send."""
    topic = rng.choice(TOPICS)
    if team == "search":     # short, many repeats -> cache hits
        return rng.choice(["What is " + t + "?" for t in TOPICS[:10]] + [f"Define {topic}."]), 24
    if team == "support":    # medium, mostly distinct
        return f"A customer asks how {topic} relates to their order status. Reply politely in two sentences.", 48
    if team == "analytics":  # long prompts, small answers
        return f"Summarise in one line, topic {topic}: " + FILLER * 40, 40
    if team == "research":   # large outputs
        return f"Write a detailed paragraph about {topic} and its history.", 200
    return f"hello {n}", 8   # intern


class Recorder:
    def __init__(self):
        self.rows = []

    def add(self, **row):
        self.rows.append(row)


async def send(client, rec, team, n, phase, t0, rng, sem):
    prompt, max_tokens = prompt_for(team, n, rng)
    started_in = phase()  # a slow request belongs to the phase it was sent in, not the one it finishes in
    body = {"model": TEAM_MODEL.get(team, MODEL), "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    start = time.time()
    status, node, hit, tokens, error = None, None, False, 0, None
    async with sem:
        try:
            r = await client.post("/v1/chat/completions", json=body,
                                  headers={"Authorization": f"Bearer {KEYS[team]['key']}"})
            status = r.status_code
            node = r.headers.get("x-litellm-model-id")
            hit = "x-litellm-cache-key" in r.headers
            if status == 200:
                tokens = r.json()["usage"]["total_tokens"]
        except httpx.HTTPError as e:
            status, error = "timeout" if isinstance(e, httpx.TimeoutException) else "error", type(e).__name__
    rec.add(team=team, phase=started_in, t=round(start - t0, 2), latency=round(time.time() - start, 3),
            status=status, node=node, hit=hit, tokens=tokens, error=error)


async def team_load(client, rec, team, rate_per_min, t0, phase, stop, rng, sem, burst=None):
    """Open-loop arrivals. `burst=(every_s, size, over_s)` adds periodic bursts on top of the base rate."""
    pending, n = set(), 0
    next_burst = time.time() + (burst[0] if burst else math.inf)
    next_send = time.time() + rng.random() * 60 / max(rate_per_min, 1)
    while not stop.is_set():
        now = time.time()
        due = []
        if rate_per_min and now >= next_send:
            due.append(0.0)
            next_send += rng.expovariate(rate_per_min / 60)
        if burst and now >= next_burst:
            due += [i * burst[2] / burst[1] for i in range(burst[1])]
            next_burst += burst[0]
        for delay in due:
            n += 1
            async def one(d=delay, k=n):
                await asyncio.sleep(d)
                await send(client, rec, team, k, phase, t0, rng, sem)
            task = asyncio.create_task(one())
            pending.add(task)
            task.add_done_callback(pending.discard)
        await asyncio.sleep(0.05)
    await asyncio.gather(*pending, return_exceptions=True)


def nodes(script, ports):
    subprocess.run([str(ROOT / "cluster" / script)], env={**os.environ, "NODE_PORTS": " ".join(map(str, ports))},
                   check=True, capture_output=True, timeout=90)


async def controller(scale, current_phase, t0, events, stop):
    for name, seconds, kill in PHASES:
        current_phase[0] = name
        events.append((round(time.time() - t0, 1), f"phase {name} begins"))
        if kill is None:
            await asyncio.to_thread(nodes, "start_nodes.sh", PRIMARY_PORTS)
            events.append((round(time.time() - t0, 1), "primary nodes restarted"))
        elif kill:
            await asyncio.to_thread(nodes, "stop_nodes.sh", kill)
            events.append((round(time.time() - t0, 1), f"stopped nodes {kill}"))
        await asyncio.sleep(seconds * scale)
    stop.set()


def flush_semantic_cache():
    """Delete cached answers so a run never inherits a warm cache from the previous one.

    Cached answers live in Redis for 10 minutes and the prompt pool is small, so back-to-back
    runs otherwise see far more cache hits (83-90% against 77-81% when cold) and look faster.
    Only the entries are deleted; the search index stays, so the gateway needs no restart.
    """
    import redis
    password = next(l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines() if l.startswith("REDIS_PASSWORD="))
    r = redis.Redis(host="localhost", port=6380, password=password)
    keys = list(r.scan_iter(match="litellm_semantic_cache_index:*", count=500))
    if keys:
        r.delete(*keys)
    return len(keys)


def preflight_cache():
    """Fail fast if the semantic cache cannot work (e.g. the embedding node is broken).

    Without it every request goes to the model nodes and the run silently measures an overloaded
    system: seen once, when the embedding runner returned "Compute error" and the hit rate fell to 0%.
    """
    prompt = f"preflight {time.time()}: name one primary colour"
    body = {"model": TEAM_MODEL["search"], "messages": [{"role": "user", "content": prompt}], "max_tokens": 5}
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {KEYS['search']['key']}"}, timeout=120) as c:
        PRE_RUN.append(("search", time.time()))
        first = c.post("/v1/chat/completions", json=body)
        time.sleep(1.5)
        PRE_RUN.append(("search", time.time()))
        second = c.post("/v1/chat/completions", json=body)
    if first.status_code != 200 or "x-litellm-cache-key" not in second.headers:
        raise SystemExit(f"preflight failed: semantic cache is not serving hits (first={first.status_code}, "
                         f"second={second.status_code}); check the embedding node on port 11438")


def discover_models():
    """The model each team's key is allowed to call (first entry)."""
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=30) as c:
        for team, entry in KEYS.items():
            models = c.get("/key/info", params={"key": entry["key"]}).json()["info"].get("models") or [MODEL]
            TEAM_MODEL[team] = models[0]


async def run(scale, keep_cache=False):
    discover_models()
    if not keep_cache:
        preflight_cache()
    CACHE_FLUSHED[0] = None if keep_cache else flush_semantic_cache()
    print("semantic cache:", "kept (warm)" if keep_cache else f"flushed ({CACHE_FLUSHED[0]} entries removed)")
    print("models in use:", TEAM_MODEL)
    rec, events = Recorder(), []
    rng = random.Random(7)
    current_phase = [PHASES[0][0]]
    stop = asyncio.Event()
    sem = asyncio.Semaphore(80)
    limits = httpx.Limits(max_connections=120, max_keepalive_connections=40)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=CLIENT_TIMEOUT, limits=limits) as client:
        # One warm-up request per team: Prometheus shows no rate for a series' first burst.
        for team in KEYS:
            if team == "intern-sandbox":  # its 50-token quota would be burned by a warm-up
                continue
            PRE_RUN.append((team, time.time()))
            await send(client, Recorder(), team, 0, lambda: "warmup", time.time(), rng, sem)
        t0 = time.time()
        PRE_RUN[:] = [(tm, round(ts - t0, 2)) for tm, ts in PRE_RUN]
        started = datetime.now(timezone.utc)
        phase = lambda: current_phase[0]
        loads = [
            team_load(client, rec, "search", 90, t0, phase, stop, rng, sem),
            team_load(client, rec, "support", 20, t0, phase, stop, rng, sem),
            team_load(client, rec, "analytics", 8, t0, phase, stop, rng, sem),
            team_load(client, rec, "research", 4, t0, phase, stop, rng, sem, burst=(30, 25, 8)),
            team_load(client, rec, "intern-sandbox", 10, t0, phase, stop, rng, sem),
        ]
        try:
            await asyncio.gather(controller(scale, current_phase, t0, events, stop), *loads)
        finally:
            await asyncio.to_thread(nodes, "start_nodes.sh", PRIMARY_PORTS + [11438, 11439])
    return rec.rows, events, started


def relabel_phases(rows, scale):
    """Phase from request start time (older saved runs labelled by finish time)."""
    bounds, t = [], 0.0
    for name, seconds, _ in PHASES:
        bounds.append((t, name))
        t += seconds * scale
    for r in rows:
        if r["phase"] != "warmup":
            r["phase"] = [name for start, name in bounds if r["t"] >= start - 0.5][-1]
    return rows


def pct(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(q * len(values)) - 1)]


def summarise(rows):
    by = defaultdict(list)
    for r in rows:
        by[(r["phase"], r["team"])].append(r)
    out = {}
    for key, rs in by.items():
        ok = [r for r in rs if r["status"] == 200]
        out[key] = {
            "sent": len(rs), "ok": len(ok), "cache_hits": sum(r["hit"] for r in ok),
            "429": sum(r["status"] == 429 for r in rs), "422": sum(r["status"] == 422 for r in rs),
            "5xx": sum(isinstance(r["status"], int) and r["status"] >= 500 for r in rs),
            "timeout/error": sum(r["status"] in ("timeout", "error") for r in rs),
            "p50": pct([r["latency"] for r in ok], 0.5), "p95": pct([r["latency"] for r in ok], 0.95),
            "tokens_billed": sum(r["tokens"] for r in ok if not r["hit"]),
        }
    return out


def print_tables(rows, summary):
    teams = list(KEYS)
    for phase, _, _ in PHASES:
        print(f"\n=== {phase} ===")
        print(f"{'team':<16}{'sent':>6}{'ok':>5}{'hits':>6}{'429':>5}{'422':>5}{'5xx':>5}{'t/o':>5}{'p50':>7}{'p95':>7}{'tokens':>8}")
        for team in teams:
            s = summary.get((phase, team))
            if not s:
                continue
            f = lambda v: "-" if v is None else f"{v:.2f}"
            print(f"{team:<16}{s['sent']:>6}{s['ok']:>5}{s['cache_hits']:>6}{s['429']:>5}{s['422']:>5}{s['5xx']:>5}"
                  f"{s['timeout/error']:>5}{f(s['p50']):>7}{f(s['p95']):>7}{s['tokens_billed']:>8}")
    print("\n=== Which node served uncached 200s, per phase ===")
    for phase, _, _ in PHASES:
        c = Counter(r["node"] for r in rows if r["phase"] == phase and r["status"] == 200 and not r["hit"])
        print(f"{phase:<18}", dict(sorted(c.items(), key=lambda kv: str(kv[0]))))


def checks(rows, summary, duration_s, caps=None, pre_run=None):
    """(description, passed, detail) tuples comparing behaviour with the configured limits."""
    out, caps = [], caps or {}
    tot = lambda team, k: sum(v[k] for (p, t), v in summary.items() if t == team)
    minutes_windows = math.ceil(duration_s / 60) + 1  # fixed windows can straddle a boundary

    out.append(("support stays under its limits: no 429/422",
                tot("support", "429") + tot("support", "422") == 0, f"429={tot('support','429')} 422={tot('support','422')}"))
    out.append(("analytics (long prompts, 8/min on average vs limit 10): no 422 (quota is never reached)",
                tot("analytics", "422") == 0, f"422={tot('analytics','422')}"))
    out.append(("search offers ~90/min vs RPM 60: gets 429s",
                tot("search", "429") > 0, f"429={tot('search','429')} of {tot('search','sent')}"))
    out.append(("research bursts of 25 vs RPM 20: gets 429s", tot("research", "429") > 0, f"429={tot('research','429')}"))
    for team in ("search", "support", "analytics", "research", "intern-sandbox"):
        limit = TEAMS[team]["rpm_limit"]
        ok = tot(team, "ok")
        out.append((f"{team}: successes within RPM {limit} x {minutes_windows} windows", ok <= limit * minutes_windows,
                    f"ok={ok} bound={limit * minutes_windows}"))
    # A 429 is justified by either rule: (a) RPM: the team had already been admitted `limit`
    # requests inside the 60 s before it (a window open at time t started no earlier than t-60);
    # (b) concurrency: the team already had `cap` requests in flight (max_parallel_requests).
    for team in ("search", "support", "analytics", "research"):
        limit, cap = TEAMS[team]["rpm_limit"], caps.get(team)
        mine = [r for r in rows if r["team"] == team and r["phase"] != "warmup"]
        # requests sent before t0 (preflight, warm-up) are in the gateway's RPM window too
        pre = [t for tm, t in (pre_run or []) if tm == team]
        premature = []
        for r in mine:
            if r["status"] == 429:
                admitted = sum(1 for o in mine if o["status"] != 429 and r["t"] - 60 <= o["t"] <= r["t"]) \
                    + sum(1 for t in pre if r["t"] - 60 <= t)
                inflight = sum(1 for o in mine if o["status"] != 429 and o["t"] <= r["t"] < o["t"] + o["latency"])
                if admitted < limit - 1 and not (cap is not None and inflight >= cap):
                    premature.append((r["t"], admitted, inflight))
        rule = f"RPM {limit}" + (f" or {cap} in flight" if cap else "")
        out.append((f"{team}: every 429 is justified ({rule})", not premature,
                    f"{sum(r['status'] == 429 for r in mine)} 429s, {len(premature)} unjustified"))
    denied = tot("intern-sandbox", "429") + tot("intern-sandbox", "422")
    billed = sum(1 for r in rows if r["team"] == "intern-sandbox" and r["status"] == 200 and not r["hit"])
    out.append(("intern-sandbox is denied (429 or 422) after a tiny allowance (<= 3 billed successes)",
                denied > 0 and billed <= 3,
                f"billed ok={billed} ok={tot('intern-sandbox','ok')} 429={tot('intern-sandbox','429')} 422={tot('intern-sandbox','422')}"))

    def served(phase, after=0.0):
        return Counter(r["node"] for r in rows if r["phase"] == phase and r["status"] == 200 and not r["hit"] and r["t"] >= after)

    b_start = min((r["t"] for r in rows if r["phase"] == "B node down"), default=0)
    late_b = served("B node down", b_start + 15)  # after one health-probe interval plus margin
    out.append((f"B: {B_NODE_ID} receives no traffic once health checks notice (+15 s)",
                None if sum(late_b.values()) < 5 else late_b.get(B_NODE_ID, 0) == 0, f"{dict(late_b)}"))
    out.append(("B: no client-visible failures while one node is down",
                all(v["5xx"] + v["timeout/error"] == 0 for (p, _), v in summary.items() if p == "B node down"),
                str({t: summary[("B node down", t)]["5xx"] for t in KEYS if ("B node down", t) in summary})))
    c = served("C primaries down")
    out.append(("C: fallback node serves the uncached traffic",
                None if not c and not any(r["phase"] == "C primaries down" for r in rows) else sum(v for k, v in c.items() if str(k).startswith("fallback-node")) > 0, str(dict(c))))
    c_bad = sum(v["5xx"] + v["timeout/error"] for (p, _), v in summary.items() if p == "C primaries down")
    c_sent = sum(v["sent"] for (p, _), v in summary.items() if p == "C primaries down")
    out.append(("C: failures stay below 10% of requests", c_bad <= 0.1 * max(c_sent, 1), f"{c_bad} of {c_sent}"))
    d_start = min((r["t"] for r in rows if r["phase"] == "D recovery"), default=0)
    d_late = served("D recovery", d_start + 20)
    out.append(("D: all three phi3 nodes serve again (+20 s after restart)",
                None if sum(d_late.values()) < 5 else EXPECTED_NODES <= set(d_late), str(dict(d_late))))
    a_bad = sum(v["5xx"] + v["timeout/error"] for (p, _), v in summary.items() if p == "A baseline")
    out.append(("A: no failures or timeouts in the healthy baseline", a_bad == 0, f"{a_bad} failures"))
    d_rows = [r for r in rows if r["phase"] == "D recovery" and r["t"] >= d_start + 20]
    d_bad = sum(r["status"] in ("timeout", "error") or (isinstance(r["status"], int) and r["status"] >= 500) for r in d_rows)
    out.append(("D: no failures or timeouts once recovered (+20 s)", None if len(d_rows) < 5 else d_bad == 0,
                f"{d_bad} of {len(d_rows)}"))
    return out


def cross_check_database(rows, started):
    """Client vs spend logs per team: (client_rows, db_rows, client_tokens, db_tokens, client_timeouts).

    Spend logs are written in batches, so poll until they settle. Requests the client gave up on
    (timeouts) are still completed and billed by the gateway, so db may exceed client by those.
    """
    client = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r["status"] == 200 and not r["hit"]:
            client[r["team"]][0] += 1
            client[r["team"]][1] += r["tokens"]
        elif r["status"] == "timeout":
            client[r["team"]][2] += 1
    result = {}
    with psycopg.connect(database_url(), autocommit=True) as conn:
        deadline = time.time() + 120
        while True:
            db = {t: (n, int(tok)) for t, n, tok in conn.execute(
                'SELECT t.team_alias, count(*), coalesce(sum(s.total_tokens), 0) FROM "LiteLLM_SpendLogs" s '
                'JOIN "LiteLLM_TeamTable" t ON t.team_id = s.team_id '
                "WHERE s.\"startTime\" >= %s AND s.call_type = 'acompletion' AND s.status = 'success' "
                "AND s.cache_hit IS DISTINCT FROM 'True' AND t.team_alias = ANY(%s) GROUP BY 1",
                (started, list(KEYS))).fetchall()}
            settled = all(db.get(t, (0, 0))[0] - client[t][0] == client[t][2] for t in KEYS)
            if settled or time.time() > deadline:
                break
            time.sleep(5)
    for t in KEYS:
        n, tok = db.get(t, (0, 0))
        result[t] = (client[t][0], n, client[t][1], tok, client[t][2])
    return result


def current_caps():
    """max_parallel_requests per team (set on each team's key), as the gateway reports it."""
    with httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {master_key()}"}, timeout=30) as c:
        return {t: c.get("/key/info", params={"key": e["key"]}).json()["info"].get("max_parallel_requests")
                for t, e in KEYS.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scale", type=float, default=1.0, help="multiply phase lengths")
    ap.add_argument("--keep-cache", action="store_true", help="do not flush the semantic cache first (warm-cache run)")
    ap.add_argument("--pool", action="store_true", help="dedicated-pool layout (see pool_profile.py)")
    ap.add_argument("--label", default="", help="name of the configuration under test, saved with the run")
    ap.add_argument("--analyze", metavar="FILE", help="re-check a saved run instead of sending traffic")
    args = ap.parse_args()
    if args.pool:
        use_pool_layout()
    if args.analyze:
        saved = json.loads(Path(args.analyze).read_text())
        if saved.get("pool"):
            use_pool_layout()
        rows, total = saved["requests"], sum(s for _, s, _ in PHASES) * saved["scale"]
        rows = relabel_phases(rows, saved["scale"])
        summary = summarise(rows)
        print_tables(rows, summary)
        print("\n=== Checks against configured limits ===")
        results = checks(rows, summary, total, saved.get("caps"), saved.get("pre_run"))
        for desc, ok, detail in results:
            print(f"  [{'INCONCLUSIVE' if ok is None else 'PASS' if ok else 'FAIL'}] {desc}  ({detail})")
        raise SystemExit(1 if any(ok is False for _, ok, _ in results) else 0)
    total = sum(s for _, s, _ in PHASES) * args.scale
    print(f"Simulating {total:.0f}s of traffic (scale {args.scale}) against {BASE_URL}")

    rows, events, started = asyncio.run(run(args.scale, args.keep_cache))
    summary = summarise(rows)
    print_tables(rows, summary)

    print("\n=== Events ===")
    for t, e in events:
        print(f"  t={t:>6}s  {e}")

    print("\n=== Checks against configured limits ===")
    caps = current_caps()
    results = checks(rows, summary, total, caps, PRE_RUN)
    for desc, ok, detail in results:
        print(f"  [{'INCONCLUSIVE' if ok is None else 'PASS' if ok else 'FAIL'}] {desc}  ({detail})")

    print("\n=== Uncached completions: client vs Postgres spend logs ===")
    print(f"  {'team':<16}{'client rows':>12}{'db rows':>9}{'timeouts':>10}{'client tok':>12}{'db tok':>9}")
    tokens = cross_check_database(rows, started)
    for team, (crow, drow, ctok, dtok, tmo) in tokens.items():
        # db may only exceed client by the requests the client abandoned (gateway still completed them)
        verdict = "ok" if drow - crow == tmo else ("ok (some abandoned requests never finished)" if 0 <= drow - crow < tmo else "MISMATCH")
        print(f"  {team:<16}{crow:>12}{drow:>9}{tmo:>10}{ctok:>12}{dtok:>9}   {verdict}")

    out_dir = ROOT / "sim_results"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"run-{started.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"label": args.label, "caps": caps, "pool": args.pool, "models": dict(TEAM_MODEL), "cache_flushed": CACHE_FLUSHED[0], "scale": args.scale, "started": started.isoformat(), "events": events, "pre_run": PRE_RUN,
                                "checks": [{"check": d, "passed": p, "detail": x} for d, p, x in results],
                                "tokens": tokens, "requests": rows}))
    print(f"\nraw results: {path.relative_to(ROOT)}  ({len(rows)} requests)")
    raise SystemExit(1 if any(ok is False for _, ok, _ in results) else 0)


if __name__ == "__main__":
    main()
