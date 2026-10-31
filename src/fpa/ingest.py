"""Download NYC Open Data Expense Budget datasets into DuckDB (raw schema).

* mwzb-yiwb  Expense Budget (line level, ~1.1M rows, FY2017-FY2027, 3 publications per FY)
* 39g5-gbp3  Expense Budget Funding - All Source (unit-of-appropriation level, by funding source)

Raw data is cached as parquet under data/raw/ and is not committed to git.
Author: Amir Khan
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "fpa.duckdb"
DATASETS = {
    "expense_budget": "https://data.cityofnewyork.us/resource/mwzb-yiwb.json",
    "expense_funding": "https://data.cityofnewyork.us/resource/39g5-gbp3.json",
}
PAGE = 50_000


def page_params(offset: int, page: int = PAGE) -> dict:
    return {"$limit": page, "$offset": offset, "$order": ":id"}


def fetch(url: str, page: int = PAGE) -> pd.DataFrame:
    s, frames, offset = requests.Session(), [], 0
    while True:
        for attempt in range(5):
            try:
                r = s.get(url, params=page_params(offset, page), timeout=300)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        rows = r.json()
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        offset += len(rows)
        print(f"  {offset:,}", flush=True)
        if len(rows) < page:
            break
    return pd.concat(frames, ignore_index=True).astype("string")


def load(refresh: bool = False, db_path: Path = DB_PATH) -> dict[str, int]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("create schema if not exists raw")
    out = {}
    for name, url in DATASETS.items():
        pq = RAW_DIR / f"{name}.parquet"
        if refresh or not pq.exists():
            print(f"downloading {name}", flush=True)
            fetch(url).to_parquet(pq, index=False)
        con.execute(f"create or replace table raw.{name} as select * from read_parquet('{pq.as_posix()}')")
        out[name] = con.execute(f"select count(*) from raw.{name}").fetchone()[0]
        print(f"raw.{name}: {out[name]:,}", flush=True)
    con.close()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    load(ap.parse_args().refresh)
