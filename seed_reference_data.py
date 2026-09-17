"""
Loads pricing.json and sla_targets.json (or their .example.json fallbacks)
into benchmark.db. Run once after editing either file:

    python seed_reference_data.py
"""

import json
import os
import sys

import db

_HERE = os.path.dirname(__file__)


def _load(name: str) -> dict:
    real, example = os.path.join(_HERE, f"{name}.json"), os.path.join(_HERE, f"{name}.example.json")
    path = real if os.path.exists(real) else example
    if path == example:
        print(f"[seed] {name}.json not found - using {name}.example.json (placeholder values).",
              file=sys.stderr)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed_pricing() -> int:
    data = _load("pricing")
    for m in data["models"]:
        db.add_pricing(m["model_name"], m["price_per_million_prompt"], m["price_per_million_completion"])
    return len(data["models"])


def seed_sla_targets() -> int:
    data = _load("sla_targets")
    for t in data["targets"]:
        db.add_sla_target(t["metric"], t["comparison"], t["target_value"],
                          agent=t.get("agent"), operation=t.get("operation"))
    return len(data["targets"])


if __name__ == "__main__":
    n_pricing = seed_pricing()
    n_sla = seed_sla_targets()
    print(f"Seeded {n_pricing} pricing row(s), {n_sla} SLA target(s) into benchmark.db")
