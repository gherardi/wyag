import os
from dataclasses import dataclass, field

import ignore
import objects
import refs
import repo


@dataclass
class WorktreeStatus:
    # staged: HEAD tree vs index
    staged_added: list = field(default_factory=list)
    staged_modified: list = field(default_factory=list)
    staged_deleted: list = field(default_factory=list)
    # unstaged: index vs worktree
    unstaged_modified: list = field(default_factory=list)
    unstaged_deleted: list = field(default_factory=list)
    untracked: list = field(default_factory=list)

    @property
    def has_staged_changes(self):
        return bool(self.staged_added or self.staged_modified or self.staged_deleted)

    @property
    def is_clean(self):
        return not (self.has_staged_changes
                    or self.unstaged_modified or self.unstaged_deleted
                    or self.untracked)


def compute(repository, index):
    # the three-way comparison that IS git status, returned as a value (no I/O out)
    status = WorktreeStatus()
    _status_head_index(repository, index, status)
    _status_index_worktree(repository, index, status)
    for lst in (status.staged_added, status.staged_modified, status.staged_deleted,
                status.unstaged_modified, status.unstaged_deleted, status.untracked):
        lst.sort()
    return status


def _status_head_index(repository, index, status):
    # compare index (staging area) with HEAD commit -> staged add/modify/delete
    head_sha = refs.ref_resolve(repository, "HEAD")
    if head_sha:
        head = objects.tree_to_dict(repository, "HEAD")
    else:
        head = dict()
    for entry in index.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                status.staged_modified.append(entry.name)
            del head[entry.name]
        else:
            status.staged_added.append(entry.name)
    for name in head.keys():
        status.staged_deleted.append(name)


def _status_index_worktree(repository, index, status):
    # compare working directory with index -> unstaged modify/delete + untracked
    ign = ignore.gitignore_read(repository)
    gitdir_prefix = repository.gitdir + os.path.sep
    all_files = list()
    for (root, _, files) in os.walk(repository.worktree, True):
        if root == repository.gitdir or root.startswith(gitdir_prefix):
            continue
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, repository.worktree)
            all_files.append(rel_path)

    for entry in index.entries:
        full_path = os.path.join(repository.worktree, entry.name)
        if not os.path.exists(full_path):
            status.unstaged_deleted.append(entry.name)
        else:
            # check ctime/mtime first; only rehash when the timestamps moved
            stat = os.stat(full_path)
            ctime_ns = entry.ctime[0] * 10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10**9 + entry.mtime[1]
            if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                with open(full_path, "rb") as fd:
                    new_sha = objects.object_hash(fd, b"blob", None)
                    if entry.sha != new_sha:
                        status.unstaged_modified.append(entry.name)
        if entry.name in all_files:
            all_files.remove(entry.name)

    for f in all_files:
        if not ignore.check_ignore(ign, f):
            status.untracked.append(f)
