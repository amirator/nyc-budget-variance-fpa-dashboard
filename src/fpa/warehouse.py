"""Build the DuckDB star schema and analytics tables by running sql/*.sql in order. Author: Amir Khan"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql"
DB_PATH = ROOT / "data" / "fpa.duckdb"


def build(db_path: Path = DB_PATH) -> list[tuple[str, int]]:
    con = duckdb.connect(str(db_path))
    for f in sorted(SQL_DIR.glob("*.sql")):
        con.execute(f.read_text())
        print(f"ran {f.name}", flush=True)
    checks = con.execute("select check_name, failing_rows from mart.dq_checks").fetchall()
    con.close()
    bad = [c for c in checks if c[1]]
    for name, n in checks:
        print(f"  [{'FAIL' if n else 'pass'}] {name}" + (f" ({n})" if n else ""))
    if bad:
        raise SystemExit(f"{len(bad)} warehouse check(s) failed")
    return checks


if __name__ == "__main__":
    build()
