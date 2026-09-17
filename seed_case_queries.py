"""
Loads the exact query text for every dataset case into benchmark.db, so it's
joinable from sqlite_web's /query/ page (results only stores case_id, never
the message that was actually sent).

    python seed_case_queries.py
"""

import glob
import json
import os

import db

_DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS case_queries (
    agent    TEXT NOT NULL,
    case_id  TEXT NOT NULL,
    query    TEXT NOT NULL,
    PRIMARY KEY (agent, case_id)
);
"""


def main():
    conn = db.connect()
    conn.executescript(_SCHEMA)

    rows = []
    for path in glob.glob(os.path.join(_DATASETS_DIR, "**", "*.json"), recursive=True):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        agent = data.get("agent", "")
        for case in data.get("cases", []):
            msg = case.get("message")
            if msg is None and "messages" in case:
                msg = " | ".join(m.get("content", "") for m in case["messages"])
            rows.append((agent, case["id"], msg or ""))

    conn.executemany(
        "INSERT OR REPLACE INTO case_queries (agent, case_id, query) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    print(f"Loaded {len(rows)} case queries into benchmark.db (table: case_queries)")


if __name__ == "__main__":
    main()
