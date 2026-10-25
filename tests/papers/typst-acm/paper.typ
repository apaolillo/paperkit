#import "@preview/faithful-acmart:0.2.0": *

#show: acmart.with(
  format: "sigconf",
  title: "A Paper in the ACM Format, in Typst",
  authors: (
    (
      name: "A. Author",
      email: "author@example.org",
      affiliation: (
        institution: "An Institution",
        city: "A City",
        country: "A Country",
      ),
    ),
  ),
  abstract: [
    This paper exercises an ACM template from Typst Universe, a bibliography
    and a citation, through paperkit.
  ],
  keywords: ("Reproducible builds", "Typst"),
)

= Introduction

Reproducible builds matter @reproducible.

#bibliography("refs.bib")
