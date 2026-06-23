import os
import tempfile
import unittest
from datetime import datetime

import index
import objects
import refs
import repo
import status


class StatusTest(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.dir = tempfile.mkdtemp()
        repo.repo_create(self.dir)
        os.chdir(self.dir)
        self.repo = repo.repo_find()

    def tearDown(self):
        os.chdir(self._cwd)

    # helpers ---------------------------------------------------------------
    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def status(self):
        return status.compute(self.repo, index.index_read(self.repo))

    def commit_index(self):
        idx = index.index_read(self.repo)
        tree = index.tree_from_index(self.repo, idx)
        sha = objects.commit_create(self.repo, tree, None, "T <t@e>", datetime.now(), "msg")
        refs.ref_create(self.repo, "heads/master", sha)  # HEAD -> refs/heads/master

    # tests -----------------------------------------------------------------
    def test_empty_repo_is_clean(self):
        self.assertTrue(self.status().is_clean)

    def test_untracked(self):
        self.write("a.txt", "hi")
        st = self.status()
        self.assertEqual(st.untracked, ["a.txt"])
        self.assertFalse(st.is_clean)

    def test_staged_added(self):
        self.write("a.txt", "hi")
        index.add(self.repo, ["a.txt"])
        st = self.status()
        self.assertEqual(st.staged_added, ["a.txt"])
        self.assertEqual(st.untracked, [])
        self.assertTrue(st.has_staged_changes)

    def test_unstaged_modified(self):
        # the bug-prone path: timestamp check then rehash
        self.write("a.txt", "hi")
        index.add(self.repo, ["a.txt"])
        self.write("a.txt", "changed")
        # force the timestamp-differs branch deterministically
        os.utime(os.path.join(self.dir, "a.txt"), (10**9, 10**9))
        st = self.status()
        self.assertEqual(st.unstaged_modified, ["a.txt"])

    def test_unstaged_deleted(self):
        self.write("a.txt", "hi")
        index.add(self.repo, ["a.txt"])
        os.unlink(os.path.join(self.dir, "a.txt"))
        st = self.status()
        self.assertEqual(st.unstaged_deleted, ["a.txt"])

    def test_committed_then_clean(self):
        self.write("a.txt", "hi")
        index.add(self.repo, ["a.txt"])
        self.commit_index()
        st = self.status()
        self.assertFalse(st.has_staged_changes)

    def test_staged_modified_vs_head(self):
        self.write("a.txt", "hi")
        index.add(self.repo, ["a.txt"])
        self.commit_index()
        self.write("a.txt", "changed")
        index.add(self.repo, ["a.txt"])
        st = self.status()
        self.assertEqual(st.staged_modified, ["a.txt"])

    def test_staged_deleted_vs_head(self):
        self.write("a.txt", "hi")
        index.add(self.repo, ["a.txt"])
        self.commit_index()
        index.rm(self.repo, ["a.txt"])
        st = self.status()
        self.assertEqual(st.staged_deleted, ["a.txt"])

    def test_sorted_output(self):
        for n in ["c.txt", "a.txt", "b.txt"]:
            self.write(n, "x")
        self.assertEqual(self.status().untracked, ["a.txt", "b.txt", "c.txt"])


if __name__ == "__main__":
    unittest.main()
