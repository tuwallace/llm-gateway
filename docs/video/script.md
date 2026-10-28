# Video script: "One LLM gateway, five teams: what I measured, and what I got wrong"

Narration blocks below are read by `narration/build_narration.py` (one audio file per segment, sentence-level timings that
the animations in `anim/` are synced to). The storyboard (`storyboard.md`) holds the on-screen citations for each claim.
Numbers come from `README.md` and `docs/*.md`; if a number here and a document differ, the document wins.

## 1. Hook

**Narration:**
> Five teams share one L L M gateway. One of them sends a burst of requests. Every limit holds, every rate limit is respected, and the quiet team still waits half a minute. I built this gateway on one Mac, tried to break it, and measured what happened. This video is what I measured, and what I got wrong.

## 2. What I built

**Narration:**
> The gateway is LiteLLM, sitting in front of seven local Ollama nodes. Three phi three nodes are the primaries, one llama three node is the fallback, and three more are standbys. Postgres records every request and its spend. Redis caches answers semantically. Prometheus and Grafana watch the whole thing. It all runs natively on one Mac, because Docker on macOS has no G P U access. And I capped the context window at four thousand tokens, which cut each phi three node from fifteen gigabytes to under four.

## 3. Keys, limits and token quotas

**Narration:**
> Each team gets its own key, its own rate limits, and a budget. Local models are free, so I priced every token at a hundred-thousandth of a dollar. Now a dollar budget is really a token quota. The intern team gets fifty tokens and three requests a minute, and it really is denied. One caveat: a quota is enforced per response, so a team can overshoot by a request or two.

## 4. The semantic cache

**Narration:**
> A semantic cache answers a paraphrase without touching a model. Ask for the capital of France once, and it's a miss. Ask it a different way, and it's a hit, in a few hundredths of a second. Ask about Germany, same shape, different fact, and it correctly misses. That works because I set the similarity threshold at zero point nine. At zero point eight, Germany was only three hundredths below a false hit. The catch is that cache hits spend nothing and skip the nodes, so a high hit rate also hides outages.

## 5. The simulation

**Narration:**
> To test it I sent open-loop traffic in four phases: healthy, one node down, all primaries down, and recovery. The checks passed. Every rate-limit rejection was justified, and the Postgres spend logs matched the client exactly. But look at support, the quiet team. After a research burst, its uncached requests waited a median of thirty-eight seconds, against about one second otherwise. Limits cap how much a team sends. They don't cap how long everyone else waits.

## 6. Fix one: concurrency caps

**Narration:**
> First fix: a cap on parallel requests per team. It worked. Support dropped from about thirty seconds to one or two. But there were three costs. Every rejected request was charged twice against the team's request budget, so the research team was starved. The cap rejects instead of queueing. And during failover, the cap was bypassed, with eighteen requests in flight on a cap of one. One correction: my first caps runs started with a warm cache, so I re-ran them cold, and trusted those.

## 7. Fix two: a dedicated pool

**Narration:**
> Second fix: reserve a node for the heavy team, under its own model alias. Support dropped to about one point three seconds during bursts, and research kept its full throughput, about nine thousand eight hundred tokens. The price is that the heavy team now queues behind itself, and the shared fallback is unchanged. I verified the wiring with probes first. The wrong alias returns a four oh three, and shared traffic never touched the reserved node.

## 8. When every primary dies

**Narration:**
> Now the worst case: all three primaries down. One llama three node serves everyone, and thirteen requests timed out in that phase. A concurrency limit on the fallback turned timeouts into fast errors, and then tripped a thirty-second blackout. A second fallback node on its own changed nothing. What helped was a standby pool the size of the primaries, with a five-second cooldown. It runs phi three, not llama three, because matching the primaries with llama three needs about thirty gigabytes.

## 9. Run it again

**Narration:**
> Then I did what I should have done first: I repeated the runs. Three times each for the baseline, the big fallback, and the dedicated pool, with a cold cache. The pool result held. Support's median during bursts was one point four to one point five seconds every time, against fifteen to twenty-seven for the baseline. The big fallback cut outage latency from thirty-one to thirty-nine seconds down to between six and sixteen. But my earlier claim, that it removed failures, did not hold. Three new baseline runs had zero failures too. One run per configuration could never have told me that.

## 10. Measuring honestly

**Narration:**
> Four measurement mistakes changed my results. A warm cache between runs made the second run look faster, so now I flush it first. I labelled requests by when they finished, not when they started. The embedding node crashed on G P U memory and silently turned the cache off, so now a preflight check aborts the run. And my own preflight requests tripped my own rate-limit check, until I started recording them.

## 11. Takeaways

**Narration:**
> Four takeaways. Limits control volume, but isolation needs separate capacity. In an outage, capacity protects you, not clever limits. Repeat the run before you believe it. And check that your test rig works before you trust its numbers. The code, the write-ups, and every number are in the repository. Thanks for watching.
