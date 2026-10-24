#!/bin/sh
# Format, lint, type-check and test paperkit with the tool versions pinned
# in uv.lock. The formatters rewrite files in place: check `git status`
# after. With --check nothing is modified and an unformatted file is an
# error instead, which is what CI runs.
set -e

fix=1
case "$1" in
    --check) fix=0 ;;
    "") ;;
    *)
        echo "usage: $(basename "$0") [--check]" >&2
        exit 2
        ;;
esac

root_dir=$(readlink -e "$(dirname "$0")/..")
cd "${root_dir}"

echo "-- syncing the dev environment (uv.lock). --"
uv sync --locked --quiet
echo "-- check copyright headers. --"
./scripts/list_missing_copyright.sh
if [ "${fix}" -eq 1 ]; then
    echo "-- running ruff (lint, with the safe fixes applied). --"
    uv run ruff check --fix src tests
    echo "-- running ruff format. --"
    uv run ruff format src tests
else
    echo "-- running ruff (lint). --"
    uv run ruff check src tests
    echo "-- running ruff format (check only). --"
    uv run ruff format --check src tests
fi
echo "-- running mypy. --"
uv run mypy src
echo "-- running pytest. --"
uv run pytest -q tests
