import os
import sys
import tempfile
import time
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import objects
import repo


class ObjectTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = repo.repo_create(os.path.realpath(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_blob_roundtrip(self):
        b = objects.GitBlob(b"hello\x00world")
        sha = objects.object_write(b, self.r)
        self.assertEqual(objects.object_read(self.r, sha).blobdata, b"hello\x00world")

    def test_blob_sha_matches_git(self):
        # same value as `echo hello | git hash-object --stdin`
        b = objects.GitBlob(b"hello\n")
        self.assertEqual(objects.object_write(b), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_commit_roundtrip(self):
        c = objects.GitCommit()
        c.kvlm[b"tree"] = b"a" * 40
        c.kvlm[None] = b"a message\n"
        out = objects.object_read(self.r, objects.object_write(c, self.r))
        self.assertEqual(out.kvlm[b"tree"], b"a" * 40)
        self.assertEqual(out.kvlm[None], b"a message\n")

    def test_tree_roundtrip(self):
        t = objects.GitTree()
        t.items.append(objects.GitTreeLeaf(b"100644", "a.txt", "b" * 40))
        out = objects.object_read(self.r, objects.object_write(t, self.r))
        self.assertEqual(out.items[0].path, "a.txt")
        self.assertEqual(out.items[0].sha, "b" * 40)

    def test_read_missing_returns_none(self):
        self.assertIsNone(objects.object_read(self.r, "0" * 40))

    def test_find_by_short_hash(self):
        sha = objects.object_write(objects.GitBlob(b"x"), self.r)
        self.assertEqual(objects.object_find(self.r, sha[:7]), sha)


class CommitTimezoneTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = repo.repo_create(os.path.realpath(self.tmp.name))
        self.old_tz = os.environ.get("TZ")

    def tearDown(self):
        if self.old_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = self.old_tz
        time.tzset()
        self.tmp.cleanup()

    def offset(self, tz_name):
        os.environ["TZ"] = tz_name
        time.tzset()
        sha = objects.commit_create(self.r, "a" * 40, None, "T <t@e>", datetime(2021, 1, 1, 12), "m")
        return objects.object_read(self.r, sha).kvlm[b"committer"].decode().split()[-1]

    def test_west_of_utc(self):
        self.assertEqual(self.offset("America/New_York"), "-0500")

    def test_utc(self):
        self.assertEqual(self.offset("UTC"), "+0000")

    def test_half_hour(self):
        self.assertEqual(self.offset("Asia/Kolkata"), "+0530")


if __name__ == "__main__":
    unittest.main()
