.PHONY: help install test lint format serve build docker clean

USER ?= your-username

help:
	@echo "install   Install the package with dev dependencies"
	@echo "test      Run the test suite"
	@echo "lint      Run ruff"
	@echo "format    Auto-fix imports and formatting where possible"
	@echo "serve     Run the web UI on http://127.0.0.1:8000"
	@echo "build     Build a sample 300-location map (make build USER=name)"
	@echo "docker    Build and run with Docker Compose"

install:
	python -m pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

format:
	ruff check . --fix

serve:
	been2guessr serve

build:
	been2guessr build "$(USER)" -n 300 -o output/map.json --csv

docker:
	docker compose up --build

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info output
