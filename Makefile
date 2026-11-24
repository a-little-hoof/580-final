PYTHON ?= python3
BUILD_PYTHON ?= .venv/bin/python

.PHONY: test test-agent test-validators test-traces build-env wheel analysis-env analyze report

test: test-agent test-validators test-traces

test-agent:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

test-validators:
	$(PYTHON) -m unittest discover -s study/controlled/tests -p 'test_*.py' -v

test-traces:
	$(PYTHON) -m unittest discover -s study/task0 -p 'test_*.py' -v

build-env:
	$(PYTHON) -m venv .venv
	$(BUILD_PYTHON) -m pip install -r build-requirements.txt

wheel:
	$(BUILD_PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .

analysis-env:
	$(PYTHON) -m venv .venv
	$(BUILD_PYTHON) -m pip install -r analysis-requirements.txt

analyze:
	$(BUILD_PYTHON) study/controlled/analyze_results.py --freeze study/controlled/final/freeze.json --progress study/controlled/final/progress.json --out study/controlled/final/analysis
	$(BUILD_PYTHON) study/controlled/plot_results.py --analysis study/controlled/final/analysis/analysis.json --out report/figures

report:
	$(BUILD_PYTHON) report/build_pdf.py
