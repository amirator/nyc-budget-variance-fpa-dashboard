"""Single entry point: python -m fpa [all|ingest|build|report] [--refresh]"""
import argparse

from fpa import ingest, report, warehouse

ap = argparse.ArgumentParser(prog="fpa")
ap.add_argument("step", nargs="?", default="all", choices=["all", "ingest", "build", "report"])
ap.add_argument("--refresh", action="store_true", help="re-download source data even if cached")
a = ap.parse_args()
if a.step in ("all", "ingest"):
    ingest.load(a.refresh)
if a.step in ("all", "build"):
    warehouse.build()
if a.step in ("all", "report"):
    report.main()
