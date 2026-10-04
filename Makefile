PY := .venv/bin/python

setup:
	python3 -m venv .venv && $(PY) -m pip install -r requirements.txt

packages:
	$(PY) -m src.fetch_packages

extract:
	$(PY) -m src.extract_banks

macro:
	$(PY) -m src.load_macro

banks:
	$(PY) -m src.load_banks

regression:
	$(PY) -m src.regression

all:
	$(PY) -m src.run_all

offline:
	$(PY) -m src.run_all --offline

test:
	$(PY) -m pytest -q

.PHONY: setup packages extract macro banks regression all offline test
