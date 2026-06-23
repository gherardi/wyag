import os
import zlib
import tempfile

# Object storage adapters: the seam between content-addressed bytes and where they live.
# Both expose the same two-method interface so the object store (objects.py) can read and
# write without knowing whether bytes land on disk or in a dict. Values are the *raw*
# (uncompressed) serialized object bytes — "fmt size\x00body"; zlib is a disk-format concern
# and stays inside FilesystemStorage.

class MemoryStorage(object):
    # In-memory adapter, used by tests: sha -> raw bytes, no filesystem touched.
    def __init__(self):
        self.objects = dict()

    def read_object(self, sha):
        return self.objects.get(sha)

    def write_object(self, sha, raw):
        # content-addressed: identical sha implies identical bytes, so first write wins
        self.objects.setdefault(sha, raw)

class FilesystemStorage(object):
    # On-disk adapter: objects live zlib-compressed under .git/objects/ab/cdef...
    def __init__(self, gitdir):
        self.gitdir = gitdir

    def _object_path(self, sha, mkdir=False):
        objects_dir = os.path.abspath(os.path.join(self.gitdir, "objects"))
        path = os.path.abspath(os.path.join(objects_dir, sha[0:2], sha[2:]))
        # path-traversal guard: a sha may originate from object/ref *content* (commit/tag
        # kvlm fields, ref files), which is not hex-validated, so it must not escape objects/.
        if not path.startswith(objects_dir + os.sep):
            raise Exception(f"Potential Path Traversal Detected: {path} is outside {objects_dir}")
        directory = os.path.dirname(path)
        if mkdir:
            os.makedirs(directory, exist_ok=True)
        return path

    def read_object(self, sha):
        path = self._object_path(sha)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return zlib.decompress(f.read())

    def write_object(self, sha, raw):
        path = self._object_path(sha, mkdir=True)
        if os.path.exists(path):
            return
        # atomic write: temp file then rename, so a crash never leaves a partial object
        dirname = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dirname)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(zlib.compress(raw))
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
