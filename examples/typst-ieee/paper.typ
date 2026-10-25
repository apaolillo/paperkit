// The paper, in Typst Universe's IEEE template. The import names the
// package and its version; the configuration declares the same so the image
// carries it and builds need no network.
#import "@preview/charged-ieee:0.1.4": ieee

#show: ieee.with(
  title: [A Paper in the IEEE Format, in Typst],
  abstract: include "content/00-abstract.typ",
  authors: (
    (
      name: "A. Author",
      organization: [An Institution],
      location: [A City, A Country],
      email: "author@example.org",
    ),
    (
      name: "B. Author",
      organization: [Another Institution],
      location: [Another City, Another Country],
      email: "b.author@example.org",
    ),
  ),
  index-terms: ("Reproducible builds", "Pre-submission checks", "Typst"),
  bibliography: bibliography("references.bib"),
)

#include "content/10-introduction.typ"
#include "content/20-approach.typ"
#include "content/80-conclusion.typ"

#heading(numbering: none)[Acknowledgment]
#include "content/90-acknowledgment.typ"
