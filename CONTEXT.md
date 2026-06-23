# wyag — domain glossary

Ubiquitous language for this Git implementation. Use these terms in code and discussion.

## Core objects
- **Object** — content-addressed blob/tree/commit/tag, stored zlib-compressed under `.git/objects` keyed by SHA-1. Read/written via `objects.py`.
- **Index** — the staging area: a binary file (`.git/index`) of `GitIndexEntry` rows mapping worktree paths to blob SHAs + stat metadata. Read/written via `index.py`.
- **Worktree** — the checked-out files on disk.
- **Ref** — a named pointer (branch, tag, HEAD) resolving to a SHA, possibly through symbolic indirection. All ref ops (resolve/list/create/branch + show/tag) live in `refs.py`.

## Status
- **WorktreeStatus** — the structured result of the three-way comparison HEAD-tree ↔ index ↔ worktree. Six sorted path lists: `staged_added/modified/deleted` (HEAD vs index), `unstaged_modified/deleted` (index vs worktree), `untracked`. Plus `has_staged_changes` / `is_clean`. Produced by `status.compute(repository, index)` with no I/O out (returns a value, prints nothing). The CLI renders it; `commit` reads `has_staged_changes` as its "nothing to commit" guard. Lives in `status.py`.
