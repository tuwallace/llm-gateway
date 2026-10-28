import React from "react";
import { Slide, Appear, Footnote, Narration, beat, C, useProgress } from "./ui";
import { Big, Card, Hbar, Table } from "./kit";

const TEAMS = ["search", "support", "analytics", "research", "intern-sandbox"];

// 1. Hook
export const Hook: React.FC = () => {
  const S = "seg1", flare = beat(S, "One of them"), ok = beat(S, "Every limit holds"), wait = beat(S, "still waits half a minute");
  const p = useProgress(flare, 0.8);
  return (
    <Slide>
      <Narration seg={S} />
      <Appear at={beat(S, "Five teams")} dur={1}><div style={{ fontSize: 92, fontWeight: 800, letterSpacing: -2, marginTop: 20 }}>Five teams. One gateway.</div></Appear>
      <div style={{ display: "flex", gap: 24, marginTop: 56 }}>
        {TEAMS.map((t, i) => (
          <Appear key={t} at={beat(S, "Five teams") + 0.4 + i * 0.25} style={{ flex: 1 }}>
            <div style={{ background: C.panel, borderRadius: 20, padding: "34px 12px", textAlign: "center", fontSize: 32, fontWeight: 700,
              border: `3px solid ${t === "research" && p > 0 ? C.red : t === "support" ? C.teal : C.panelLine}`, boxShadow: t === "research" ? `0 0 ${60 * p}px rgba(255,107,107,${0.6 * p})` : "none" }}>{t}</div>
          </Appear>
        ))}
      </div>
      <Appear at={ok} style={{ marginTop: 50, fontSize: 40, color: C.teal }}>{"✓"} every rate limit respected {"·"} every quota respected</Appear>
      <div style={{ marginTop: 34, maxWidth: 1300 }}>
        <Hbar at={wait} label="support, normally" value={1.1} max={40} color={C.teal} />
        <Hbar at={wait + 0.5} label="support, after a research burst" value={37.9} max={40} color={C.red} />
      </div>
      <Appear at={beat(S, "This video is what I measured")} dur={1}><div style={{ fontSize: 50, fontWeight: 700, marginTop: 30 }}>What I measured, and what I got wrong.</div></Appear>
      <Footnote>docs/simulation-report.md {"·"} one Mac, shared GPU: latencies are indicative</Footnote>
    </Slide>
  );
};

// 2. What I built
export const Stack: React.FC = () => {
  const S = "seg2";
  const Box: React.FC<{ at: number; t: string; sub?: string; color?: string; w?: number }> = ({ at, t, sub, color = C.panelLine, w = 250 }) => (
    <Appear at={at}><div style={{ width: w, background: C.panel, border: `3px solid ${color}`, borderRadius: 18, padding: "18px 16px", textAlign: "center" }}>
      <div style={{ fontSize: 34, fontWeight: 800 }}>{t}</div>{sub && <div style={{ fontSize: 24, color: C.muted, marginTop: 6 }}>{sub}</div>}</div></Appear>
  );
  const mem = beat(S, "cut each phi three node");
  return (
    <Slide title="A shared LLM gateway on one Mac">
      <Narration seg={S} />
      <div style={{ display: "flex", alignItems: "center", gap: 40 }}>
        <Box at={0.6} t="5 teams" sub="keys, RPM, quotas" w={230} />
        <Box at={beat(S, "LiteLLM")} t="LiteLLM" sub="gateway :4000" color={C.teal} w={290} />
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Box at={beat(S, "Three phi three nodes")} t="3 x phi3" sub="primaries" color={C.blue} w={300} />
          <Box at={beat(S, "one llama three node")} t="llama3" sub="fallback" color={C.amber} w={300} />
          <Box at={beat(S, "three more are standbys")} t="3 x standby" sub="idle until needed" w={300} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 26, marginTop: 56 }}>
        <Box at={beat(S, "Postgres")} t="Postgres" sub="requests and spend" w={330} />
        <Box at={beat(S, "Redis")} t="Redis" sub="semantic cache" w={330} />
        <Box at={beat(S, "Prometheus and Grafana")} t="Prometheus + Grafana" sub="observability" w={420} />
      </div>
      <Appear at={beat(S, "It all runs natively")} style={{ marginTop: 44, fontSize: 34, color: C.muted }}>Native Ollama on Metal (Docker has no GPU on macOS)</Appear>
      <div style={{ position: "absolute", right: 90, top: 190, width: 560 }}>
        <Hbar at={mem} label="default ctx" value={15.5} max={16} color={C.red} unit=" GB" />
        <Hbar at={mem + 0.6} label="ctx 4096" value={3.84} max={16} color={C.teal} unit=" GB" />
        <Appear at={mem}><div style={{ fontSize: 26, color: C.muted }}>resident per phi3 node</div></Appear>
      </div>
      <Footnote>README.md (stack) {"·"} ROADMAP.md (Ollama cluster: feasibility)</Footnote>
    </Slide>
  );
};

