"""
REST API wrapping the CLI tools (run_benchmark.py, rankings.py, sla_check.py,
costs.py) as HTTP endpoints, so a run can be triggered and its results
queried remotely instead of only from a terminal.

    uvicorn service:app --host 0.0.0.0 --port 8000

Then, e.g.:

    curl -X POST http://localhost:8000/runs
    curl http://localhost:8000/runs/1
    curl http://localhost:8000/rankings?by=model&all_time=true
    curl http://localhost:8000/sla-check
    curl http://localhost:8000/costs?by=operation

See Dockerfile to run this containerized.
"""

from fastapi import BackgroundTasks, FastAPI, HTTPException

import agent_client
import db
import report
from config import JUDGE
from rankings import _latest_run_id
from runner import load_datasets, run_all

app = FastAPI(title="LLM Operations Benchmark API")

_BY_MAP = {"agent": "agent", "operation": "operation", "model": "model_name"}


def _run_in_progress() -> bool:
    conn = db.connect()
    row = conn.execute(
        "SELECT id FROM runs WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row is not None


def _resolve_run_id(run_id: int | None, all_time: bool) -> int | None:
    """Same scoping rule the CLI tools use: an explicit run_id wins, then
    --all-time (None = no filter), else fall back to the latest run and
    error if there isn't one yet."""
    if run_id is not None:
        return run_id
    if all_time:
        return None
    latest = _latest_run_id()
    if latest is None:
        raise HTTPException(404, "No runs stored yet - trigger one with POST /runs first.")
    return latest


def _execute_benchmark(run_id: int, no_reset: bool) -> None:
    """Runs in a background thread (FastAPI/Starlette run sync background
    tasks off the event loop), so the POST /runs call that kicked it off
    doesn't block for the full run duration."""
    try:
        if not no_reset:
            agent_client.reset_all()
        datasets = load_datasets()
        results = []
        for r in run_all(datasets, verbose=True):
            db.insert_result(run_id, r)
            results.append(r)
        matrix = report.build_matrix(results)
        report.save(results, matrix)
    except Exception as e:
        db.fail_run(run_id, str(e))
        return
    db.finish_run(run_id)


@app.get("/health")
def health():
    """This service's own health, plus whether the 4 agents under test are
    reachable right now."""
    return {"status": "ok", "agents": agent_client.health_check_all()}


@app.post("/runs", status_code=202)
def start_run(background_tasks: BackgroundTasks, no_reset: bool = False):
    """Triggers a benchmark run in the background and returns immediately
    with the new run's id. Poll GET /runs/{run_id} for status."""
    if _run_in_progress():
        raise HTTPException(409, "A run is already in progress.")

    status = agent_client.health_check_all()
    if not all(status.values()):
        down = [n for n, ok in status.items() if not ok]
        raise HTTPException(503, f"Agent(s) not reachable: {', '.join(down)}")

    run_id = db.start_run(JUDGE.get("name", ""), JUDGE.get("model", ""))
    background_tasks.add_task(_execute_benchmark, run_id, no_reset)
    return {"run_id": run_id, "status": "started"}


@app.get("/runs/{run_id}")
def get_run(run_id: int):
    conn = db.connect()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "No such run.")

    result = dict(row)
    result["status"] = "finished" if result["finished_at"] else "running"
    if result["finished_at"]:
        result["rankings"] = db.rankings(run_id=run_id, group_by="agent")
    return result


@app.get("/rankings")
def get_rankings(by: str = "agent", run_id: int | None = None, all_time: bool = False):
    if by not in _BY_MAP:
        raise HTTPException(400, f"'by' must be one of: {', '.join(_BY_MAP)}")
    scoped = _resolve_run_id(run_id, all_time)
    return {
        "scope": f"run #{scoped}" if scoped else "all-time",
        "rankings": db.rankings(run_id=scoped, group_by=_BY_MAP[by]),
    }


@app.get("/sla-check")
def get_sla_check(run_id: int | None = None, all_time: bool = False):
    scoped = _resolve_run_id(run_id, all_time)
    rows = db.check_slas(run_id=scoped)
    return {
        "scope": f"run #{scoped}" if scoped else "all-time",
        "any_breach": any(r["breached"] for r in rows),
        "targets": rows,
    }


@app.get("/costs")
def get_costs(by: str = "agent", run_id: int | None = None, all_time: bool = False):
    if by not in _BY_MAP:
        raise HTTPException(400, f"'by' must be one of: {', '.join(_BY_MAP)}")
    scoped = _resolve_run_id(run_id, all_time)
    return {
        "scope": f"run #{scoped}" if scoped else "all-time",
        "costs": db.costs(run_id=scoped, group_by=_BY_MAP[by]),
    }
