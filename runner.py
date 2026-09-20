"""
Runs every dataset's cases against the live agents and grades each reply.

Datasets are organized per agent (datasets/<agent>/*.json) — each file names
its agent once at the top level, so individual cases don't repeat it.
"""

import glob
import json
import os

import agent_client
from judge import rubric_score

_DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")


def load_datasets() -> list:
    datasets = []
    for path in sorted(glob.glob(os.path.join(_DATASETS_DIR, "**", "*.json"), recursive=True)):
        with open(path, encoding="utf-8") as f:
            datasets.append(json.load(f))
    return datasets


def run_case(operation: str, agent: str, case: dict) -> dict:
    if "messages" in case:
        result, transcript, turn_results = agent_client.send_conversation(
            agent, case["messages"])
        context = "\n\n".join(f"User: {u}\nAgent: {a}" for u, a in transcript)
        # Multi-turn cases bill per turn — sum across every turn actually run,
        # not just the last one, or cost/latency would undercount them.
        prompt_tokens = sum(t.get("prompt_tokens", 0) for t in turn_results)
        completion_tokens = sum(t.get("completion_tokens", 0) for t in turn_results)
        total_tokens = sum(t.get("total_tokens", 0) for t in turn_results)
        response_time_ms = sum(t.get("response_time_ms", 0) for t in turn_results)
        model_name = next((t.get("model", "") for t in reversed(turn_results) if t.get("model")), "")
    else:
        result = agent_client.send(agent, case["message"])
        context = case["message"]
        prompt_tokens = result.get("prompt_tokens", 0)
        completion_tokens = result.get("completion_tokens", 0)
        total_tokens = result.get("total_tokens", 0)
        response_time_ms = result.get("response_time_ms", 0)
        model_name = result.get("model", "")

    actual = result.get("response", "") if not result.get("error") else ""

    if result.get("error"):
        return {
            "operation": operation, "case_id": case["id"], "agent": agent,
            "score": 0.0,
            "reasoning": f"agent call failed: {result['response']}",
            "actual": "", "method": "call_failed", "query": context,
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "response_time_ms": 0, "model_name": model_name,
        }

    try:
        grade = rubric_score(context, case["rubric"], actual)
    except Exception as e:
        return {
            "operation": operation, "case_id": case["id"], "agent": agent,
            "score": 0.0,
            "reasoning": f"judge call failed: {e}",
            "actual": actual, "method": "judge_failed", "query": context,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": total_tokens, "response_time_ms": response_time_ms,
            "model_name": model_name,
        }
    return {
        "operation": operation, "case_id": case["id"], "agent": agent,
        "score": grade.get("score", 0.0),
        "reasoning": grade.get("reasoning", ""), "actual": actual,
        "method": grade.get("method", "judge_rubric"), "query": context,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "total_tokens": total_tokens, "response_time_ms": response_time_ms,
        "model_name": model_name,
    }


def run_all(datasets: list, verbose: bool = True):
    """Yields each case's result as soon as it's scored, so a caller can
    persist incrementally — a crash partway through a run must not lose the
    cases that already finished."""
    for ds in datasets:
        op, agent = ds["operation"], ds["agent"]
        for case in ds["cases"]:
            r = run_case(op, agent, case)
            if verbose:
                mark = "PASS" if r["score"] >= 0.5 else "FAIL"
                print(f"  [{mark}] {r['agent']:<14} {op[:38]:<38} score={r['score']:.2f}")
            yield r