// 6. Caps
export const Caps: React.FC = () => {
  const S = "seg6";
  return (
    <Slide title="Fix 1: a concurrency cap per team">
      <Narration seg={S} />
      <div style={{ maxWidth: 1500 }}>
        <Hbar at={beat(S, "It worked")} label="support, no cap" value={32} max={35} color={C.red} />
        <Hbar at={beat(S, "Support dropped")} label="support, capped" value={1.5} max={35} color={C.teal} />
      </div>
      <div style={{ display: "flex", gap: 28, marginTop: 50 }}>
        <Card at={beat(S, "Every rejected request")} color={C.amber} title="1. Rejections cost double">Each 429 is charged 2 RPM units. Research was starved: 88% fewer uncached tokens.</Card>
        <Card at={beat(S, "The cap rejects")} color={C.amber} title="2. It rejects, not queues">Excess requests get an immediate 429; clients must back off.</Card>
        <Card at={beat(S, "And during failover")} color={C.red} title="3. Bypassed in failover">18 requests in flight on a cap of 1, all queued on one node.</Card>
      </div>
      <Appear at={beat(S, "One correction")} style={{ marginTop: 40, fontSize: 32, color: C.amber }}>Correction: the first caps runs had a warm cache; the cold re-run is the one to trust.</Appear>
      <Footnote>docs/concurrency-experiment.md (Findings 1-3, Correction)</Footnote>
    </Slide>
  );
};

// 7. Pool
export const Pool: React.FC = () => {
  const S = "seg7";
  const N: React.FC<{ at: number; t: string; color: string }> = ({ at, t, color }) => <Appear at={at}><div style={{ background: C.panel, border: `3px solid ${color}`, borderRadius: 16, padding: "22px 30px", fontSize: 32, fontWeight: 700 }}>{t}</div></Appear>;
  return (
    <Slide title="Fix 2: a dedicated pool for the heavy team">
      <Narration seg={S} />
      <div style={{ display: "flex", gap: 90, alignItems: "flex-start" }}>
        <div><div style={{ fontSize: 28, color: C.muted, marginBottom: 14 }}>my-educational-model</div>
          <div style={{ display: "flex", gap: 20 }}><N at={0.8} t="node-1" color={C.blue} /><N at={1.0} t="node-2" color={C.blue} /></div></div>
        <div><div style={{ fontSize: 28, color: C.muted, marginBottom: 14 }}>research-model</div><N at={beat(S, "reserve a node")} t="research-node" color={C.red} /></div>
      </div>
      <div style={{ display: "flex", gap: 28, marginTop: 56 }}>
        <Big at={beat(S, "Support dropped")} value="1.3 s" label="support median during bursts (31.9 s shared)" color={C.teal} />
        <Big at={beat(S, "research kept its full throughput")} value="9,773" label="research uncached tokens (9,329 shared)" color={C.teal} />
      </div>
      <div style={{ display: "flex", gap: 28, marginTop: 30 }}>
        <Card at={beat(S, "The price is")} color={C.amber} title="The price">Heavy team queues behind itself; the shared fallback is unchanged.</Card>
        <Card at={beat(S, "I verified the wiring")} color={C.blue} title="Verified first">Wrong alias {"→"} 403. Shared traffic only on node-1 and node-2.</Card>
      </div>
      <Footnote>docs/dedicated-pool-experiment.md {"·"} experiments/pool_probes.py</Footnote>
    </Slide>
  );
};

// 8. Failure
export const Failure: React.FC = () => {
  const S = "seg8";
  return (
    <Slide title="When every primary is down">
      <Narration seg={S} />
      <Table head={["Configuration", "Result", "Verdict"]} widths={[640, 760, 400]} rows={[
        { at: beat(S, "One llama three node"), cells: ["One llama3 fallback", "13 and 11 timeouts in phase C", "baseline"] },
        { at: beat(S, "A concurrency limit"), cells: ["+ limit on the fallback", "10 failures in B, 4 in C (30 s blackout)", "timeouts become 500s"], color: C.amber },
        { at: beat(S, "A second fallback node"), cells: ["+ second fallback node", "10 timeouts in phase C", "no change"], color: C.amber },
        { at: beat(S, "What helped"), cells: ["standby pool + 5 s cooldown", "phase C median 6 to 16 s (31 to 39 s)", "helped latency"], color: C.teal },
      ]} />
      <Appear at={beat(S, "It runs phi three")} style={{ marginTop: 40, fontSize: 32, color: C.muted }}>The standby pool runs phi3, not llama3: a llama3 pool of primary size needs about 30 GB.</Appear>
      <Footnote>docs/fallback-experiment.md (Results, Follow-up) {"·"} experiments/make_fallback_config.py</Footnote>
    </Slide>
  );
};

