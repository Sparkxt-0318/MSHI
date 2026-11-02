# MSHI v3 — every target calls the single entry point `python -m mshi.run`.
PY ?= .venv/bin/python

.PHONY: all data features clean-test repro smoke test list env lock

all:            ## every stage, in order (fetch -> sites -> features -> locked test re-run -> reproduction checks)
	$(PY) -m mshi.run --stage all

data:           ## pinned sources + COSORE annual + site build (no gridded features)
	$(PY) -m mshi.run --stage fetch_srdb --stage fetch_cosore --stage fetch_naturalearth \
	    --stage cosore_annual --stage build_sites --stage repro_checks

features:       ## WorldClim, SoilGrids, MODIS points, feature tables
	$(PY) -m mshi.run --stage fetch_worldclim --stage fetch_soilgrids --stage modis_points --stage features

clean-test:     ## hash-verified re-run of the locked Asia -> Europe test (never overwrites the locked result)
	$(PY) -m mshi.run --stage clean_test --stage repro_checks

repro:
	$(PY) -m mshi.run --stage repro_checks

smoke:          ## 50-site smoke run into data/interim/smoke/
	$(PY) -m mshi.run --stage all --smoke

test:
	$(PY) -m pytest -q

list:
	$(PY) -m mshi.run --list

env:            ## create the reference virtualenv
	python3.13 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt

lock:
	uv pip freeze --python $(PY) > requirements-lock.txt
