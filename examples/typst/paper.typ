// The paper. Its sections live in content/, so this file sets the page and
// the text and names the pieces.
#set page(paper: "us-letter", margin: 1in, numbering: "1")
#set text(size: 11pt)
#set heading(numbering: "1.")
#set par(justify: true)

#align(center, text(17pt)[*A Paper in Typst*])
#align(center)[A. Author, An Institution \ B. Author, Another Institution]

#heading(numbering: none, outlined: false)[Abstract]
#include "content/00-abstract.typ"

#include "content/10-introduction.typ"
#include "content/20-approach.typ"
#include "content/80-conclusion.typ"

#heading(numbering: none)[Acknowledgments]
#include "content/90-acknowledgments.typ"

#bibliography("references.bib", title: "References")
