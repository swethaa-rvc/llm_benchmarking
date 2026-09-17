"""
Scoring. Every grading path in here either compares against a fixed expected
value or asks the independent judge model — never the candidate grading
itself, and never a hardcoded guess standing in for either.
"""

import json
import re
import subprocess
import sys
import tempfile
import textwrap

from config import JUDGE
from providers import call_model

_JUDGE_SYSTEM = """You are a strict, impartial grader for an LLM benchmark.
You did not produce the answer you are grading and have no stake in it
scoring well. Judge only against the rubric or reference given — do not
reward style, length or confidence. Reply with JSON only, no other text."""


def _ask_judge(prompt: str) -> dict:
    raw = call_model(JUDGE, _JUDGE_SYSTEM, prompt)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"score": 0.0, "reasoning": f"judge did not return JSON: {raw[:200]!r}"}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"score": 0.0, "reasoning": f"judge returned unparseable JSON: {raw[:200]!r}"}


def _final_answer_line(text: str) -> str | None:
    """Pulls the value off a trailing 'ANSWER: <value>' line, for tasks that
    are asked to show their work before stating a final answer."""
    match = re.search(r"ANSWER:\s*(.+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def exact_or_semantic_match(input_text: str, expected: str, actual: str) -> dict:
    """Programmatic match first (cheap, deterministic) — tried against the
    whole output and, where present, an 'ANSWER: <value>' line. Falls back
    to the judge only to allow for formatting differences that don't change
    correctness — the judge cannot override an exact match either way."""
    expected_norm = str(expected).strip().lower()
    if actual.strip().lower() == expected_norm:
        return {"score": 1.0, "reasoning": "exact match", "method": "exact"}

    final = _final_answer_line(actual)
    if final is not None and final.strip().lower() == expected_norm:
        return {"score": 1.0, "reasoning": "exact match on ANSWER line", "method": "exact"}

    prompt = f"""Input given to the model:
{input_text}

Reference (correct) answer:
{expected}

Model's actual answer:
{actual}

Is the model's answer correct — the same meaning/value as the reference,
allowing for wording or formatting differences only? Reply with JSON:
{{"score": 1.0 or 0.0, "reasoning": "one sentence"}}"""
    result = _ask_judge(prompt)
    result["method"] = "judge_semantic"
    return result


def rubric_score(input_text: str, rubric: str, actual: str) -> dict:
    """Open-ended operations (summarization, RAG, translation, safety) have
    no single correct string — the judge scores against a written rubric."""
    prompt = f"""Input given to the model:
{input_text}

Grading rubric:
{rubric}

Model's actual answer:
{actual}

Score the answer from 0.0 (fails the rubric) to 1.0 (fully meets it). Reply
with JSON: {{"score": <float 0-1>, "reasoning": "one or two sentences"}}"""
    result = _ask_judge(prompt)
    result["method"] = "judge_rubric"
    return result


def run_code_tests(code: str, test_code: str, timeout_s: int = 10) -> dict:
    """
    Executes model-generated code against hidden unit tests in a separate
    subprocess with a timeout.

    This is adequate for benchmarking your own candidate models locally.
    It is NOT a security sandbox — do not point this at untrusted or
    adversarial model output without containerizing the subprocess
    (e.g. Docker with no network, a memory/CPU cap, a non-root user).
    """
    combined = textwrap.dedent(code) + "\n\n" + textwrap.dedent(test_code)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(combined)
        path = f.name

    try:
        proc = subprocess.run([sys.executable, path], capture_output=True,
                              text=True, timeout=timeout_s)
        passed = proc.returncode == 0
        return {
            "score": 1.0 if passed else 0.0,
            "reasoning": "all tests passed" if passed else proc.stderr[-400:],
            "method": "code_tests",
        }
    except subprocess.TimeoutExpired:
        return {"score": 0.0, "reasoning": f"timed out after {timeout_s}s", "method": "code_tests"}


def score_case(op_type: str, case: dict, actual: str) -> dict:
    """Dispatches to the right grading method for one dataset entry's type."""
    if op_type == "exact":
        return exact_or_semantic_match(case["input"], case["expected"], actual)
    if op_type == "judge_rubric":
        return rubric_score(case["input"], case["rubric"], actual)
    if op_type == "code_tests":
        return run_code_tests(actual, case["tests"])
    raise ValueError(f"Unknown grading type: {op_type!r}")
