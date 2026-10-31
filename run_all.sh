#!/usr/bin/env bash
# One command: ingest (cached) -> build warehouse + checks -> tests -> report
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH=src
python -m fpa ingest "$@"
python -m fpa build
python -m pytest -q tests
python -m fpa report
