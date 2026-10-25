#import "@preview/charged-ieee:0.1.4": ieee

#show: ieee.with(
  title: [A Paper in the IEEE Format, in Typst],
  abstract: [
    This paper exercises an IEEE template from Typst Universe, a bibliography
    and a citation, through paperkit.
  ],
  authors: (
    (
      name: "A. Author",
      organization: [An Institution],
      location: [A City, A Country],
      email: "author@example.org",
    ),
  ),
  index-terms: ("Reproducible builds", "Typst"),
  bibliography: bibliography("refs.bib"),
)

= Introduction

Reproducible builds matter @reproducible.
