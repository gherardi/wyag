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


@dataclass
class StatusReport:
    branch: str = None
    detached_head: str = None
    staged: list = field(default_factory=list)
    unstaged: list = field(default_factory=list)
    untracked: list = field(default_factory=list)


def compute(repository, index):
    # the three-way comparison that IS git status, returned as a value (no I/O out)
    status = WorktreeStatus()
    _status_head_index(repository, index, status)
    _status_index_worktree(repository, index, status)
    for lst in (status.staged_added, status.staged_modified, status.staged_deleted,
                status.unstaged_modified, status.unstaged_deleted, status.untracked):
        lst.sort()
    return status


def staged_changes(repository, idx):
    # compare the index (staging area) against the HEAD commit's tree
    try:
        head_sha = objects.object_find(repository, "HEAD")
    except:
        head_sha = None
    head = objects.tree_to_dict(repository, "HEAD") if head_sha else dict()
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
    return changes


def worktree_changes(repository, idx):
    # compare the working directory against the index; return (unstaged changes, untracked paths)
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

    unstaged = list()
    for entry in idx.entries:
        full_path = os.path.join(repository.worktree, entry.name)
        if not os.path.exists(full_path):
            unstaged.append(("deleted", entry.name))
        else:
            # detect content changes via timestamps first, then confirm with a content hash
            stat = os.stat(full_path)
            ctime_ns = entry.ctime[0] * 10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10**9 + entry.mtime[1]
            if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                with open(full_path, "rb") as fd:
                    new_sha = objects.object_hash(fd, b"blob", None)
                    if entry.sha != new_sha:
                        unstaged.append(("modified", entry.name))
        if entry.name in all_files:
            all_files.remove(entry.name)

    untracked = [f for f in all_files if not ignore.check_ignore(ign, f)]
    return unstaged, untracked


def status_report(repository, idx):
    branch = repo.branch_get_active(repository)
    try:
        detached = None if branch else objects.object_find(repository, "HEAD")
    except:
        detached = None
    unstaged, untracked = worktree_changes(repository, idx)
    return StatusReport(
        branch=branch or None,
        detached_head=detached,
        staged=staged_changes(repository, idx),
        unstaged=unstaged,
        untracked=untracked,
    )


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
