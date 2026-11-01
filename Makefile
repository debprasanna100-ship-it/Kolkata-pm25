# Kolkata PM2.5 - convenience targets
# Windows users: these work in Git Bash / WSL, or just run the python commands directly.

PY ?= python
export PYTHONPATH := src

.PHONY: help install build train explain app all test clean

help:
	@echo "make install   install core + dev dependencies"
	@echo "make build     assemble the dataset (demo mode)"
	@echo "make train     train + evaluate all horizons"
	@echo "make explain   SHAP / permutation + source proxies"
	@echo "make all       build -> train -> explain"
	@echo "make app       launch the dashboard"
	@echo "make test      unit tests (pytest) + dashboard smoke test"
	@echo "make clean     remove generated data and artefacts"

install:
	$(PY) -m pip install -r requirements.txt

build:
	$(PY) -m pm25.cli build --mode demo

train:
	$(PY) -m pm25.cli train

explain:
	$(PY) -m pm25.cli explain

all:
	$(PY) -m pm25.cli all

app:
	$(PY) -m pm25.cli app

test:
	$(PY) -m pytest tests -q
	$(PY) tests/smoke_dashboard.py

clean:
	rm -rf data/processed artifacts
	find . -name "__pycache__" -type d -exec rm -rf {} +
