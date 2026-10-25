# Roadmap

Typst support shipped with 0.2.0, as did the examples. What remains on the
horizon, roughly in the order it would pay off:

- **A shared TeX Live image per pin.** Every project that pins the same
  `[texlive]` snapshot installs the same TeX Live into an image of its own,
  and so does CI. An image keyed by the `[texlive]` table, shared across
  projects and reused by the fixtures workflow, builds it once.
- **Section page budgets.** Some calls limit sections, not the whole
  document: a proposal's parts, a CV, an appendix. A `[page_limits]
  sections` table, measured from the headings the way `before_refs` is,
  would replace the counters such projects write by hand.
- **paperkit in a paper's own CI.** With `--strict` and exit codes that
  follow the verdict, a documented workflow for a paper repository, or a
  reusable action, that runs `paperkit build --strict` on every push.
- **`paperkit watch`**: rebuild when a source changes, for the writing loop.
- **A double-blind check**: author names, affiliations, funding lines and
  self-identifying phrasing in a submission declared anonymous. Same family
  as the other desk-reject checks; the care is in not crying wolf.
- **Title and abstract export for Typst papers**, which needs a convention for
  where a template keeps them; `typst query` can read metadata a paper
  exposes, so a small `#metadata` block may be enough.
- **Typst profiles for the other venues** (`typst-lncs`, `typst-usenix`), when
  a Universe template and a paper that uses it come together; the USENIX
  example then also gets the real style file.
