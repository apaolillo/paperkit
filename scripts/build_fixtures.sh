#!/bin/sh
# Build the fixture papers in tests/papers and check that each one ends the
# way it is meant to. By default the builds run on this host, which needs a
# TeX installation; with --docker they go through the image like a user's
# builds do, which only needs Docker. The unit suite never builds anything.
#
# PAPERKIT=/path/to/paperkit ./scripts/build_fixtures.sh [--docker]
set -e

paperkit_bin=${PAPERKIT:-paperkit}
# Builds run from inside each fixture directory, so a relative PAPERKIT such
# as .venv/bin/paperkit must be made absolute here; a bare name stays a PATH
# lookup.
case "${paperkit_bin}" in
    */*)
        paperkit_bin=$(readlink -e "${paperkit_bin}") || {
            echo "PAPERKIT=${PAPERKIT}: no such file" >&2
            exit 2
        }
        ;;
esac
where="--no-docker"
case "$1" in
    --docker) where="" ;;
    "") ;;
    *)
        echo "usage: $(basename "$0") [--docker]" >&2
        exit 2
        ;;
esac
root_dir=$(readlink -e "$(dirname "$0")/..")
papers_dir="${root_dir}/tests/papers"
failures=0

# expect <paper> <wanted exit status> [extra paperkit arguments...]
expect() {
    paper=$1
    want=$2
    shift 2
    printf '%-28s' "${paper} $*"
    set +e
    # shellcheck disable=SC2086
    (cd "${papers_dir}/${paper}" && "${paperkit_bin}" build ${where} "$@" >"${papers_dir}/${paper}/build.out" 2>&1)
    got=$?
    set -e
    if [ "${got}" -eq "${want}" ]; then
        echo "exit ${got}, as expected"
    else
        echo "exit ${got}, expected ${want}"
        sed 's/\x1b\[[0-9;]*m//g' "${papers_dir}/${paper}/build.out" | tail -20
        failures=$((failures + 1))
    fi
}

# Clean papers build and pass their checks. Inside the image every tool is
# present, so there they must pass with nothing to report at all.
expect minimal 0
expect acmart 0
expect ieee 0
if [ -z "${where}" ]; then
    expect minimal 0 --strict
    expect acmart 0 --strict
    expect ieee 0 --strict
fi
# This one trips every warning-level check and goes over its page limit, which
# is not an error by itself, but is one under --strict.
expect warnings 0
expect warnings 1 --strict

if [ "${failures}" -ne 0 ]; then
    echo "${failures} fixture(s) did not end as expected" >&2
    exit 1
fi
echo "all fixtures built as expected"
