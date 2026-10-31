all:
	./run_all.sh
test:
	PYTHONPATH=src python -m pytest -q tests
refresh:
	./run_all.sh --refresh
.PHONY: all test refresh
