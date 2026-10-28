#!/usr/bin/env python3
"""Builds the upload folder: docs/video/upload/{llm-gateway-video.mp4, captions.srt, chapters.txt, thumbnail.png} and refreshes the
chapter list inside upload/description.txt from the real clip durations. Joins the 11 rendered clips (anim/out/*.mp4) in script order,
trims the idle tail of each clip, fades in/out, writes captions from the narration timings.   Run:  python3 docs/video/finalize.py
(Adapted from the helpdesk-rag video pipeline.)"""
import json, pathlib, re, shutil, subprocess, textwrap

HERE = pathlib.Path(__file__).resolve().parent
OUT, UP = HERE / "anim/out", HERE / "upload"
N = json.loads((HERE / "anim/src/narration.json").read_text())
ORDER = [("Hook", "seg1", "Five teams, one gateway"), ("Stack", "seg2", "What I built"), ("Seg3", "seg3", "Keys, limits and token quotas"),
         ("Seg4", "seg4", "The semantic cache"), ("Seg5", "seg5", "The simulation: limits hold, latency doesn't"), ("Caps", "seg6", "Fix 1: concurrency caps"),
         ("Pool", "seg7", "Fix 2: a dedicated node pool"), ("Failure", "seg8", "When every primary dies"), ("Variance", "seg9", "Run it again: what survived"),
         ("Honest", "seg10", "Measuring honestly"), ("Takeaways", "seg11", "Takeaways")]
TRIM = 2.4          # the 2 s hold Remotion adds + the 0.4 s of silence the narration builder appends; removed from every clip except the last
HEAD = 0.25         # of the 0.5 s lead-in silence at the start of each narration, removed from every clip except the first
FADE_IN, FADE_OUT = 0.6, 0.9

def run(cmd): return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
def probe(f, entry): return run(["ffprobe", "-v", "error", "-show_entries", entry, "-of", "csv=p=0", str(f)]).strip()
ts = lambda t, sep=",": f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}{sep}{int(round((t % 1) * 1000)):03d}"

UP.mkdir(exist_ok=True)
clips = []
for cid, seg, title in ORDER:
    f = OUT / f"{cid}.mp4"
    assert f.exists(), f"missing {f}: render it first (npm run render:all in docs/video/anim)"
    d = float(probe(f, "format=duration")); clips.append(dict(cid=cid, seg=seg, title=title, file=f, dur=d))
for i, c in enumerate(clips):
    c["head"] = HEAD if i > 0 else 0.0
    c["keep"] = c["dur"] - c["head"] - (TRIM if i < len(clips) - 1 else 0)
    c["offset"] = sum(x["keep"] for x in clips[:i])
total = sum(c["keep"] for c in clips)

parts, ins = [], []
for i, c in enumerate(clips):
    ins += ["-i", str(c["file"])]
    parts.append(f"[{i}:v]trim=start={c['head']:.3f}:duration={c['keep']:.3f},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v{i}];"
                 f"[{i}:a]atrim=start={c['head']:.3f}:duration={c['keep']:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]")
cat = "".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][a]"
fade = (f"[v]fade=t=in:st=0:d={FADE_IN},fade=t=out:st={total - FADE_OUT:.3f}:d={FADE_OUT}[vf];"
        f"[a]afade=t=in:st=0:d={FADE_IN},afade=t=out:st={total - FADE_OUT:.3f}:d={FADE_OUT}[af]")
final = UP / "llm-gateway-video.mp4"
run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts) + ";" + cat + ";" + fade, "-map", "[vf]", "-map", "[af]",
     "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
     "-movflags", "+faststart", str(final)])

cues = []
for c in clips:
    for s in N[c["seg"]]["sentences"]:
        a, b = c["offset"] + s["start"] - c["head"], c["offset"] + s["end"] - c["head"]
        if s["start"] - c["head"] > c["keep"]: continue
        words = s["text"].split(); chunks, cur = [], ""
        for w in words:                                   # split long sentences into cues of <= 76 characters (two caption lines)
            if len(cur) + len(w) + 1 > 76 and cur: chunks.append(cur); cur = w
            else: cur = (cur + " " + w).strip()
        chunks.append(cur); L = sum(len(x) for x in chunks); t = a
        for x in chunks:
            seg_len = (b - a) * len(x) / L; cues.append((t, t + seg_len, x)); t += seg_len
srt = [f"{i}\n{ts(a)} --> {ts(b)}\n" + "\n".join(textwrap.wrap(x, 44)) + "\n" for i, (a, b, x) in enumerate(cues, 1)]
(UP / "captions.srt").write_text("\n".join(srt))

chapters = "\n".join(f"{int(c['offset'] // 60)}:{int(c['offset'] % 60):02d} {c['title']}" for c in clips)
(UP / "chapters.txt").write_text(chapters + "\n")
d = UP / "description.txt"
if d.exists():  # refresh the chapter block between "CHAPTERS" and "SOURCES"
    d.write_text(re.sub(r"(CHAPTERS\n).*?(\n\nSOURCES)", lambda m: m.group(1) + chapters + m.group(2), d.read_text(), flags=re.S))
if (OUT / "thumbnail.png").exists(): shutil.copy(OUT / "thumbnail.png", UP / "thumbnail.png")
print(f"wrote {final} ({total / 60:.2f} min), {len(cues)} caption cues, {len(clips)} chapters")
