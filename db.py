"""
Durable storage for benchmark data — SQLite, one file (benchmark.db).

Rankings are never stored, only computed on read (AVG(score) grouped by
agent) — a stored ranking would go stale the moment new results land.
SLA breaches and costs are likewise computed from `results` + the two
reference tables (model_pricing, sla_targets), not cached.

See ARCHITECTURE.md for the full design and why SQLite was chosen.
"""

import os
import sqlite3
from datetime import datetime, timezone

_DB_PATH = os.path.join(os.path.dirname(__file__), "benchmark.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    judge_name   TEXT,
    judge_model  TEXT,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL REFERENCES runs(id),
    agent              TEXT NOT NULL,
    operation          TEXT NOT NULL,
    case_id            TEXT NOT NULL,
    plan               TEXT,
    query              TEXT,
    score              REAL NOT NULL,
    reasoning          TEXT,
    prompt_tokens      INTEGER DEFAULT 0,
    completion_tokens  INTEGER DEFAULT 0,
    total_tokens       INTEGER DEFAULT 0,
    response_time_ms   INTEGER DEFAULT 0,
    model_name         TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_run   ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_agent ON results(agent);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_name                    TEXT NOT NULL,
    price_per_million_prompt      REAL NOT NULL,
    price_per_million_completion  REAL NOT NULL,
    effective_from                TEXT NOT NULL,
    PRIMARY KEY (model_name, effective_from)
);

CREATE TABLE IF NOT EXISTS sla_targets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent         TEXT,      -- NULL = applies to every agent
    operation     TEXT,      -- NULL = applies to every operation
    metric        TEXT NOT NULL,   -- 'accuracy' | 'response_time_ms'
    comparison    TEXT NOT NULL,   -- 'gte' | 'lte'
    target_value  REAL NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # CREATE TABLE IF NOT EXISTS doesn't add columns to an already-existing
    # table, so a column added after the table was first created needs its
    # own migration here. Safe to run every connect() — skipped once present.
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(results)")}
    if "query" not in existing:
        conn.execute("ALTER TABLE results ADD COLUMN query TEXT")
        conn.commit()
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Runs ─────────────────────────────────────────────────────────────────────

def start_run(judge_name: str, judge_model: str, notes: str = "") -> int:
    conn = connect()
    cur = conn.execute(
        "INSERT INTO runs (started_at, judge_name, judge_model, notes) VALUES (?, ?, ?, ?)",
        (_now(), judge_name, judge_model, notes),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def finish_run(run_id: int) -> None:
    conn = connect()
    conn.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (_now(), run_id))
    conn.commit()
    conn.close()


# ── Results ──────────────────────────────────────────────────────────────────

