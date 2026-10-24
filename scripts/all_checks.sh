#!/bin/sh
# Format, lint, type-check and test paperkit with the tool versions pinned
# in uv.lock. Formatters rewrite files in place: check `git status` after.
set -e

root_dir=$(readlink -e "$(dirname "$0")/..")
cd "${root_dir}"

echo "-- syncing the dev environment (uv.lock). --"
uv sync --locked --quiet
echo "-- check copyright headers. --"
./scripts/list_missing_copyright.sh
echo "-- running ruff (lint, with the safe fixes applied). --"
uv run ruff check --fix src tests
echo "-- running ruff format. --"
uv run ruff format src tests
echo "-- running mypy. --"
uv run mypy src
echo "-- running pytest. --"
uv run pytest -q tests
