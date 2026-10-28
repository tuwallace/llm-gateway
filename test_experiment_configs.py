"""The experiment config generators produce what their docs claim (no gateway needed)."""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent


def generate(tmp_path, *flags):
    out = tmp_path / "cfg.yaml"
    subprocess.run([sys.executable, str(ROOT / "experiments" / "make_fallback_config.py"), *flags, "--out", str(out)],
                   check=True, capture_output=True, cwd=ROOT)
    return yaml.safe_load(out.read_text())


def fallbacks(cfg):
    return [m for m in cfg["model_list"] if m["model_name"] == "my-fallback-model"]


def test_standby_pool_replaces_llama3_with_three_phi3_nodes(tmp_path):
    cfg = generate(tmp_path, "--standby", "3")
    fb = fallbacks(cfg)
    assert [m["model_info"]["id"] for m in fb] == ["fallback-node", "fallback-node-2", "fallback-node-3"]
    assert {m["litellm_params"]["model"] for m in fb} == {"ollama/phi3"}
    assert [m["litellm_params"]["api_base"] for m in fb] == [f"http://localhost:{p}" for p in (11439, 11440, 11441)]


def test_limit_and_cooldown_are_applied(tmp_path):
    cfg = generate(tmp_path, "--standby", "3", "--limit", "2", "--cooldown", "5")
    assert all(m["litellm_params"]["max_parallel_requests"] == 2 for m in fallbacks(cfg))
    assert cfg["router_settings"]["cooldown_time"] == 5


def test_primaries_and_embeddings_are_untouched(tmp_path):
    base = yaml.safe_load((ROOT / "litellm_config.yaml").read_text())
    cfg = generate(tmp_path, "--standby", "3", "--limit", "2")
    keep = lambda c: [m for m in c["model_list"] if m["model_name"] in ("my-educational-model", "ollama-embed")]
    assert keep(cfg) == keep(base)
    assert base["router_settings"]["cooldown_time"] == 30  # default config unchanged


def test_second_node_adds_one_llama3_deployment(tmp_path):
    cfg = generate(tmp_path, "--second-node")
    fb = fallbacks(cfg)
    assert [m["model_info"]["id"] for m in fb] == ["fallback-node", "fallback-node-2"]
    assert {m["litellm_params"]["model"] for m in fb} == {"ollama/llama3"}
