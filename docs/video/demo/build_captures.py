"""Capture the real output of the three demo scripts into anim/src/captures.json (read by the terminal replays).
Needs the gateway running (seg4). Run from anywhere: gateway-env/bin/python docs/video/demo/build_captures.py"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
out = {}
for key, script in (("seg3", "seg3_teams.py"), ("seg4", "seg4_cache.py"), ("seg5", "seg5_simulation.py")):
    r = subprocess.run([sys.executable, str(HERE / script)], cwd=ROOT, capture_output=True, text=True, check=True)
    out[key] = r.stdout.rstrip("\n")
(HERE.parent / "anim/src/captures.json").write_text(json.dumps(out, indent=1))
print({k: len(v.splitlines()) for k, v in out.items()}, "lines captured")
