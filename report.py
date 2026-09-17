"""
Aggregates raw per-case results into an agent x operation accuracy table.
"""

import csv
import json
import os
from datetime import datetime, timezone

from config import AGENTS

_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def build_matrix(results: list) -> dict:
    """{operation: {agent: {"avg": float, "n": int}}}"""
    matrix = {}
    for r in results:
        op, agent = r["operation"], r["agent"]
        matrix.setdefault(op, {})
        cell = matrix[op].setdefault(agent, {"total": 0.0, "n": 0})
        cell["total"] += r["score"]
        cell["n"] += 1
    for op in matrix:
        for agent in matrix[op]:
            cell = matrix[op][agent]
            cell["avg"] = cell["total"] / cell["n"] if cell["n"] else 0.0
    return matrix


def print_matrix(matrix: dict) -> None:
    agents = list(AGENTS.keys())
    header = f"{'operation':<42}" + "".join(f"{a:>16}" for a in agents)
    print("\n" + header)
    print("-" * len(header))
    for op, row in matrix.items():
        line = f"{op[:41]:<42}"
        for a in agents:
            cell = row.get(a)
            line += f"{cell['avg']*100:>15.0f}%" if cell else f"{'--':>16}"
        print(line)

    overall = {}
    for op, row in matrix.items():
        for a, cell in row.items():
            overall.setdefault(a, {"total": 0.0, "n": 0})
            overall[a]["total"] += cell["total"]
            overall[a]["n"] += cell["n"]
    print("-" * len(header))
    line = f"{'OVERALL':<42}"
    for a in agents:
        cell = overall.get(a)
        line += f"{(cell['total']/cell['n'])*100:>15.0f}%" if cell and cell["n"] else f"{'--':>16}"
    print(line)


def save(results: list, matrix: dict) -> str:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_path = os.path.join(_RESULTS_DIR, f"raw_{stamp}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    csv_path = os.path.join(_RESULTS_DIR, f"summary_{stamp}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["operation", "agent", "avg_score", "n_cases"])
        for op, row in matrix.items():
            for agent, cell in row.items():
                w.writerow([op, agent, f"{cell['avg']:.3f}", cell["n"]])

    return csv_path
