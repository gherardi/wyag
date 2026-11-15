# wyag

A lightweight version control system implementation in Python.

## Description

`wyag` is a project that demonstrates the core concepts of Git by implementing a simplified version control system from scratch. It handles repository creation, reading and writing objects, creating and reading commits, branch navigation, the staging area, indexing, and commit history management.

## Usage

```bash
./wyag init .
./wyag add <file>
./wyag commit -m "message"
```

## Commands

| Command | Description |
|---|---|
| `init [directory]` | Create a new, empty repository |
| `cat-file <type> <object>` | Print the raw content of an object (blob, tree, commit or tag) |
| `hash-object [-t type] [-w] <file>` | Compute the SHA-1 of a file and optionally write it to the object database |
| `log [commit]` | Print the commit history, starting from the given commit (HEAD by default) |
| `ls-tree [-r] <tree>` | List the contents of a tree object, optionally recursing into subtrees |
| `checkout <commit> <directory>` | Extract a commit or tree into an empty directory |
| `show-ref` | List all references with their hashes |
| `tag [-a] [name] [object]` | List tags, or create a lightweight (or annotated, with `-a`) tag |
| `rev-parse [--wyag-type type] <name>` | Resolve a name (HEAD, branch, tag, short hash) to a full SHA-1 |
| `ls-files [--verbose]` | List the files in the staging area |
| `check-ignore <path>...` | Print the paths that match the ignore rules |
| `status` | Show the current branch, staged changes, unstaged changes and untracked files |
| `rm <path>...` | Remove files from the index and the working tree |
| `add <path>...` | Add files or directories to the index |
| `commit -m <message>` | Record the staged changes as a new commit |

## Getting Started

1. Clone the repository
2. Install Python 3.10+
3. Run `chmod +x wyag` to make the file executable

## Reference

This project was developed following the guide created by [Thibault Polge](https://github.com/thblt) at [https://wyag.thb.lt/](https://wyag.thb.lt/)
