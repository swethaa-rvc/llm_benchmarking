"""
Prints cost breakdown from stored benchmark history.

    python costs.py                latest run only, by agent
    python costs.py --all-time      every run ever stored
    python costs.py --by operation  break down by operation instead of agent
    python costs.py --by model      break down by underlying model (e.g. the
                                     Azure GPT-4o / Claude / Gemini 3-way
                                     comparison) instead of agent
    python costs.py --run 3         a specific run id
"""

import sys

import db
from rankings import _latest_run_id

_BY_MAP = {"agent": "agent", "operation": "operation", "model": "model_name"}


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
    print(f"Cost by {by} - {scope}\n")

    rows = db.costs(run_id=run_id, group_by=group_by)
    if not rows:
        print("No results found for this scope.")
        return

    print(f"{by:<20}{'cost (USD)':>14}{'tokens':>12}{'n cases':>10}")
    total = 0.0
    for row in rows:
        cost = row["cost_usd"] or 0.0
        total += cost
        print(f"{row['name']:<20}{'$' + format(cost, '.4f'):>14}{row['total_tokens']:>12}{row['n']:>10}")
    print("-" * 56)
    print(f"{'TOTAL':<20}{'$' + format(total, '.4f'):>14}")
    print("\nCost is $0 for any model not in model_pricing - "
         "run python seed_reference_data.py to load pricing.json/pricing.example.json.")


if __name__ == "__main__":
    main()