// 9. Variance
const Dots: React.FC<{ at: number; label: string; vals: number[]; paren?: number; max: number; color: string }> = ({ at, label, vals, paren, max, color }) => {
  const p = useProgress(at, 0.8);
  const all = paren === undefined ? vals : [...vals, paren];
  return (
    <div style={{ display: "flex", alignItems: "center", margin: "18px 0", opacity: p }}>
      <div style={{ width: 300, fontSize: 30, color: C.muted }}>{label}</div>
      <div style={{ position: "relative", flex: 1, height: 14, background: "#0b0f19", borderRadius: 7 }}>
        {all.map((v, i) => <div key={i} style={{ position: "absolute", left: `${(v / max) * 100}%`, top: -13, width: 40, height: 40, marginLeft: -20, borderRadius: 20, background: i === vals.length ? "transparent" : color, border: `4px solid ${color}` }} />)}
      </div>
      <div style={{ width: 330, fontSize: 28, textAlign: "right" }}>{vals.join(" / ")}{paren !== undefined ? ` (${paren})` : ""} s</div>
    </div>
  );
};
export const Variance: React.FC = () => {
  const S = "seg9";
  const a = beat(S, "The pool result held"), b = beat(S, "The big fallback cut");
  return (
    <Slide title="Three runs each, cold cache">
      <Narration seg={S} />
      <div style={{ fontSize: 30, color: C.muted, marginBottom: 6 }}>Support median during a research burst</div>
      <Dots at={a} label="baseline" vals={[27.0, 25.1, 15.1]} max={40} color={C.red} />
      <Dots at={a + 0.3} label="big fallback" vals={[13.3, 32.9]} paren={20.9} max={40} color={C.amber} />
      <Dots at={a + 0.6} label="dedicated pool" vals={[1.5, 1.4, 1.4]} max={40} color={C.teal} />
      <div style={{ fontSize: 30, color: C.muted, margin: "34px 0 6px" }}>Median latency, all primaries down</div>
      <Dots at={b} label="baseline" vals={[31, 39, 32]} max={40} color={C.red} />
      <Dots at={b + 0.3} label="big fallback" vals={[6.2, 16.0]} paren={15.9} max={40} color={C.teal} />
      <Dots at={b + 0.6} label="dedicated pool" vals={[32, 27, 39]} max={40} color={C.red} />
      <Appear at={beat(S, "But my earlier claim")} style={{ marginTop: 34, fontSize: 36 }}>
        <span style={{ textDecoration: "line-through", color: C.muted }}>"Big fallback removes failures: 0 against 15 and 17"</span>
        <span style={{ color: C.amber }}>{"  "}{"→"} three new baselines: 0 / 0 / 0 failures</span></Appear>
      <Footnote>docs/variance-experiment.md {"·"} (value) = partly valid run, cache hit rate 52%, not used for conclusions</Footnote>
    </Slide>
  );
};

// 10. Measuring honestly
export const Honest: React.FC = () => {
  const S = "seg10";
  return (
    <Slide title="Four measurement mistakes">
      <Narration seg={S} />
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <Card at={beat(S, "A warm cache between runs")} color={C.amber} title="Warm cache across runs">Hit rate 83-90% against 75-78% cold. Fix: flush the cache before every run.</Card>
        <Card at={beat(S, "I labelled requests")} color={C.amber} title="Phase by finish time">Slow requests credited to later phases. Fix: label by start time; old report corrected.</Card>
        <Card at={beat(S, "The embedding node crashed")} color={C.red} title="Silent cache failure">GPU out of memory: hit rate fell from 74% to 0%. Fix: a preflight check aborts the run.</Card>
        <Card at={beat(S, "And my own preflight")} color={C.amber} title="Checker blind spot">Unjustified 429s 18-30 {"→"} 0 once the preflight requests were counted.</Card>
      </div>
      <Footnote>docs/simulation-report.md (Correction) {"·"} docs/variance-experiment.md {"·"} simulate.py: preflight_cache</Footnote>
    </Slide>
  );
};

// 11. Takeaways
export const Takeaways: React.FC = () => {
  const S = "seg11";
  const items: [string, string, string][] = [
    ["Limits control volume; isolation needs separate capacity.", "Limits control volume", C.teal],
    ["In an outage, capacity protects you, not clever limits.", "In an outage", C.teal],
    ["Repeat the run before you believe it.", "Repeat the run", C.amber],
    ["Check that your test rig works before you trust its numbers.", "And check that your test rig works", C.amber],
  ];
  return (
    <Slide title="Takeaways">
      <Narration seg={S} />
      {items.map(([t, ph, col], i) => (
        <Appear key={t} at={beat(S, ph)} style={{ fontSize: 50, margin: "30px 0", display: "flex", gap: 24 }}>
          <span style={{ color: col, fontWeight: 800 }}>{i + 1}</span><span>{t}</span>
        </Appear>
      ))}
      <Appear at={beat(S, "The code, the write-ups")} style={{ marginTop: 60, fontSize: 36, color: C.muted }}>Code, write-ups and every number are in the repository.
        <div style={{ marginTop: 14, fontSize: 40, color: C.teal, fontWeight: 700 }}>github.com/tuwallace/llm-gateway</div>
      </Appear>
    </Slide>
  );
};
