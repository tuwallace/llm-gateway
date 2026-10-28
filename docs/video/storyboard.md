# Video storyboard: "Running one LLM gateway for five teams"

A walkthrough of the key points of this project, about 8 minutes, laid out like the helpdesk-rag recording guide:
a segment table, then per-segment cues (time, narration, what is on screen) and the **citations** that support each claim.
Every number below comes from a saved document or run in this repo; if a number on screen differs, the document wins.

Citation format: `path:line` for code, `path` plus a section name for documents. Show the citation as a lower-third
on screen for about 4 seconds when the claim is spoken.

## 1. Segment overview

| # | Segment | Type | Length | Main source |
|---|---|---|---|---|
| 1 | Hook: five teams, one box | ANIM | 0:30 | ROADMAP.md (Teams) |
| 2 | What I built | ANIM | 0:50 | README.md (stack table), litellm_config.yaml |
| 3 | Keys, limits and token quotas | LIVE | 0:50 | seed_teams.py, test_teams.py |
| 4 | The cache, and why 0.9 | LIVE | 0:45 | litellm_config.yaml:70-82, ROADMAP.md (Known limits) |
| 5 | The simulation: limits hold, latency doesn't | LIVE + ANIM | 1:00 | docs/simulation-report.md |
| 6 | Fix 1: concurrency caps | ANIM | 0:50 | docs/concurrency-experiment.md |
| 7 | Fix 2: a dedicated pool | ANIM | 0:45 | docs/dedicated-pool-experiment.md |
| 8 | When every primary dies | ANIM | 0:55 | docs/fallback-experiment.md |
| 9 | Run it again: what survived | ANIM | 0:60 | docs/variance-experiment.md |
| 10 | Measuring honestly | ANIM | 0:45 | docs/variance-experiment.md, simulation-report.md (Correction) |
| 11 | Takeaways | ANIM | 0:35 | README.md (Key findings) |

Total about 8 minutes. LIVE segments are screen recordings of the commands shown; ANIM segments are graphics drawn from the tables cited.

## 2. One-time setup before recording

```bash
cd path/to/llm-gateway
docker compose ps                         # postgres, redis, prometheus, grafana: Up
sh cluster/start_nodes.sh                 # nodes 11435-11441
./restart_gateway.sh --reset              # fresh gateway, spend zeroed
curl -s localhost:4000/health/readiness   # db: connected
```

Notifications off, terminal font 20 pt, short prompt, and **hide `.env`, `teams_keys.json` and any key** (never `cat` them
on camera; show `.env.example` instead). Do not record the Grafana admin login.

## 3. Segment 1: hook (ANIM, 0:30)

| Narration | On screen | Citation |
|---|---|---|
| Five teams share one LLM gateway. One of them sends a burst. | Five team tiles; one fires a burst of 25 | ROADMAP.md, Teams table |
| Every limit holds, and the quiet team still waits half a minute. | Support latency bar jumps from 1.1 s to 38 s | docs/simulation-report.md, Findings 1 |
| This is what I measured, and what I got wrong. | Title card | |

## 4. Segment 2: what I built (ANIM, 0:50)

| Narration | On screen | Citation |
|---|---|---|
| LiteLLM in front of seven local Ollama nodes: three phi3 primaries, a llama3 fallback, three standbys. | Architecture diagram from the README stack table | README.md stack table; cluster/start_nodes.sh |
| Postgres tracks spend, Redis caches semantically, Prometheus and Grafana watch it. | Same diagram, lights up each box | docker-compose.yml; litellm_config.yaml |
| It runs natively on a Mac: Docker has no GPU, and a context cap of 4,096 cuts each node from fifteen gigabytes to under four. | Memory bars 15.5 GB to 3.84 GB | ROADMAP.md, Ollama cluster: feasibility |

## 5. Segment 3: keys, limits and token quotas (LIVE, 0:50)

Commands (type before recording, press Enter on cue):

```bash
python docs/video/demo/seg3_teams.py        # team limits and quotas table (no keys printed)
sed -n 20,40p seed_teams.py                 # PRICE_PER_TOKEN and the TEAMS source
gateway-env/bin/python -m pytest -q test_teams.py
```

