"""
Checks stored results against sla_targets and reports any breach.

    python sla_check.py               latest run only
    python sla_check.py --all-time     every run ever stored
    python sla_check.py --run 3        a specific run id

Exits non-zero if any SLA is breached — usable as a CI/pipeline gate.
"""

import sys

import db
from rankings import _latest_run_id


def main():
    args = sys.argv[1:]
    run_id = None
    if "--run" in args:
        run_id = int(args[args.index("--run") + 1])
    elif "--all-time" not in args:
        run_id = _latest_run_id()
        if run_id is None:
            sys.exit("No runs stored yet in benchmark.db - run python run_benchmark.py first.")

    scope = f"run #{run_id}" if run_id else "all-time history"
    print(f"SLA check - {scope}\n")

    rows = db.check_slas(run_id=run_id)
    if not rows:
        print("No SLA targets defined - run python seed_reference_data.py first.")
        return

    any_breach = False
    for t in rows:
        if t["actual"] is None:
            print(f"  [NO DATA] {t['agent']:<14} {t['operation']:<14} {t['metric']} - no matching results")
            continue
        status = "BREACH" if t["breached"] else "OK"
        any_breach = any_breach or t["breached"]
        unit = "%" if t["metric"] == "accuracy" else "ms"
        actual_disp = t["actual"] * 100 if t["metric"] == "accuracy" else t["actual"]
        target_disp = t["target"] * 100 if t["metric"] == "accuracy" else t["target"]
        print(f"  [{status:<7}] {t['agent']:<14} {t['operation']:<14} {t['metric']:<16} "
             f"actual={actual_disp:.0f}{unit}  target {t['comparison']} {target_disp:.0f}{unit}  "
             f"(n={t['n_cases']})")

    print()
    if any_breach:
        print("One or more SLAs breached.")
        sys.exit(1)
    print("All SLAs met.")


if __name__ == "__main__":
    main()
