"""
Loads the judge model (JUDGE_PROVIDER / JUDGE_MODEL in .env, else models.json)
and its .env credentials, and defines the
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


# Credential env vars each provider reads when the judge is picked from .env
# rather than models.json — the same names the agents' own .env uses.
_PROVIDER_CREDS = {
    "openai":       {"api_key_env": "OPENAI_API_KEY"},
    "anthropic":    {"api_key_env": "ANTHROPIC_API_KEY"},
    "gemini":       {"api_key_env": "GEMINI_API_KEY"},
    "together":     {"api_key_env": "TOGETHER_API_KEY"},
    "azure_openai": {"api_key_env": "AZURE_OPENAI_API_KEY",
                     "endpoint_env": "AZURE_OPENAI_ENDPOINT",
                     "api_version_env": "AZURE_OPENAI_API_VERSION"},
}


def _judge(cfg: dict) -> dict:
    """JUDGE_PROVIDER / JUDGE_MODEL in .env override models.json, so the judge
    is switched the same way the agents' LLM_PROVIDER is — an env var and a
    restart. For azure_openai, JUDGE_MODEL is the deployment name."""
    provider = os.getenv("JUDGE_PROVIDER", "").strip()
    model = os.getenv("JUDGE_MODEL", "").strip()
    if not provider and not model:
        return cfg["judge"]
    if not (provider and model):
        sys.exit("[config] set both JUDGE_PROVIDER and JUDGE_MODEL in .env, or neither")
    if provider not in _PROVIDER_CREDS:
        sys.exit(f"[config] unknown JUDGE_PROVIDER {provider!r} - expected one of "
                 f"{', '.join(_PROVIDER_CREDS)}")
    judge = {"name": os.getenv("JUDGE_NAME", f"{model}-judge"),
             "provider": provider, "model": model, **_PROVIDER_CREDS[provider]}
    if provider == "azure_openai":
        judge["deployment"] = model
    return judge


_CFG = _load()
JUDGE = _judge(_CFG)

# The four agents under test. Ports match revinci-ai-agents-demo-bundle's
# README exactly — all four must already be running before a benchmark run.
# Host defaults to localhost for running this project directly; running
# inside a container needs AGENT_HOST=host.docker.internal instead, since
# "localhost" there would mean the container itself, not your machine.
_AGENT_HOST = os.getenv("AGENT_HOST", "localhost")
AGENTS = {
    "it-ops":        f"http://{_AGENT_HOST}:8101",
    "hr":            f"http://{_AGENT_HOST}:8102",
    "sales":         f"http://{_AGENT_HOST}:8103",
    "data-analysis": f"http://{_AGENT_HOST}:8104",
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
