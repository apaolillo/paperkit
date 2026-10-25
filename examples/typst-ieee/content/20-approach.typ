= Approach

The report for a Typst build has the rows a LaTeX build has, minus the
boxes, which Typst does not have, and plus one: the packages the compilation
used, read from its dependency list, and whether each was declared. An
import nobody declared still builds, downloaded at build time, and that row
says so.

#figure(
  table(
    columns: 2,
    align: left,
    table.header([*Declared*], [*In the image*]),
    [`@preview/charged-ieee:0.1.4`], [yes, fetched at image build],
  ),
  caption: [The packages row of the report for this paper.],
)
