# LLM Operations Benchmark

Benchmarks each of the four agents in `revinci-ai-agents-demo-bundle`
(IT Ops, HR, Sales, Data Analysis) against **its own** operations — defined
per agent around that agent's specific query-building and RAG (retrieval-
augmented generation) mechanics, not one generic list forced onto all four.
See `BENCHMARK_PLAN.md` for what each operation is and why. Every case is a
real `/chat` call to a real running agent, graded by an independent judge
LLM.

## Setup

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env          # fill in the judge model's API key
    copy models.example.json models.json   # pick/confirm the judge model

The default judge is Gemini (`gemini` provider) — set `GEMINI_API_KEY` in
`.env`. Chosen specifically because the 3 models being compared (see below)
are Azure GPT-4o, Claude, and Gemini — Gemini judges the other two with full
independence, and only judges its own family's output for the Gemini run
(an accepted, documented gap — see `BENCHMARK_PLAN.md`).

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

## Running it

All four agents must already be running (see the demo bundle's own README):

    localhost:8101  it-ops
    localhost:8102  hr
    localhost:8103  sales
    localhost:8104  data-analysis

Then:

    python run_benchmark.py

This checks all four are healthy, resets their demo state, runs all 32 cases
(4 operations x 4 agents x 2 cases), prints a score matrix, and saves
`results/raw_<timestamp>.json` (every case's full grade) and
`results/summary_<timestamp>.csv` (the aggregate table).

Skip the reset with `python run_benchmark.py --no-reset` if you want to
benchmark against whatever demo state is already there.

Every run is also stored permanently in `benchmark.db` (SQLite) — see
`ARCHITECTURE.md` for the schema and why. Before rankings/SLA/cost numbers
mean anything, seed the reference data once:

    copy pricing.example.json pricing.json         # edit with real rates
    copy sla_targets.example.json sla_targets.json # edit with real targets
    python seed_reference_data.py

Then, any time after a run:

    python rankings.py              # agent leaderboard for the latest run
    python rankings.py --all-time   # leaderboard across every run ever stored
    python sla_check.py             # any SLA breached? (exits non-zero if so)
    python costs.py                 # $ spent, by agent, for the latest run

All three accept `--run <id>` to inspect a specific past run, and
`rankings.py`/`costs.py` accept `--by operation` to break down by operation
instead of agent.

## Comparing before vs. after a change

Run the benchmark, change something (a prompt, a rubric weight, the model an
agent runs on), run it again, then:

    python compare_runs.py

Diffs the two most recent saved runs and flags any operation/agent pair that
moved 15+ points either way. Pass two specific CSVs to compare non-adjacent
runs: `python compare_runs.py results/summary_A.csv results/summary_B.csv`.

## Files

    BENCHMARK_PLAN.md      the operations, what each tests, and why
    ARCHITECTURE.md          the storage design (SQLite schema, rankings/SLA/cost logic)
    config.py                  loads the judge model + the four agent URLs
    agent_client.py             talks to the four agents' /health, /chat, /demo/reset
    judge.py                    grading logic (judge-scored rubric, exact/semantic match, code tests)
    runner.py                    runs every dataset's cases and grades each reply
    report.py                     aggregates results into the score matrix + CSV
    run_benchmark.py               CLI entry point — also writes every result to benchmark.db
    compare_runs.py                 diffs two saved CSV runs, flags regressions/improvements
    db.py                            SQLite schema + insert/query helpers
    seed_reference_data.py            loads pricing.json + sla_targets.json into benchmark.db
    rankings.py                        agent/operation leaderboard, from stored history
    sla_check.py                        breach report against sla_targets, exits non-zero on breach
    costs.py                             $ spent, from stored history
    datasets/<agent>/*.json                4 operations per agent, 2 cases each (32 total)

## Extending it

Add a case to any `datasets/<agent>/*.json` file, or a new operation as a
new file under the right agent's folder — `runner.py` picks up every `.json`
file under `datasets/` automatically (recursively). Each dataset file names
its `agent` and `operation` once at the top; each case inside needs `id`,
`plan`, and either `message` (single turn) or `messages` (a list, sent in
order on one session — use this when the test needs to create something and
then act on it in a second turn), plus `rubric` describing what a correct
reply looks like.
