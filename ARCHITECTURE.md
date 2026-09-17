# Benchmark Data Architecture — Plan

Goal: store and manage benchmark data — accuracy scores, **rankings**,
**SLAs**, and **costs** — durably across many runs, not just print one run's
results and discard them (which is all the current JSON/CSV output does).

## What's missing today

`agent_client.py` already receives everything needed from every `/chat`
call — `prompt_tokens`, `completion_tokens`, `total_tokens`,
`response_time_ms` — because the demo bundle's own `ChatResponse` returns
them. `runner.py` currently discards all of it and keeps only the reply
text and the judge's score. Nothing is stored between runs except two
timestamped files per run (`raw_*.json`, `summary_*.csv`) — there's no way
to ask "how has Sales trended over the last 10 runs" without manually
opening several files and doing the math by hand.

## Storage choice: SQLite, not more JSON files

- **Zero setup** — one file (`benchmark.db`), no server to run, fits how
  this project already works (no other service dependency).
- **Actually queryable** — "average score for Sales over the last 30 days"
  is one SQL query instead of writing a script to open N JSON files.
- **Still just a file** — easy to inspect (`sqlite3 benchmark.db`), easy to
  back up, easy to migrate to Postgres later if this ever needs to be
  shared across machines/people.

The existing `results/raw_*.json` and `summary_*.csv` outputs stay — they're
useful as a human-readable snapshot of one run — but `benchmark.db` becomes
the durable store everything else (rankings, SLAs, costs, trends) is
computed from.

## Schema

```
runs
  id              INTEGER PRIMARY KEY
  started_at      TEXT      -- ISO timestamp
  finished_at     TEXT
  judge_name      TEXT      -- from models.json's judge.name
  judge_model     TEXT      -- from models.json's judge.model
  notes           TEXT      -- optional, e.g. "after prompt tweak for Sales"

results
  id              INTEGER PRIMARY KEY
  run_id          INTEGER   REFERENCES runs(id)
  agent           TEXT      -- it-ops | hr | sales | data-analysis
  operation       TEXT
  case_id         TEXT
  plan            TEXT      -- basic | standard | advanced
  score           REAL      -- 0.0-1.0, from the judge
  reasoning       TEXT      -- judge's explanation
  prompt_tokens   INTEGER
  completion_tokens INTEGER
  total_tokens    INTEGER
  response_time_ms INTEGER
  model_name      TEXT      -- which underlying model the agent reported (ChatResponse.model)
  created_at      TEXT

model_pricing
  model_name                    TEXT PRIMARY KEY
  price_per_million_prompt      REAL   -- USD, matches how providers publish rates
  price_per_million_completion  REAL
  effective_from                TEXT   -- pricing changes over time; keep history, don't overwrite

sla_targets
  id              INTEGER PRIMARY KEY
  agent           TEXT      -- or NULL = applies to all agents
  operation       TEXT      -- or NULL = applies to all operations
  metric          TEXT      -- 'accuracy' | 'response_time_ms'
  comparison      TEXT      -- 'gte' | 'lte'
  target_value    REAL
  active          INTEGER   -- 1/0, so an old SLA can be retired without deleting history
```

**No separate "rankings" table.** A ranking is always a computed view over
`results` (e.g. `AVG(score) GROUP BY agent ORDER BY AVG(score) DESC`) —
storing it separately would let it go stale the moment new results come in.
Compute it on read, always.

## How each of the three things works

**Rankings** — `SELECT agent, AVG(score) FROM results WHERE run_id = ? GROUP BY agent ORDER BY 2 DESC`
for one run, or drop the `run_id` filter and group by week/month for a trend
over time. Same query shape whether ranking agents (today) or raw
underlying models (if that's ever added back as a comparison axis) — the
schema doesn't hardcode "agent" as the only rankable thing conceptually,
`agent` and `model_name` are both just columns.

**SLAs** — for each `sla_targets` row, compare it against the matching
`results` rows (`accuracy` → `AVG(score)`, `response_time_ms` → `AVG` or
`P95`), flag a breach when the comparison fails. A breach is a fact you can
query for ("show every SLA currently breached"), not something computed
once and forgotten.

**Costs** — `cost = (prompt_tokens/1e6 * price_per_million_prompt) + (completion_tokens/1e6 * price_per_million_completion)`,
joined from `results.model_name` to `model_pricing.model_name`. Summed per
run, per agent, or per operation. Pricing lives in its own table (not
hardcoded in code) because prices change and old runs' costs shouldn't
silently recompute at a new price — `effective_from` lets you compute
"what did this cost at the time," not just "what would it cost today."

## What changes in the existing harness

- `agent_client.py` — already returns everything needed; no change.
- `runner.py` — capture `prompt_tokens`/`completion_tokens`/`total_tokens`/
  `response_time_ms`/`model` from the agent's response into each result
  dict (currently dropped).
- `report.py` — add a `db.py` sibling that opens `benchmark.db`, creates the
  schema on first run, and inserts one `runs` row + N `results` rows per
  benchmark run. `report.py`'s existing CSV/JSON output stays as-is.
- New: `rankings.py` (print/export the ranking queries), `sla_check.py`
  (evaluate `sla_targets` against recent results, print breaches),
  `costs.py` (print cost breakdown per run/agent/operation).
- `models.json` gains pricing info per model (or a separate
  `pricing.json` seeding the `model_pricing` table).

## Rollout

1. Add `db.py` (schema creation + insert helpers) — additive, doesn't touch
   existing JSON/CSV output.
2. Wire `runner.py`/`run_benchmark.py` to also write to `benchmark.db`.
3. Add the three read-side scripts (`rankings.py`, `sla_check.py`, `costs.py`).
4. Seed `model_pricing` and `sla_targets` with real values (needs your
   input — see below).

## Open questions — need your input before implementing

- **Pricing source**: hardcode known per-model $/1K-token rates in
  `pricing.json`, or is there a billing API (the demo bundle's own
  `shared/billing/client.py` posts usage somewhere — same target?) this
  should pull from instead?
- **SLA targets**: what should the actual numbers be? (e.g. "accuracy ≥ 90%
  per operation," "response time ≤ 8000ms") — these need to come from you
  or your lead, not invented.
- **Retention**: keep every run forever, or prune after N days/runs?
