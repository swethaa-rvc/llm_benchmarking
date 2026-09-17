"""
Prints agent/operation/model rankings from stored benchmark history.

    python rankings.py                latest run only, ranked by agent
    python rankings.py --all-time      every run ever stored, ranked by agent
    python rankings.py --by operation  rank by operation instead of agent
    python rankings.py --by model      rank by underlying model (e.g. the
                                        Azure GPT-4o / Claude / Gemini 3-way
                                        comparison) instead of agent
    python rankings.py --run 3         a specific run id
"""

import sys

import db

_BY_MAP = {"agent": "agent", "operation": "operation", "model": "model_name"}


def _latest_run_id() -> int | None:
    conn = db.connect()
    row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row["id"] if row else None


def main():
    args = sys.argv[1:]
    by = args[args.index("--by") + 1] if "--by" in args else "agent"
    if by not in _BY_MAP:
        sys.exit(f"--by must be one of: {', '.join(_BY_MAP)}")
    group_by = _BY_MAP[by]

    run_id = None
    if "--run" in args:
        run_id = int(args[args.index("--run") + 1])
    elif "--all-time" not in args:
        run_id = _latest_run_id()
        if run_id is None:
            sys.exit("No runs stored yet in benchmark.db - run python run_benchmark.py first.")

    scope = f"run #{run_id}" if run_id else "all-time history"
    print(f"Rankings by {by} - {scope}\n")

    rows = db.rankings(run_id=run_id, group_by=group_by)
    if not rows:
        print("No results found for this scope.")
        return

    print(f"{'rank':<6}{by:<20}{'avg score':>12}{'n cases':>10}")
    for i, row in enumerate(rows, 1):
        print(f"{i:<6}{row['name']:<20}{row['avg_score']*100:>11.0f}%{row['n']:>10}")


if __name__ == "__main__":
    main()
