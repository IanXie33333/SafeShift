.PHONY: setup clean-data test lint

setup:
	uv sync --extra dev

clean-data:
	uv run python src/cleaning/clean_ita_data.py

test:
	uv run pytest

lint:
	uv run ruff check .
