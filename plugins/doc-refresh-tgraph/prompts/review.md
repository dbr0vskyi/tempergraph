# review

Review the rewrite of {doc} against the request: {request}

1. Read the request for the sections it names, then read each of those sections in the document.
2. A section is ready when each statement in it can be checked against a file or a command of this repository and holds, and it still says what its heading promises. It is not ready when a statement is wrong, cannot be checked, or the section lost something a reader needs.
3. For each rewritten section, say whether it is ready and why in one sentence that names the statement or the file you checked. Do not edit the document.

## What a good result shows

- The review names each rewritten section and gives `approve` or `redo` with a reason.

## Output

- `verdict`: `approve` when every rewritten section is ready, else `redo`, with the sections to redo and why.
