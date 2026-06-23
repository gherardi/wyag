import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import repo
import index
import objects
import status


class StatusReportTests(unittest.TestCase):
    # status_report returns a value, so we assert on data instead of scraping stdout

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.realpath(self.tmp.name)
        self.r = repo.repo_create(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content):
        full = os.path.join(self.path, name)
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(full, "w") as f:
            f.write(content)
        return full

    def _add(self, *names):
        index.add(self.r, [os.path.join(self.path, n) for n in names])

    def _commit_index(self):
        idx = index.index_read(self.r)
        tree = index.tree_from_index(self.r, idx)
        sha = objects.commit_create(self.r, tree, None, "T <t@e>", datetime.now(), "base")
        with open(repo.repo_file(self.r, "refs/heads/master"), "w") as f:
            f.write(sha + "\n")
        return sha

    def _report(self):
        return status.status_report(self.r, index.index_read(self.r))

    def test_branch_is_master(self):
        self.assertEqual(self._report().branch, "master")

    def test_added_is_staged(self):
        self._commit_index()  # HEAD = empty-tree commit
        self._write("new.txt", "hi")
        self._add("new.txt")
        self.assertIn(("added", "new.txt"), self._report().staged)

    def test_committed_then_modified_is_staged_modified(self):
        self._write("f.txt", "v1")
        self._add("f.txt")
        self._commit_index()
        self._write("f.txt", "v2 changed")
        self._add("f.txt")
        self.assertIn(("modified", "f.txt"), self._report().staged)

    def test_removed_from_index_is_staged_deleted(self):
        self._write("gone.txt", "data")
        self._add("gone.txt")
        self._commit_index()
        index.rm(self.r, [os.path.join(self.path, "gone.txt")])
        self.assertIn(("deleted", "gone.txt"), self._report().staged)

    def test_worktree_edit_is_unstaged_modified(self):
        full = self._write("w.txt", "first")
        self._add("w.txt")
        self._commit_index()
        with open(full, "w") as f:
            f.write("edited on disk")
        # force a different mtime so detection is deterministic
        future = os.stat(full).st_mtime + 100
        os.utime(full, (future, future))
        self.assertIn(("modified", "w.txt"), self._report().unstaged)

    def test_worktree_delete_is_unstaged_deleted(self):
        full = self._write("d.txt", "data")
        self._add("d.txt")
        self._commit_index()
        os.unlink(full)
        self.assertIn(("deleted", "d.txt"), self._report().unstaged)

    def test_untracked_file_is_listed(self):
        self._write("loose.txt", "untracked")
        self.assertIn("loose.txt", self._report().untracked)

    def test_clean_tracked_file_is_not_reported(self):
        self._write("clean.txt", "stable")
        self._add("clean.txt")
        self._commit_index()
        rep = self._report()
        self.assertNotIn("clean.txt", rep.untracked)
        self.assertEqual(rep.unstaged, [])


if __name__ == "__main__":
    unittest.main()
