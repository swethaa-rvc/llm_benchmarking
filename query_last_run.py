"""
Latest run's results with the exact query text joined in from datasets/,
since results only stores case_id, not the message that was sent.

    python query_last_run.py               latest run, whatever it is
    python query_last_run.py --run 12       a specific run id
"""

import argparse
import glob
import json
import os
import sys

import db

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")


def _load_messages() -> dict:
    """{(agent, case_id): message} from every dataset file."""
    out = {}
    for path in glob.glob(os.path.join(_DATASETS_DIR, "**", "*.json"), recursive=True):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        agent = data.get("agent", "")
        for case in data.get("cases", []):
            msg = case.get("message")
            if msg is None and "messages" in case:
                msg = " | ".join(m.get("content", "") for m in case["messages"])
            out[(agent, case["id"])] = msg or ""
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, default=None)
    args = ap.parse_args()

    conn = db.connect()
    run_id = args.run or conn.execute("SELECT MAX(id) FROM runs").fetchone()[0]
    ru = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    rows = conn.execute(
        "SELECT * FROM results WHERE run_id = ? ORDER BY agent, operation, case_id",
        (run_id,),
    ).fetchall()
    conn.close()

    messages = _load_messages()

    print(f"Run {run_id}  |  judge: {ru['judge_name']} {ru['judge_model'] or ''}  "
          f"|  started: {ru['started_at']}\n")

    cols = ["agent", "case_id", "query", "model", "in_tok", "out_tok",
            "time_ms", "score", "reasoning"]
    data = []
    for r in rows:
        query = messages.get((r["agent"], r["case_id"]), "")
        data.append([
            r["agent"], r["case_id"], query, r["model_name"] or "",
            r["prompt_tokens"], r["completion_tokens"], r["response_time_ms"],
            f"{r['score']:.2f}", (r["reasoning"] or "")[:80],
        ])

    widths = [max(len(str(c)) for c in [col] + [row[i] for row in data])
              for i, col in enumerate(cols)]
    widths = [min(w, 60) for w in widths]

    def fmt_row(vals):
        return "  ".join(str(v)[:w].ljust(w) for v, w in zip(vals, widths))

    print(fmt_row(cols))
    print("  ".join("-" * w for w in widths))
    for row in data:
        print(fmt_row(row))
    print(f"\n{len(data)} row(s)")


if __name__ == "__main__":
    main()