| Time | Narration | On screen | Citation |
|---|---|---|---|
| 0:00 | Each team gets its own key, rate limits and a budget. | The TEAMS table in seed_teams.py | seed_teams.py:30 |
| 0:12 | Local models are free, so I priced every token at a hundred-thousandth of a dollar. Now a budget is a token quota. | Highlight `PRICE_PER_TOKEN = 0.00001` | seed_teams.py:20; ROADMAP.md, Known limits |
| 0:25 | The intern team gets fifty tokens and three requests a minute, and it really is denied. | test_teams output passing | test_teams.py; docs/simulation-report.md (intern-sandbox) |
| 0:38 | A quota is enforced per response, so a team can overshoot by a request or two. | Text callout: up to 58 tokens on a 200-token quota | ROADMAP.md, Known limits |

## 6. Segment 4: the cache, and why 0.9 (LIVE, 0:45)

```bash
sed -n 68,84p litellm_config.yaml
python docs/video/demo/seg4_cache.py        # needs the gateway; flushes the cache, then miss / HIT / miss / HIT
gateway-env/bin/python -m pytest -q test_cache.py
```

| Time | Narration | On screen | Citation |
|---|---|---|---|
| 0:00 | A semantic cache answers a paraphrase without touching a model. | cache_params block | litellm_config.yaml:70-82 |
| 0:15 | I set the similarity threshold at 0.9. At 0.8, the capital of Germany was only 0.03 below a false hit for the capital of France. | Two prompts with their scores | ROADMAP.md, Known limits |
| 0:30 | Cache hits spend nothing and skip the nodes, so the hit rate also hides outages. | 73-76% normal, 92% in the outage phase | docs/simulation-report.md, Findings 2; docs/variance-experiment.md (cache hit rate row) |

## 7. Segment 5: the simulation (LIVE + ANIM, 1:00)

Show the phase plan, then the result table. Do not run the full 4-minute simulation on camera; show the saved run. Its cache was partly warm (81% hits against 73-76% cold), noted in simulation-report.md.

```bash
sed -n 43,46p simulate.py                                   # PHASES
python docs/video/demo/seg5_simulation.py  # summary of data/baseline-run.json (the run in simulation-report.md)
gateway-env/bin/python simulate.py --analyze docs/video/demo/data/baseline-run.json | head -40
```

| Time | Narration | On screen | Citation |
|---|---|---|---|
| 0:00 | Open-loop traffic, four phases: healthy, one node down, all primaries down, recovery. | PHASES list, then a timeline graphic | simulate.py:43; docs/simulation-report.md, Setup |
| 0:15 | The checks pass: every 429 was justified, and Postgres matches the client exactly. | Checks list; DB cross-check table | docs/simulation-report.md, Cross-checks |
| 0:30 | But support waited a median of thirty-eight seconds after a research burst, against one second otherwise. | Latency chart | docs/simulation-report.md, Findings 1 |
| 0:45 | Limits cap how much a team sends, not how long others wait. | Callout | same |

## 8. Segment 6: fix 1, concurrency caps (ANIM, 0:50)

| Narration | On screen | Citation |
|---|---|---|
| A cap on parallel requests brought the quiet team from thirty seconds to one or two. | Before/after bars | docs/concurrency-experiment.md, Findings 1 |
| But every rejection costs two units of the team's request budget, so the noisy team was starved. | Chart: 19, 17, 15, 13, 11, 7 accepted after 0, 1, 2, 3, 4, 6 rejections | docs/concurrency-experiment.md, Findings 2; experiments/concurrency_probes.py |
| And during failover, the cap was bypassed: eighteen requests in flight on a cap of one. | Counter climbing to 18 | docs/concurrency-experiment.md, Findings 3 |
| Caveat, stated on screen: the first caps runs started with a warm cache; the cold re-run is the one to trust. | Correction banner | docs/concurrency-experiment.md (Correction), docs/dedicated-pool-experiment.md (Correction) |

## 9. Segment 7: fix 2, a dedicated pool (ANIM, 0:45)

