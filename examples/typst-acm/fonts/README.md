# Fonts for the Typst ACM example

`faithful-acmart` sets Libertinus Sans and Libertinus Math for the text and
Inconsolata for code, and ships none of them; Typst embeds Libertinus Serif
only. These OpenType files come from TeX Live's
`texmf-dist/fonts/opentype/public/{libertinus-fonts,inconsolata}` and are
licensed under the SIL Open Font License, reproduced in `OFL.txt`.

The configuration lists this directory under `[typst] fonts` and keeps system
fonts out of the build, so the paper renders the same wherever it is built,
and `paperkit zip` ships the directory in the archive.
