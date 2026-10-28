"""Segment 4: semantic cache. Needs the gateway running. Flushes the cache first, prints no keys."""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import simulate  # noqa: E402

simulate.flush_semantic_cache()
key = json.loads((ROOT / "teams_keys.json").read_text())["search"]["key"]
PROMPTS = [
    ("original question", "What is the capital of France?"),
    ("paraphrase", "Which city is the capital of France?"),
    ("same shape, other fact", "What is the capital of Germany?"),
    ("original again", "What is the capital of France?"),
]
print(f"  {'prompt':<26}{'text':<40}{'result':<8}{'time':>7}")
with httpx.Client(base_url="http://localhost:4000", headers={"Authorization": f"Bearer {key}"}, timeout=120) as c:
    for name, text in PROMPTS:
        t = time.time()
        r = c.post("/v1/chat/completions", json={"model": "my-educational-model", "max_tokens": 30,
                                                  "messages": [{"role": "user", "content": text}]})
        hit = "x-litellm-cache-key" in r.headers
        print(f"  {name:<26}{text:<40}{'HIT' if hit else 'miss':<8}{time.time() - t:>6.2f}s")
        time.sleep(1.5)  # let the cache entry be written before the next lookup
print("\n  similarity threshold 0.9 (litellm_config.yaml:79)")