def insert_result(run_id: int, r: dict) -> None:
    conn = connect()
    conn.execute(
        """INSERT INTO results
           (run_id, agent, operation, case_id, plan, query, score, reasoning,
            prompt_tokens, completion_tokens, total_tokens, response_time_ms,
            model_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, r["agent"], r["operation"], r["case_id"], r.get("plan", ""),
         r.get("query", ""), r["score"], r.get("reasoning", ""),
         r.get("prompt_tokens", 0), r.get("completion_tokens", 0),
         r.get("total_tokens", 0), r.get("response_time_ms", 0),
         r.get("model_name", ""), _now()),
    )
    conn.commit()
    conn.close()


# ── Reference data: pricing and SLA targets ─────────────────────────────────

def add_pricing(model_name: str, price_per_million_prompt: float,
                price_per_million_completion: float, effective_from: str = None) -> None:
    conn = connect()
    conn.execute(
        """INSERT OR REPLACE INTO model_pricing
           (model_name, price_per_million_prompt, price_per_million_completion, effective_from)
           VALUES (?, ?, ?, ?)""",
        (model_name, price_per_million_prompt, price_per_million_completion, effective_from or _now()),
    )
    conn.commit()
    conn.close()


def add_sla_target(metric: str, comparison: str, target_value: float,
                   agent: str = None, operation: str = None) -> None:
    """Insert an SLA target, skipping it if an identical active target
    already exists — makes re-running seed_reference_data.py idempotent
    instead of piling up duplicate rows. Uses `IS ?` (not `= ?`) for
    agent/operation since most targets are NULL (applies to all), and
    SQL's `= NULL` never matches."""
    conn = connect()
    conn.execute(
        """INSERT INTO sla_targets (agent, operation, metric, comparison, target_value, active)
           SELECT ?, ?, ?, ?, ?, 1
           WHERE NOT EXISTS (
               SELECT 1 FROM sla_targets
               WHERE metric = ? AND comparison = ? AND target_value = ?
                 AND agent IS ? AND operation IS ? AND active = 1
           )""",
        (agent, operation, metric, comparison, target_value,
         metric, comparison, target_value, agent, operation),
    )
    conn.commit()
    conn.close()


# ── Rankings (computed, never stored) ────────────────────────────────────────

def rankings(run_id: int = None, group_by: str = "agent") -> list:
    """Average score per `group_by` ('agent', 'operation', or 'model_name'),
    best first. Pass run_id to scope to one run; omit it to rank across all
    history — use group_by='model_name' with no run_id to see which
    underlying model actually scored best across several single-model runs
    (e.g. the Azure/Claude/Gemini 3-way comparison)."""
    if group_by not in ("agent", "operation", "model_name"):
        raise ValueError("group_by must be 'agent', 'operation', or 'model_name'")
    conn = connect()
    where = "WHERE run_id = ?" if run_id else ""
    params = (run_id,) if run_id else ()
    rows = conn.execute(
        f"""SELECT {group_by} AS name, AVG(score) AS avg_score, COUNT(*) AS n
            FROM results {where}
            GROUP BY {group_by} ORDER BY avg_score DESC""",
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── SLA breach checking ──────────────────────────────────────────────────────

def check_slas(run_id: int = None) -> list:
    """Every active SLA target, with the actual measured value and whether
    it's currently breached. Scoped to one run if run_id given, else all
    history."""
    conn = connect()
    targets = conn.execute("SELECT * FROM sla_targets WHERE active = 1").fetchall()

    out = []
    for t in targets:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id = ?"); params.append(run_id)
        if t["agent"]:
            clauses.append("agent = ?"); params.append(t["agent"])
        if t["operation"]:
            clauses.append("operation = ?"); params.append(t["operation"])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        col = "score" if t["metric"] == "accuracy" else "response_time_ms"
        row = conn.execute(f"SELECT AVG({col}) AS actual, COUNT(*) AS n FROM results {where}", params).fetchone()
        actual = row["actual"]
        breached = None
        if actual is not None:
            breached = (actual < t["target_value"]) if t["comparison"] == "gte" else (actual > t["target_value"])

        out.append({
            "id": t["id"], "agent": t["agent"] or "all", "operation": t["operation"] or "all",
            "metric": t["metric"], "comparison": t["comparison"], "target": t["target_value"],
            "actual": actual, "n_cases": row["n"], "breached": breached,
        })
    conn.close()
    return out


# ── Per-query, multi-model comparison ────────────────────────────────────────

def per_case_comparison() -> list:
    """Every case, with each model's score for that exact same query side by
    side — {"agent", "operation", "case_id", "scores": {model_name: score}}.
    This is the 3-way comparison view: how did GPT-5.1 vs Claude vs Gemini
    each answer THIS specific query, not just their overall averages."""
    conn = connect()
    rows = conn.execute(
        """SELECT agent, operation, case_id, model_name, score
           FROM results ORDER BY agent, operation, case_id, model_name"""
    ).fetchall()
    conn.close()

    cases = {}
    for r in rows:
        key = (r["agent"], r["operation"], r["case_id"])
        cases.setdefault(key, {"agent": r["agent"], "operation": r["operation"],
                               "case_id": r["case_id"], "scores": {}})
        cases[key]["scores"][r["model_name"]] = r["score"]
    return list(cases.values())


# ── Costs ────────────────────────────────────────────────────────────────────

def costs(run_id: int = None, group_by: str = "agent") -> list:
    """Cost in USD per `group_by`, using each result's model_name joined to
    the pricing effective at (or before) that result's created_at."""
    if group_by not in ("agent", "operation", "run_id", "model_name"):
        raise ValueError("group_by must be 'agent', 'operation', 'run_id', or 'model_name'")
    conn = connect()
    where = "WHERE r.run_id = ?" if run_id else ""
    params = (run_id,) if run_id else ()
    rows = conn.execute(
        f"""SELECT r.{group_by} AS name,
                   SUM(r.prompt_tokens / 1000000.0 * COALESCE(p.price_per_million_prompt, 0)
                       + r.completion_tokens / 1000000.0 * COALESCE(p.price_per_million_completion, 0)) AS cost_usd,
                   SUM(r.total_tokens) AS total_tokens,
                   COUNT(*) AS n
            FROM results r
            LEFT JOIN model_pricing p
                   ON p.model_name = r.model_name
                  AND p.effective_from = (
                        SELECT MAX(p2.effective_from) FROM model_pricing p2
                        WHERE p2.model_name = r.model_name AND p2.effective_from <= r.created_at
                  )
            {where}
            GROUP BY r.{group_by} ORDER BY cost_usd DESC""",
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── Retention ────────────────────────────────────────────────────────────────

def prune_runs_older_than(days: int) -> int:
    """Deletes runs (and their results) older than `days`. Not run
    automatically — call it yourself when you actually want to prune."""
    conn = connect()
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    old_ids = [row["id"] for row in
               conn.execute("SELECT id FROM runs WHERE started_at < ?", (cutoff_iso,)).fetchall()]
    for rid in old_ids:
        conn.execute("DELETE FROM results WHERE run_id = ?", (rid,))
        conn.execute("DELETE FROM runs WHERE id = ?", (rid,))
    conn.commit()
    conn.close()
    return len(old_ids)
