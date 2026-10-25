= Approach

The citations come from `typst query`, the build's own account of what the
document cites, so the unused-entry check reads the same truth for Typst
that the `.aux` file is for LaTeX. Typst's diagnostics are the log, and the
list of files the compilation read, from `typst compile --deps`, is what
`paperkit zip` archives: exactly the sources, no more.

#figure(
  table(
    columns: 2,
    align: left,
    table.header([*LaTeX*], [*Typst*]),
    [`.aux` file], [`typst query`],
    [`.log` file], [compiler diagnostics],
    [`[zip] include` patterns], [the dependency list],
    [three or four passes], [one],
  ),
  caption: [Where paperkit reads the same facts for each engine.],
)
