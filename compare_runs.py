"""
Diffs two benchmark runs — "before" vs "after" a change to an agent (a
prompt edit, a rubric change, a different underlying model, etc.).

    python compare_runs.py                              # two most recent runs in results/
    python compare_runs.py results/summary_A.csv results/summary_B.csv
"""

import csv
import glob
import os
import sys

_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def _load(path: str) -> dict:
    """{(operation, agent): avg_score}"""
    scores = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            scores[(row["operation"], row["agent"])] = float(row["avg_score"])
    return scores


def _two_most_recent() -> tuple:
    files = sorted(glob.glob(os.path.join(_RESULTS_DIR, "summary_*.csv")))
    if len(files) < 2:
        sys.exit(f"Need at least 2 saved runs in {_RESULTS_DIR}/ to compare — "
                 f"found {len(files)}. Run python run_benchmark.py twice first.")
    return files[-2], files[-1]


def compare(before_path: str, after_path: str) -> None:
    before, after = _load(before_path), _load(after_path)
    keys = sorted(set(before) | set(after))

    print(f"BEFORE: {os.path.basename(before_path)}")
    print(f"AFTER:  {os.path.basename(after_path)}\n")

    header = f"{'operation':<40}{'agent':<16}{'before':>9}{'after':>9}{'delta':>9}  flag"
    print(header)
    print("-" * len(header))

    regressions, improvements = [], []
    for op, agent in keys:
        b = before.get((op, agent))
        a = after.get((op, agent))
        if b is None:
            flag = "NEW"
        elif a is None:
            flag = "REMOVED"
        else:
            delta = a - b
            if delta <= -0.15:
                flag = "REGRESSION"
                regressions.append((op, agent, delta))
            elif delta >= 0.15:
                flag = "IMPROVED"
                improvements.append((op, agent, delta))
            else:
                flag = ""
        b_str = f"{b*100:.0f}%" if b is not None else "--"
        a_str = f"{a*100:.0f}%" if a is not None else "--"
        d_str = f"{(a-b)*100:+.0f}%" if (a is not None and b is not None) else "--"
        print(f"{op[:39]:<40}{agent:<16}{b_str:>9}{a_str:>9}{d_str:>9}  {flag}")

    print()
    if regressions:
        print(f"⚠ {len(regressions)} regression(s) (score dropped 15pts+):")
        for op, agent, delta in regressions:
            print(f"    {agent:<16} {op}  ({delta*100:+.0f}%)")
    if improvements:
        print(f"✓ {len(improvements)} improvement(s) (score rose 15pts+):")
        for op, agent, delta in improvements:
            print(f"    {agent:<16} {op}  ({delta*100:+.0f}%)")
    if not regressions and not improvements:
        print("No operation moved by more than 15 points either way.")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        compare(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        b, a = _two_most_recent()
        compare(b, a)
    else:
        sys.exit("Usage: python compare_runs.py [before.csv after.csv]")