| Narration | On screen | Citation |
|---|---|---|
| Reserve one node for the heavy team, under its own model alias. | Pool diagram: research-node apart | docs/dedicated-pool-experiment.md, Setup; experiments/make_pool_config.py |
| Support dropped to about a second, and research kept its full throughput. | Table row: 1.3 / 2.4 s, 9,773 tokens | docs/dedicated-pool-experiment.md, Results |
| The price: the heavy team now queues behind itself, and the shared fallback is unchanged. | Callout | docs/dedicated-pool-experiment.md, Findings 2-3 |
| Verified with probes before the run: 403 on the wrong alias, shared traffic never touched the reserved node. | Probe output | experiments/pool_probes.py; docs/dedicated-pool-experiment.md, Verification |

## 10. Segment 8: when every primary dies (ANIM, 0:55)

| Narration | On screen | Citation |
|---|---|---|
| With all three primaries down, one llama3 node serves everyone, and requests time out. | Phase C timeouts: 13 and 11 | docs/fallback-experiment.md, Results |
| A concurrency limit on the fallback turns timeouts into fast errors, and trips a thirty-second blackout. | Cooldown timeline | docs/fallback-experiment.md, What the limit does |
| A second fallback node alone changed nothing. | Row: 12 failures | docs/fallback-experiment.md, Results (node2) |
| A standby pool the size of the primaries, with a five-second cooldown, was the only thing that helped. | Config flags `--standby 3 --cooldown 5` | experiments/make_fallback_config.py; docs/fallback-experiment.md, Follow-up |
| It runs phi3, not llama3: matching the primaries with llama3 needs about thirty gigabytes. | Callout | docs/fallback-experiment.md, Follow-up caveats |

## 11. Segment 9: run it again (ANIM, 1:00)

This is the strongest segment. Show the numbers as run 1 / run 2 / run 3.

| Narration | On screen | Citation |
|---|---|---|
| I repeated the baseline, the big fallback and the pool three times each, cold cache. | Nine run tiles | docs/variance-experiment.md, Setup |
| The pool result held: support's median during bursts was 1.4 to 1.5 seconds every time, against 15 to 27 for the baseline. | Bars, no overlap | docs/variance-experiment.md, Results |
| The big fallback shortened outage latency: median 6 to 16 seconds against 31 to 39. | Bars | same |
| But "it removes failures" did not hold. Three new baselines had zero failures. | Strike through the earlier claim | docs/variance-experiment.md, Which differences are real; docs/fallback-experiment.md (Correction) |
| One run per configuration could not have told me that. | Title card | |

## 12. Segment 10: measuring honestly (ANIM, 0:45)

Show the table from README.md ("Measurement lessons") one row at a time.

| Narration | On screen | Citation |
|---|---|---|
| A warm cache between runs made the second run look faster. I now flush it before every run. | Hit rate 83-90% vs 75-78% | simulate.py:156; docs/concurrency-experiment.md (Correction) |
| I labelled requests by when they finished, not started. Fixed, and the old report corrected. | Label diff | docs/simulation-report.md (Correction) |
| The embedding runner crashed on GPU memory and silently turned the cache off. Now a preflight aborts the run. | Hit rate dropping to 0%; preflight message | docs/variance-experiment.md, What went wrong first; simulate.py:172 |
| And my own preflight requests tripped my own rate-limit check. Fixed by recording them. | Unjustified 429s 18-30 to 0 | docs/variance-experiment.md, search-429 section |

## 13. Segment 11: takeaways (ANIM, 0:35)

1. Limits control volume. Isolation needs separate capacity. (README Key findings 1, 3)
2. Capacity, not clever limits, protects you in an outage. (README Key findings 4)
3. Repeat the run before you believe it. (README Key findings 5)
4. Check that your test rig is working before you trust its numbers. (README Key findings 6)

End card: repo name and the README link.

## 14. Honesty checks before publishing

- Say once, on screen, that this is one machine with a shared GPU; latencies are indicative (README, Limits).
- The big-fallback run 3 is only partly valid (hit rate 52%); it is shown in brackets in the source table. Keep the brackets.
- The standby pool is phi3, not llama3.
- Open questions remain: the one-off RPM enforcement failure, fallback use while primaries are healthy, the cap-bypass
  mechanism (ROADMAP.md, Open issues). Do not present these as solved.
- Never show `.env`, `teams_keys.json`, `observability/scraper.key`, or a Bearer token in a terminal.
- If narration is synthetic, YouTube may require its altered or synthetic content label.
