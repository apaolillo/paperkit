= Introduction

A Typst paper compiles in one pass, with the bibliography built in, from a
compiler that is one binary @typst. paperkit builds it in an image a fraction
of the size of the LaTeX one, around a Typst release pinned by version and
checksum, and runs the same checks on the result: the fonts in the PDF, the
page counts, the source hygiene, the entries nothing cites
@reproducible.

Two things make a Typst build depend on the machine unless the project says
otherwise. Fonts, which Typst takes from the system by default and
substitutes silently when a family is missing, so this project sees only the
fonts Typst embeds and the ones it lists itself. Packages from Typst
Universe, fetched over the network on first import, so a project declares
them and the image build fetches them once. This paper uses neither, which
is the simplest case; `examples/typst-ieee` and `examples/typst-acm` use
both.
