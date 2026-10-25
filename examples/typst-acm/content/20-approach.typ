= Approach

ACM calls state the page limit as "N pages, not including references", so
the acknowledgments are inside the budget. The `typst-acm` profile sets
`ack_counts_as_content` as its LaTeX sibling does, and the configuration
writes it out next to the call's number. The headings paperkit measures
against come from `typst query`, the same source as the citations.

#figure(
  table(
    columns: 2,
    align: left,
    table.header([*Font*], [*Where from*]),
    [Libertinus Serif], [embedded in Typst],
    [Libertinus Sans, Libertinus Math], [`fonts/`, with the paper],
    [Inconsolata], [`fonts/`, with the paper],
  ),
  caption: [The fonts of this paper and where the build finds them.],
)
