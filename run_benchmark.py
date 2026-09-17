"""
CLI entry point.

    python run_benchmark.py            run everything, reset demo state first
    python run_benchmark.py --no-reset skip the /demo/reset step
"""

import sys

import agent_client
import db
import report
from config import JUDGE
from runner import load_datasets, run_all


def main():
    print("Checking all four agents are up...")
    status = agent_client.health_check_all()
    for name, ok in status.items():
        print(f"  {'OK  ' if ok else 'DOWN'}  {name}")
    if not all(status.values()):
        down = [n for n, ok in status.items() if not ok]
        sys.exit(f"\nAgent(s) not reachable: {', '.join(down)}. "
                 f"Start every agent (ports 8101-8104) before running the benchmark.")

    if "--no-reset" not in sys.argv:
        print("\nResetting demo state on all four agents...")
        agent_client.reset_all()

    datasets = load_datasets()
    print(f"\nLoaded {len(datasets)} operations, "
         f"{sum(len(d['cases']) for d in datasets)} cases total.\n")

    run_id = db.start_run(JUDGE.get("name", ""), JUDGE.get("model", ""))

    # Insert each result as it's scored, not after the whole run finishes —
    # a crash partway through (a bad judge model, a network drop) must not
    # wipe out the cases that already scored fine.
    results = []
    for r in run_all(datasets):
        db.insert_result(run_id, r)
        results.append(r)
    db.finish_run(run_id)

    matrix = report.build_matrix(results)
    report.print_matrix(matrix)
    path = report.save(results, matrix)
    print(f"\nSaved: {path}")
    print(f"Stored in benchmark.db as run #{run_id} - "
         f"see rankings.py, sla_check.py, costs.py to query it.")


if __name__ == "__main__":
    main()
