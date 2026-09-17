"""
Quick browser for benchmark.db - dumps a table or runs a raw SQL query.

    python view_db.py                        list tables
    python view_db.py runs                    dump the runs table
    python view_db.py results --run 3         dump results for run #3
    python view_db.py results --limit 10      first 10 rows of results
    python view_db.py --sql "SELECT ..."      run any raw SQL query
"""

import sys

import db

_TABLES = ("runs", "results", "model_pricing", "sla_targets")


def _print_rows(rows: list) -> None:
    if not rows:
        print("(no rows)")
        return
    cols = rows[0].keys()
    widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
    widths = {c: min(w, 40) for c, w in widths.items()}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r[c])[:40].ljust(widths[c]) for c in cols))
    print(f"\n{len(rows)} row(s)")


def main():
    args = sys.argv[1:]
    conn = db.connect()

    if "--sql" in args:
        query = args[args.index("--sql") + 1]
        rows = conn.execute(query).fetchall()
        _print_rows([dict(r) for r in rows])
        conn.close()
        return

    if not args:
        print("Tables:", ", ".join(_TABLES))
        print("\nUsage: python view_db.py <table> [--run N] [--limit N]")
        conn.close()
        return

    table = args[0]
    if table not in _TABLES:
        sys.exit(f"Unknown table {table!r}. Choose from: {', '.join(_TABLES)}")

    where, params = "", ()
    if "--run" in args and table == "results":
        where = "WHERE run_id = ?"
        params = (int(args[args.index("--run") + 1]),)

    limit = ""
    if "--limit" in args:
        limit = f" LIMIT {int(args[args.index('--limit') + 1])}"

    rows = conn.execute(f"SELECT * FROM {table} {where} ORDER BY id{limit}", params).fetchall()
    _print_rows([dict(r) for r in rows])
    conn.close()


if __name__ == "__main__":
    main()
