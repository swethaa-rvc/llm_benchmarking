"""
Talks to the four running demo agents over HTTP — the same /chat, /health and
/demo/reset endpoints the Streamlit UI uses. No credentials needed here; the
agents authenticate to Azure OpenAI themselves, on their own side.
"""

import uuid

import requests

from config import AGENTS

TIMEOUT_S = 120


def health_check_all() -> dict:
    """{"it-ops": True, ...} — call before a run so a dead agent fails loud
    and fast instead of every case in its dataset silently scoring 0."""
    status = {}
    for name, url in AGENTS.items():
        try:
            r = requests.get(f"{url}/health", timeout=5)
            status[name] = r.status_code == 200
        except Exception:
            status[name] = False
    return status


def reset_all() -> None:
    """Clears demo state (tickets/cases/sequences/recommendations) on every
    agent so results aren't polluted by records from an earlier run."""
    for name, url in AGENTS.items():
        try:
            requests.post(f"{url}/demo/reset", timeout=10)
        except Exception as e:
            print(f"[agent_client] warning: reset failed for {name}: {e}")


def _post_chat(url: str, session_id: str, message: str) -> dict:
    try:
        r = requests.post(
            f"{url}/chat",
            json={"session_id": session_id, "message": message},
            timeout=TIMEOUT_S,
        )
        if r.status_code != 200:
            return {"error": True, "response": f"HTTP {r.status_code}: {r.text[:300]}"}
        return r.json()
    except requests.exceptions.Timeout:
        return {"error": True, "response": "Request timed out."}
    except Exception as e:
        return {"error": True, "response": f"Request failed: {e}"}


def send(agent: str, message: str) -> dict:
    """One /chat turn on a fresh session. Returns the parsed response dict
    (or an error dict shaped the same way callers can check)."""
    return _post_chat(AGENTS[agent], f"bench-{uuid.uuid4().hex[:8]}", message)


def send_conversation(agent: str, messages: list) -> tuple:
    """Sends several turns in order on ONE session — for cases that need to
    create a record, then act on it, and check the reply to the second turn
    (e.g. an update doesn't silently change a gated record's status).

    Returns (last_result, transcript, turn_results) where transcript is a
    list of (user_message, agent_reply) pairs and turn_results is the full
    response dict for every turn actually completed — callers that need
    tokens/cost/latency should sum across turn_results rather than use only
    last_result, since each turn bills separately. Stops early on error."""
    url = AGENTS[agent]
    session_id = f"bench-{uuid.uuid4().hex[:8]}"
    transcript = []
    turn_results = []
    last = {}
    for message in messages:
        last = _post_chat(url, session_id, message)
        transcript.append((message, last.get("response", "")))
        turn_results.append(last)
        if last.get("error"):
            break
    return last, transcript, turn_results
