# Companion video: tooling and sources

Sources and scripts for the YouTube walkthrough of this project. Rendered audio and video are **not** committed (large, regenerable);
`upload/` (the finished video and publishing text) is git-ignored. The pipeline is adapted from the helpdesk-rag project's video tooling.

| Path | What it is |
|---|---|
| `storyboard.md` | plan: per-segment narration, on-screen content and the repo/doc citation behind each claim |
| `script.md` | the narration actually spoken (11 segments); numbers come from `README.md` and `docs/*.md` |
| `narration/build_narration.py` | turns `script.md` into audio (Kokoro-82M, voice `af_heart`) and sentence timings |
| `anim/` | Remotion project: 8 animated clips (`Scenes.tsx`), 3 terminal replays (`LiveSegs.tsx`), the thumbnail; each step is timed to a spoken phrase |
| `demo/` | scripts whose real output the terminal replays show; `build_captures.py` captures it into `anim/src/captures.json` |
| `finalize.py` | joins the 11 clips and writes `upload/` (video, captions, chapters, thumbnail) |

The three terminal segments (3, 4, 5) are **replays of real captured output** and say so on screen; they are not live screen recordings.
Narration is synthetic: answer "yes" to YouTube's altered/synthetic content question.

## Rebuild

Needs Node.js, `ffmpeg`, and a Python with Kokoro (`kokoro`, `soundfile`) and `espeak-ng`. The commands below reuse the helpdesk-rag
project's Kokoro environment and its `anim/node_modules`; replace them with your own installs if you do not have that project.

```bash
# 0. refresh the captured output (needs the gateway and cache running)
gateway-env/bin/python docs/video/demo/build_captures.py
# 1. narration audio and timings
cd docs/video/narration && <kokoro-python> build_narration.py --engine kokoro --voice af_heart
# 2. clips (node_modules is a symlink to the helpdesk-rag install here; `npm install` in anim/ otherwise)
cd ../anim && npm run render:all && for c in Seg3 Seg4 Seg5; do npx remotion render src/index.ts $c out/$c.mp4 --overwrite --port=3100; done
npx remotion still src/index.ts Thumbnail out/thumbnail.png --port=3100
# 3. assemble
cd ../../.. && python3 docs/video/finalize.py
```

Remotion, Kokoro and the other tools have their own licences (Remotion has terms that depend on company size).
