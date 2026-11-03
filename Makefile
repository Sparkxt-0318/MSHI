# MSHI v3 — every target calls the single entry point `python -m mshi.run`.
# The reference virtualenv if present (`make env`), otherwise the active interpreter (e.g. the conda
# environment from environment.yml). Override with `make PY=/path/to/python ...`.
PY ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python)

.PHONY: all data analysis features clean-test repro phase2 smoke test list env lock

all:            ## every stage, in order (fetch -> sites -> features -> locked test re-run -> reproduction checks)
	$(PY) -m mshi.run --stage all

data:           ## pinned sources + COSORE annual + site build (no gridded features)
	$(PY) -m mshi.run --stage fetch_srdb --stage fetch_cosore --stage fetch_naturalearth \
	    --stage cosore_annual --stage build_sites --stage repro_checks

analysis:       ## site tables for v3 analyses: restricted COSORE, geodesic distances, geographic continent
	$(PY) -m mshi.run --stage cosore_annual_analysis --stage build_sites_analysis

features:       ## WorldClim, SoilGrids, MODIS points, feature tables
	$(PY) -m mshi.run --stage fetch_worldclim --stage fetch_soilgrids --stage modis_points --stage features

clean-test:     ## hash-verified re-run of the locked Asia -> Europe test (never overwrites the locked result)
	$(PY) -m mshi.run --stage clean_test --stage repro_checks

repro:
	$(PY) -m mshi.run --stage repro_checks

phase2:         ## exploratory Phase-2 stages (they run only if the reproduction rows they build on passed)
	$(PY) -m mshi.run --stage repro_checks --stage europe_geo_sensitivity --stage features_analysis \
	    --stage transfer_matrix --stage within_continent

smoke:          ## 50-site smoke run into data/interim/smoke/
	$(PY) -m mshi.run --stage all --smoke

test:           ## regression tests fail if committed results are stale (run `make all` first after code changes)
	GIT_OPTIONAL_LOCKS=0 $(PY) -m pytest -q

list:
	$(PY) -m mshi.run --list

env:            ## create the reference virtualenv
	python3.13 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt

lock:
	uv pip freeze --python $(PY) > requirements-lock.txt
