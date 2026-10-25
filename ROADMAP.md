# Roadmap

Typst support shipped with 0.2.0. What remains on the horizon:

- **Typst profiles for the other venues** (`typst-lncs`, `typst-usenix`), when
  a Universe template and a paper that uses it come together.
- **Title and abstract export for Typst papers**, which needs a convention for
  where a template keeps them; `typst query` can read metadata a paper
  exposes, so a small `#metadata` block may be enough.
- **A build cache for TeX Live images** keyed by the `[texlive]` table, so two
  projects with the same pin share one image.
