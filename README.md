# LLM Operations Benchmark

Benchmarks the **LLM** powering each of the four agents in
`revinci-ai-agents-demo-bundle` (IT Ops, HR, Sales, Data Analysis) on two
underlying capabilities: turning a natural-language message into the right
tool call (query building), and using what a tool actually retrieved
correctly (RAG). Each agent is tested against its **own** operations, built
around that agent's specific tools, parameters, and knowledge base, not one
generic list forced onto all four. Every case is a real `/chat` call to a
real running agent, graded by an independent judge LLM against a written
rubric.

## What's tested

Every agent is tested on the same 4-operation shape, populated with that
agent's own real tools, parameters, and data:

| # | Operation | Query building or RAG? |
|---|-----------|------------------------|
| 1 | **Search query formulation** (+ category filter selection, where the agent's search tool has one) | Query building |
| 2 | **Entity/parameter extraction for structured calls** | Query building |
| 3 | **Grounded generation from retrieval** | RAG |
| 4 | **No-match / low-relevance handling** | RAG |

**4 agents × 4 operations × 3 cases = 48 cases total.**

- **Query building** — the right search terms, the right category/filter,
  the right specific entity (a lead, a segment, a service, a location)
  resolved from a partial or informal reference, and any specific
  sub-parameter (a runbook id chained from a search result, a specific
  month, a process type) extracted correctly.
- **RAG** — the final answer stays grounded in retrieved content (no
  invented figures, names, or steps), and when nothing relevant is found,
  the agent says so rather than force-fitting a weak match or guessing.

### What's tested per agent

- **IT Ops** — `search_knowledge_base(query)` has no category filter, so
  operation 1 tests query specificity only. Operation 2 tests picking the
  right ticket `category` (from real categories like Email, Network, Print)
  and the right `service` key (vpn, email, software_center, intranet,
  identity) for a status check.
- **HR** — `search_hr_policy(query, category)` has a real category filter
  (Leave, Benefits, Conduct, Compensation, General). Operation 2 tests
  resolving the right `process` key (e.g. `onboarding`) plus correct
  subject/date/employment-type, and passing a real location to
  `get_location_guidelines`.
- **Sales** — `search_playbook(query, category)` has a real category filter
  (ICP, Pricing, Competitive, etc.). Operation 2 tests fuzzy-resolving a
  partial lead name (e.g. "Helio" → Helio Freight) and picking the correct
  `sequence` type matching the actual situation (trial-activation vs
  inbound-demo vs nurture).
- **Data Analysis** — `search_analytics_kb(query, category)` has a real
  category filter (Methodology, Reporting, Limitations, etc.). Operation 2
  tests fuzzy-resolving a segment name and correctly parsing a specific
  period (e.g. "back in July" → `2026-07`) rather than always defaulting to
  the latest month.

## End-to-end flow

`llm-operations-benchmark` (this project) and `revinci-ai-agents-demo-bundle`
(the four live agents) are separate codebases with no code-level import
between them. The only connection is a URL and a JSON contract over plain
HTTP — the same `/chat` endpoint the demo bundle's own UI calls
(`config.py`'s `AGENTS` dict maps agent name → `http://localhost:810X`).

One case runs like this:

1. **Load the case** — `runner.load_datasets()` reads every `.json` under
   `datasets/<agent>/`. Each file names its `agent` and `operation` once at
   the top; each case has an `id`, a `message` (or `messages` for a
   multi-turn case), and a `rubric`.
2. **Send it** — `agent_client.send(agent, message)` does one
   `requests.post(f"{url}/chat", json={"session_id": ..., "message": ...})`
   to that agent's real, running server.
3. **Inside the agent (its own process, its own LLM)** — the agent decides
   which tool to call and with what parameters (query building), executes
   the tool against its real knowledge base or demo state, then generates a
   natural-language reply grounded in whatever was retrieved (RAG). None of
   this is visible to the benchmark — only the final `/chat` JSON reply is
   (`response`, `model`, `prompt_tokens`, `completion_tokens`,
   `total_tokens`, `response_time_ms`).
4. **Grade it** — `runner.py` hands the original message, the case's
   `rubric`, and the agent's `response` text to
   `judge.rubric_score(input, rubric, actual)`, which sends one prompt to
   the independent judge LLM asking it to score 0.0–1.0 against the rubric
   and return `{"score": ..., "reasoning": ...}` as JSON. Query-building
   correctness (operations 1–2) is graded indirectly this way — the judge
   never sees the actual tool call, only whether the final answer reflects
   the right resolved entity/category/date.
5. **Store it** — `run_benchmark.py` writes each scored case straight into
   `benchmark.db` as it completes (not batched at the end, so a crash
   partway through a run doesn't lose the cases already scored), then once
   the full run finishes, `report.py` also saves a point-in-time snapshot to
   `results/raw_<timestamp>.json` and `results/summary_<timestamp>.csv`.

## Grading

Every case is graded by the independent judge LLM against a written rubric
(`judge.rubric_score()`) — plain English, e.g. *"Names only customers that
are actually in the retrieved approved reference list for fintech... does
not invent a customer name or outcome figure not in the retrieved
content."* There's no string-matching: the judge reads the input, the
rubric, and the answer together, like a human grader would.

**The judge must never be one of the agents' own underlying candidate
models** — configured once in `models.json`. The default judge is Gemini
(`gemini` provider) — set `GEMINI_API_KEY` in `.env`. Chosen specifically
because the 3 models being compared (see below) are Azure GPT-4o, Claude,
and Gemini — Gemini judges the other two with full independence, and only
judges its own family's output for the Gemini run (an accepted, documented
gap).

## Setup

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env          # fill in the judge model's API key
    copy models.example.json models.json   # pick/confirm the judge model

## Comparing 3 models — Azure GPT-4o vs. Claude vs. Gemini

The demo bundle's agents can run on any of 3 providers via `LLM_PROVIDER` in
*its own* `.env` (`revinci-ai-agents-demo-bundle/.env`, not this project's) —
see `shared/llm.py` there. To compare all 3:

    # In revinci-ai-agents-demo-bundle/.env, set LLM_PROVIDER=azure_openai
    # Restart all 4 agents, then:
    cd llm-operations-benchmark && python run_benchmark.py

    # Set LLM_PROVIDER=anthropic in the demo bundle's .env, restart all 4 agents:
    python run_benchmark.py

    # Set LLM_PROVIDER=gemini in the demo bundle's .env, restart all 4 agents:
    python run_benchmark.py

Each run is stored as a separate row in `benchmark.db` — `model_name` per
result records which model actually answered, so nothing needs to be
labeled by hand. Then:

    python rankings.py --by model --all-time   # which model actually scored best, overall
    python costs.py --by model --all-time      # $ spent per model across all 3 runs
    python compare_models.py                   # per-query: how each model scored on the SAME question

## Running it

All four agents must already be running (see the demo bundle's own README):

    localhost:8101  it-ops
    localhost:8102  hr
    localhost:8103  sales
    localhost:8104  data-analysis

Then:

    python run_benchmark.py

This checks all four are healthy, resets their demo state, runs all 48 cases
(4 operations x 4 agents x 3 cases), prints a score matrix, and saves
`results/raw_<timestamp>.json` (every case's full grade) and
`results/summary_<timestamp>.csv` (the aggregate table).

Skip the reset with `python run_benchmark.py --no-reset` if you want to
benchmark against whatever demo state is already there.

Every run is also stored permanently in `benchmark.db` (SQLite). Before
rankings/SLA/cost numbers mean anything, seed the reference data once:

    copy pricing.example.json pricing.json         # edit with real rates
    copy sla_targets.example.json sla_targets.json # edit with real targets
    python seed_reference_data.py

Then, any time after a run:

    python rankings.py              # agent leaderboard for the latest run
    python rankings.py --all-time   # leaderboard across every run ever stored
    python sla_check.py             # any SLA breached? (exits non-zero if so)
    python costs.py                 # $ spent, by agent, for the latest run

All three accept `--run <id>` to inspect a specific past run, and
`rankings.py`/`costs.py` accept `--by operation` or `--by model` to break
down differently.

## Comparing before vs. after a change

Run the benchmark, change something (a prompt, a rubric weight, the model an
agent runs on), run it again, then:

    python compare_runs.py

Diffs the two most recent saved runs and flags any operation/agent pair that
moved 15+ points either way. Pass two specific CSVs to compare non-adjacent
runs: `python compare_runs.py results/summary_A.csv results/summary_B.csv`.

## Data storage

Everything durable lives in one SQLite file, `benchmark.db` — one file, one
schema, four tables:

```
runs
  id              INTEGER PRIMARY KEY
  started_at      TEXT      -- ISO timestamp
  finished_at     TEXT
  judge_name      TEXT      -- from models.json's judge.name
  judge_model     TEXT      -- from models.json's judge.model
  notes           TEXT      -- optional, e.g. "after prompt tweak for Sales"

results
  id                INTEGER PRIMARY KEY
  run_id            INTEGER   REFERENCES runs(id)
  agent             TEXT      -- it-ops | hr | sales | data-analysis
  operation         TEXT
  case_id           TEXT
  score             REAL      -- 0.0-1.0, from the judge
  reasoning         TEXT      -- judge's explanation
  prompt_tokens     INTEGER
  completion_tokens INTEGER
  total_tokens      INTEGER
  response_time_ms  INTEGER
  model_name        TEXT      -- which underlying model the agent reported (ChatResponse.model)
  created_at        TEXT

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
Compute it on read, always. Each case's result is written to SQLite
immediately after it's scored, one row at a time, not batched at the end.

**Rankings** — `SELECT agent, AVG(score) FROM results WHERE run_id = ? GROUP BY agent ORDER BY 2 DESC`
for one run, or drop the `run_id` filter and group by week/month for a trend
over time. Same query shape whether ranking agents or the underlying
model — the schema doesn't hardcode "agent" as the only rankable thing,
`agent` and `model_name` are both just columns.

**SLAs** — for each `sla_targets` row, compare it against the matching
`results` rows (`accuracy` → `AVG(score)`, `response_time_ms` → `AVG`),
flag a breach when the comparison fails.

**Costs** — `cost = (prompt_tokens/1e6 * price_per_million_prompt) + (completion_tokens/1e6 * price_per_million_completion)`,
joined from `results.model_name` to `model_pricing.model_name`, using
whichever pricing row's `effective_from` is closest to (but not after) that
result's `created_at` — so an old result's cost is priced at the rate that
was actually in effect when it ran, not today's rate.

## Files

    config.py                  loads the judge model + the four agent URLs
    agent_client.py             talks to the four agents' /health, /chat, /demo/reset
    judge.py                    grading logic (judge-scored rubric, exact/semantic match, code tests)
    providers.py                 one call_model() entry point across judge/candidate providers
    runner.py                    runs every dataset's cases and grades each reply
    report.py                     aggregates results into the score matrix + CSV
    run_benchmark.py               CLI entry point — also writes every result to benchmark.db
    compare_runs.py                 diffs two saved CSV runs, flags regressions/improvements
    compare_models.py                per-query, side-by-side score across every candidate model
    db.py                             SQLite schema + insert/query helpers
    seed_reference_data.py             loads pricing.json + sla_targets.json into benchmark.db
    rankings.py                         agent/operation/model leaderboard, from stored history
    sla_check.py                         breach report against sla_targets, exits non-zero on breach
    costs.py                              $ spent, from stored history
    datasets/<agent>/*.json                 4 operations per agent, 3 cases each (48 total)

## Extending it

Add a case to any `datasets/<agent>/*.json` file, or a new operation as a
new file under the right agent's folder — `runner.py` picks up every `.json`
file under `datasets/` automatically (recursively). Each dataset file names
its `agent` and `operation` once at the top; each case inside needs `id`,
and either `message` (single turn) or `messages` (a list, sent in order on
one session — use this when the test needs to create something and then act
on it in a second turn), plus `rubric` describing what a correct reply
looks like.

Onboarding a whole new agent needs two things: its URL added to `AGENTS` in
`config.py`, and real dataset files under a new `datasets/<agent>/` folder,
grounded in that agent's actual tools, parameters, and data.
