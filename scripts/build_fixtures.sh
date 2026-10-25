#!/bin/sh
# Build the fixture papers in tests/papers and the examples in examples/, and
# check that each one ends the way it is meant to. By default the builds run
# on this host, which needs a TeX installation; with --docker they go through
# the image like a user's builds do, which only needs Docker. The unit suite
# never builds anything.
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
examples_dir="${root_dir}/examples"
failures=0

# expect_in <directory> <paper> <wanted exit status> [extra paperkit arguments...]
expect_in() {
    dir=$1
    paper=$2
    want=$3
    shift 3
    printf '%-36s' "$(basename "${dir}")/${paper} $*"
    set +e
    # shellcheck disable=SC2086
    (cd "${dir}/${paper}" && "${paperkit_bin}" build ${where} "$@" >"${dir}/${paper}/build.out" 2>&1)
    got=$?
    set -e
    if [ "${got}" -eq "${want}" ]; then
        echo "exit ${got}, as expected"
    else
        echo "exit ${got}, expected ${want}"
        sed 's/\x1b\[[0-9;]*m//g' "${dir}/${paper}/build.out" | tail -20
        failures=$((failures + 1))
    fi
}

# expect <fixture paper> <wanted exit status> [extra paperkit arguments...]
expect() {
    expect_in "${papers_dir}" "$@"
}

# Clean papers build and pass their checks. Inside the image every tool is
# present, so there they must pass with nothing to report at all.
expect minimal 0
expect acmart 0
expect ieee 0
expect lncs 0
if [ -z "${where}" ]; then
    expect minimal 0 --strict
    expect acmart 0 --strict
    expect ieee 0 --strict
    expect lncs 0 --strict
fi
# This one trips every warning-level check and goes over its page limit, which
# is not an error by itself, but is one under --strict.
expect warnings 0
expect warnings 1 --strict
# Over its page budget only because the usenix profile counts the
# acknowledgments: the profile's one default, seen end to end.
expect usenix 0
expect usenix 1 --strict
# Typst: a plain document, and the IEEE and ACM templates from Universe.
# Those two import a package, declared in their config so the image carries
# it; on a host they download it once into typst's cache.
expect typst-minimal 0
expect typst-ieee 0
expect typst-acm 0
if [ -z "${where}" ]; then
    expect typst-minimal 0 --strict
    expect typst-ieee 0 --strict
    expect typst-acm 0 --strict
fi

# The examples are what a new user copies, so every one of them builds clean,
# and inside the image clean under --strict: not a warning to explain away.
# On a host the toolchain row warns that the build did not use the pinned
# environment, which is the one warning a host build is allowed.
for example_dir in "${examples_dir}"/*/; do
    example=$(basename "${example_dir}")
    expect_in "${examples_dir}" "${example}" 0
    if [ -z "${where}" ]; then
        expect_in "${examples_dir}" "${example}" 0 --strict
    fi
done

if [ "${failures}" -ne 0 ]; then
    echo "${failures} paper(s) did not end as expected" >&2
    exit 1
fi
echo "all fixtures and examples built as expected"
