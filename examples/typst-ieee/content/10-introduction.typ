= Introduction

The IEEE template on Typst Universe is a package, `charged-ieee`, imported
by name and version at the top of the paper @charged. A package is fetched
over the network the first time it is imported, which is one thing a
reproducible build should not do; paperkit fetches the packages the
configuration declares when it builds the image, and the build itself runs
offline @reproducible.

The template sets TeX Gyre Termes, which Typst does not embed. The
`typst-ieee` profile installs the font package in the image, so the build
sees it there; on a machine without it, Typst would substitute another
family and paperkit would report which.
