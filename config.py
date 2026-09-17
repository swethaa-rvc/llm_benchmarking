"""
Loads models.json (the judge model) and its .env credentials, and defines the
four agents under test — fixed local HTTP endpoints, not credentialed models,
since they're the running demo services themselves.

models.json is never committed — copy models.example.json and edit it.
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

_HERE = os.path.dirname(__file__)
_MODELS_PATH = os.path.join(_HERE, "models.json")
_EXAMPLE_PATH = os.path.join(_HERE, "models.example.json")


def _load() -> dict:
    path = _MODELS_PATH if os.path.exists(_MODELS_PATH) else _EXAMPLE_PATH
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if path == _EXAMPLE_PATH:
        print(f"[config] models.json not found - running with {os.path.basename(_EXAMPLE_PATH)}. "
              f"Copy it to models.json and pick a real judge model.", file=sys.stderr)
    return cfg


_CFG = _load()
JUDGE = _CFG["judge"]

# The four agents under test. Ports match revinci-ai-agents-demo-bundle's
# README exactly — all four must already be running before a benchmark run.
AGENTS = {
    "it-ops":        "http://localhost:8101",
    "hr":            "http://localhost:8102",
    "sales":         "http://localhost:8103",
    "data-analysis": "http://localhost:8104",
}


def resolve_credentials(model_cfg: dict) -> dict:
    """Turn a model's *_env fields into the actual values from .env."""
    creds = {}
    for field, env_key in model_cfg.items():
        if field.endswith("_env"):
            value = os.getenv(env_key, "")
            if not value:
                print(f"[config] warning: {env_key} is empty in .env "
                      f"(needed by model '{model_cfg.get('name')}')", file=sys.stderr)
            creds[field[:-4]] = value  # "api_key_env" -> "api_key"
    return creds
