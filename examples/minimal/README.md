# The minimal example

One file, no bibliography, a configuration that says three things. This is
where to start to see what a build and its report look like before copying
one of the venue examples.

```
paper.tex          the whole paper
.paperkit.toml     three keys; the defaults do the rest
```

## Try it

```bash
paperkit build                # in Docker; the first run builds the image
paperkit build --no-docker    # with the TeX Live installed on this machine
paperkit check                # the checks again, on the existing build output
```

## What it shows

- **The report.** After the build, one row per check: LaTeX errors and
  warnings, boxes, fonts, the three source checks, the page counts. Each
  row is clean, which is what a check that ran and found nothing looks like;
  a check that could not run says "skipped" instead, since not running is
  not passing.
- **The environment line.** The report names the TeX Live that built the
  PDF, read from the log, and compares it with what the configuration
  expects. Built on the host, the two can differ, and the report says so.
- **Defaults.** Every key is optional. The file sets the main file's name,
  that there are no sections and no bibliography, and the `base` profile;
  pdflatex, three passes, Docker and every check are the defaults.

## Next

`examples/acm` is the same idea at the size of a real paper: sections in
directories, two targets, a pinned TeX Live, page limits and an archive.
