import os
import sys
import time
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import objects
import storage


class FakeRepo:
    # the object store only touches repository.storage, so a real .git is unnecessary
    def __init__(self):
        self.storage = storage.MemoryStorage()


class PureSerializationTests(unittest.TestCase):
    # object_serialize / object_deserialize are pure — tested with no repo and no disk

    def test_blob_roundtrip(self):
        b = objects.GitBlob()
        b.blobdata = b"hello\x00world"
        sha, raw = objects.object_serialize(b)
        out = objects.object_deserialize(raw)
        self.assertIsInstance(out, objects.GitBlob)
        self.assertEqual(out.blobdata, b"hello\x00world")

    def test_commit_roundtrip(self):
        c = objects.GitCommit()
        c.kvlm[b"tree"] = b"a" * 40
        c.kvlm[None] = b"a message\n"
        _, raw = objects.object_serialize(c)
        out = objects.object_deserialize(raw)
        self.assertEqual(out.kvlm[b"tree"], b"a" * 40)
        self.assertEqual(out.kvlm[None], b"a message\n")

    def test_tree_roundtrip(self):
        t = objects.GitTree()
        t.items.append(objects.GitTreeLeaf(b"100644", "a.txt", "b" * 40))
        _, raw = objects.object_serialize(t)
        out = objects.object_deserialize(raw)
        self.assertEqual(out.items[0].path, "a.txt")
        self.assertEqual(out.items[0].sha, "b" * 40)

    def test_content_addressing_is_stable(self):
        b1 = objects.GitBlob(); b1.blobdata = b"same"
        b2 = objects.GitBlob(); b2.blobdata = b"same"
        self.assertEqual(objects.object_serialize(b1)[0], objects.object_serialize(b2)[0])

    def test_unknown_type_raises(self):
        with self.assertRaises(Exception):
            objects.object_deserialize(b"weird 3\x00abc")

    def test_bad_length_raises(self):
        with self.assertRaises(Exception):
            objects.object_deserialize(b"blob 99\x00abc")


class ObjectStoreSeamTests(unittest.TestCase):
    # object_read / object_write go through the storage seam — here, the in-memory adapter

    def test_write_then_read(self):
        repo = FakeRepo()
        b = objects.GitBlob(); b.blobdata = b"in memory"
        sha = objects.object_write(b, repo)
        got = objects.object_read(repo, sha)
        self.assertEqual(got.blobdata, b"in memory")

    def test_read_missing_returns_none(self):
        self.assertIsNone(objects.object_read(FakeRepo(), "0" * 40))

    def test_write_without_repo_returns_sha_only(self):
        b = objects.GitBlob(); b.blobdata = b"x"
        sha = objects.object_write(b)
        self.assertEqual(len(sha), 40)

    def test_write_is_idempotent(self):
        repo = FakeRepo()
        b = objects.GitBlob(); b.blobdata = b"dup"
        sha1 = objects.object_write(b, repo)
        sha2 = objects.object_write(b, repo)
        self.assertEqual(sha1, sha2)
        self.assertEqual(len(repo.storage.objects), 1)


class CommitTimezoneTests(unittest.TestCase):
    # regression: commit_create must format the tz offset correctly for west-of-UTC and
    # zero offsets (UTC-5 -> "-0500", UTC -> "+0000"), not "--500" / "-0000"

    def _committer_offset(self, tz_name, dt):
        old = os.environ.get("TZ")
        os.environ["TZ"] = tz_name
        time.tzset()
        try:
            repo = FakeRepo()
            sha = objects.commit_create(repo, "a" * 40, None, "T <t@e>", dt, "m")
            committer = objects.object_read(repo, sha).kvlm[b"committer"].decode()
            return committer.split()[-1]
        finally:
            if old is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_west_of_utc(self):
        self.assertEqual(self._committer_offset("America/New_York", datetime(2021, 1, 1, 12)), "-0500")

    def test_utc_is_plus_zero(self):
        self.assertEqual(self._committer_offset("UTC", datetime(2021, 1, 1, 12)), "+0000")

    def test_half_hour_offset(self):
        self.assertEqual(self._committer_offset("Asia/Kolkata", datetime(2021, 1, 1, 12)), "+0530")


if __name__ == "__main__":
    unittest.main()
