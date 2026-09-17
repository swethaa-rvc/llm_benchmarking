"""
The 3-way comparison, per query: for every test case, shows how each
underlying model scored on that exact same question — not just an overall
average. This is what "judge the score for each LLM per query" means.

    python compare_models.py
"""

import sys

import db


def main():
    cases = db.per_case_comparison()
    if not cases:
        sys.exit("No results stored yet — run python run_benchmark.py for each model first.")

    models = sorted({m for c in cases for m in c["scores"]})
    if len(models) < 2:
        print(f"Only one model found in benchmark.db so far ({models[0] if models else 'none'}) — "
             f"run the benchmark again with a different LLM_PROVIDER in the demo bundle's .env "
             f"to get a real comparison.\n")

    header = f"{'agent':<14}{'operation':<40}{'case':<10}" + "".join(f"{m:>18}" for m in models)
    print(header)
    print("-" * len(header))

    winners = {m: 0 for m in models}
    for c in cases:
        line = f"{c['agent']:<14}{c['operation'][:39]:<40}{c['case_id']:<10}"
        best_score, best_models = -1, []
        for m in models:
            s = c["scores"].get(m)
            line += f"{s*100:>17.0f}%" if s is not None else f"{'--':>18}"
            if s is not None:
                if s > best_score:
                    best_score, best_models = s, [m]
                elif s == best_score:
                    best_models.append(m)
        print(line)
        for m in best_models:
            winners[m] += 1

    print("\nWin count (best score on a case; ties count for every tied model):")
    for m, n in sorted(winners.items(), key=lambda kv: -kv[1]):
        print(f"  {m:<20} {n}")


if __name__ == "__main__":
    main()
