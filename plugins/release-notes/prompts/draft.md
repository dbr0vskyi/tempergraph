Write release notes for {request} into `notes.md` at the repository root.

1. Find the last tag with `git describe --tags --abbrev=0`, then list the merged changes since it with `git log <tag>..HEAD --merges --oneline` (or all commits when the repository does not use merge commits).
2. Use exactly these four headings, in this order: `# Added`, `# Changed`, `# Fixed`, `# Removed`. Leave a heading with no entry followed by `- none`.
3. One entry per change: what it does for a reader, in one plain sentence, with its short commit id in brackets.
4. A change you leave out goes under a final `## Excluded` list with the reason (for example, a merge of main or a version bump).
