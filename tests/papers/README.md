# Fixture papers

Small, self-contained projects paperkit can build, used to exercise the parts
of it that a unit test cannot reach: a real engine run, a real bibliography,
and the checks reading a real PDF.

| Paper | What it is for |
|---|---|
| `minimal` | The smallest thing paperkit can build: one file, no bibliography. Everything clean. |
| `acmart` | A realistic venue class with a bibliography and a citation. Everything clean. |
| `warnings` | Trips every warning-level check and goes over its page limit, without a single error. |

`warnings` is the interesting one. It contains, on purpose: a line with
trailing whitespace, a file with a non-ASCII character and no final newline, a
bibliography entry nothing cites, an overfull line, and a page limit of 1 for
a paper of 2 pages. None of that is an error, so `paperkit build` exits 0 and
`paperkit build --strict` exits 1.

Build them all and check those outcomes:

```bash
./scripts/build_fixtures.sh            # needs TeX: run it in `paperkit shell`
PAPERKIT=.venv/bin/paperkit ./scripts/build_fixtures.sh
```

The unit suite never builds them, since it must run without TeX; it only
loads their configuration files. Build output stays out of git.
