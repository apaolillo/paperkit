= Introduction

The ACM template on Typst Universe, `faithful-acmart`, follows the LaTeX
class closely, down to the fonts: Libertinus for the text and mathematics,
Inconsolata for code @faithful. Typst embeds Libertinus Serif and nothing
else of those, and the package does not ship them, so a paper that wants
the same rendering everywhere carries them. This one does, under `fonts/`,
with their licence, and lists the directory in its configuration.

paperkit then builds with system fonts off: what Typst embeds, what the
project carries and what the image installs are all a build sees, the same
on every machine @reproducible. A family nobody provides is reported with
the file and line that asked for it, rather than substituted silently.
