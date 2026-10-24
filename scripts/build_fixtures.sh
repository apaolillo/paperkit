#!/bin/sh
# Build the fixture papers in tests/papers and check that each one ends the
# way it is meant to. This needs a TeX installation, so run it inside the
# paperkit image (`paperkit shell`) or on a host that has one; the unit suite
# never builds anything.
#
# PAPERKIT=/path/to/paperkit ./scripts/build_fixtures.sh
set -e

paperkit_bin=${PAPERKIT:-paperkit}
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
    (cd "${papers_dir}/${paper}" && "${paperkit_bin}" build --no-docker "$@" >"${papers_dir}/${paper}/build.out" 2>&1)
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

# Clean papers build and pass their checks.
expect minimal 0
expect acmart 0
# This one trips every warning-level check and goes over its page limit, which
# is not an error by itself, but is one under --strict.
expect warnings 0
expect warnings 1 --strict

if [ "${failures}" -ne 0 ]; then
    echo "${failures} fixture(s) did not end as expected" >&2
    exit 1
fi
echo "all fixtures built as expected"
