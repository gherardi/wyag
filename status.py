import os

import ignore
import objects
import refs

def staged_changes(repository, idx):
    # compare the index with the tree of the HEAD commit
    if refs.ref_resolve(repository, "HEAD"):
        head = objects.tree_to_dict(repository, "HEAD")
    else:
        head = dict()
    changes = list()
    for entry in idx.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                changes.append(("modified", entry.name))
            del head[entry.name]
        else:
            changes.append(("added", entry.name))
    for name in head.keys():
        changes.append(("deleted", name))
    return sorted(changes, key=lambda c: c[1])

def worktree_changes(repository, idx):
    # compare the files on disk with the index; returns (unstaged, untracked)
    ign = ignore.gitignore_read(repository)
    gitdir_prefix = repository.gitdir + os.path.sep
    all_files = set()
    for (root, _, files) in os.walk(repository.worktree, True):
        if root == repository.gitdir or root.startswith(gitdir_prefix):
            continue
        for f in files:
            full_path = os.path.join(root, f)
            all_files.add(os.path.relpath(full_path, repository.worktree))

    unstaged = list()
    for entry in idx.entries:
        full_path = os.path.join(repository.worktree, entry.name)
        if not os.path.lexists(full_path):
            unstaged.append(("deleted", entry.name))
        else:
            # only rehash the file if its timestamps changed
            st = os.lstat(full_path)
            ctime_ns = entry.ctime[0] * 10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10**9 + entry.mtime[1]
            if (st.st_ctime_ns != ctime_ns) or (st.st_mtime_ns != mtime_ns):
                if os.path.islink(full_path):
                    blob = objects.GitBlob(os.readlink(full_path).encode("utf8"))
                    new_sha = objects.object_write(blob)
                else:
                    with open(full_path, "rb") as fd:
                        new_sha = objects.object_hash(fd, b"blob", None)
                if entry.sha != new_sha:
                    unstaged.append(("modified", entry.name))
        all_files.discard(entry.name)

    untracked = [f for f in sorted(all_files) if not ignore.check_ignore(ign, f)]
    return sorted(unstaged, key=lambda c: c[1]), untracked
