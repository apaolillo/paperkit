// The paper, in Typst Universe's ACM template. The import names the package
// and its version; the configuration declares the same so the image carries
// it. The fonts the template sets travel with the paper, under fonts/.
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
    (
      name: "B. Author",
      email: "b.author@example.org",
      affiliation: (
        institution: "Another Institution",
        city: "Another City",
        country: "Another Country",
      ),
    ),
  ),
  abstract: include "content/00-abstract.typ",
  keywords: ("Reproducible builds", "Pre-submission checks", "Typst"),
)

#include "content/10-introduction.typ"
#include "content/20-approach.typ"
#include "content/80-conclusion.typ"

#heading(numbering: none)[Acknowledgments]
#include "content/90-acknowledgments.typ"

#bibliography("references.bib")
