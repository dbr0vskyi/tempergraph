# draft

Refresh a document so the sections the request names say what is true in this repository now.

The request: {request}
The document's headings, in order: `{outline}`

1. Read the request for the document's path and the sections to refresh.
2. For each named section, read the files and commands it describes, then rewrite the section so every statement holds today. Keep its heading.
3. Leave every other section exactly as it is, byte for byte, and keep every heading of the outline, in order.

## What a good result shows

- Every heading in the outline is still in the document, in the same order.
- Every statement in each rewritten section matches the repository as it is now.

## Output

- `doc`: the document's path.
- `size`: `minor` when you changed wording or a few facts in one section, `major` when you rewrote more than one section or changed what a section tells the reader to do.
