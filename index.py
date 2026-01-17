import os
import time
import tempfile
from math import ceil

import repo
import objects

class GitIndexEntry(object):
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None, mode_type=None, mode_perms=None, uid=None, gid=None, fsize=None, sha=None, flag_assume_valid=None, flag_stage=None, name=None):
        self.ctime = ctime
        self.mtime = mtime
        self.dev = dev
        self.ino = ino
        self.mode_type = mode_type
        self.mode_perms = mode_perms
        self.uid = uid
        self.gid = gid
        self.fsize = fsize
        self.sha = sha
        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage
        self.name = name

class GitIndex(object):
    version = None
    entries = []
    def __init__(self, version=2, entries=None):
        if not entries: entries = list()
        self.version = version
        self.entries = entries

def index_read(repository):
    # git index (staging area) binary format: header + entries + hash
    # header: 4-byte signature + version + entry count
    # entries: 62 bytes + filename + null + padding to 8-byte boundary
    index_file = repo.repo_file(repository, "index")
    if not os.path.exists(index_file):
        return GitIndex()
    with open(index_file, 'rb') as f:
        raw = f.read()
    header = raw[:12]
    signature = header[:4]
    assert signature == b"DIRC"
    version = int.from_bytes(header[4:8], "big")
    assert version == 2, "wyag only supports index file version 2"
    count = int.from_bytes(header[8:12], "big")
    entries = list()
    content = raw[12:]
    idx = 0
    for i in range(0, count):
        # parse fixed 62-byte entry header with file metadata
        # followed by variable-length filename and 8-byte padding alignment
        ctime_s =  int.from_bytes(content[idx: idx+4], "big")
        ctime_ns = int.from_bytes(content[idx+4: idx+8], "big")
        mtime_s = int.from_bytes(content[idx+8: idx+12], "big")
        mtime_ns = int.from_bytes(content[idx+12: idx+16], "big")
        dev = int.from_bytes(content[idx+16: idx+20], "big")
        ino = int.from_bytes(content[idx+20: idx+24], "big")
        unused = int.from_bytes(content[idx+24: idx+26], "big")
        assert 0 == unused
        mode = int.from_bytes(content[idx+26: idx+28], "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000, 0b1010, 0b1110]
        mode_perms = mode & 0b0000000111111111
        uid = int.from_bytes(content[idx+28: idx+32], "big")
        gid = int.from_bytes(content[idx+32: idx+36], "big")
        fsize = int.from_bytes(content[idx+36: idx+40], "big")
        sha = format(int.from_bytes(content[idx+40: idx+60], "big"), "040x")
        flags = int.from_bytes(content[idx+60: idx+62], "big")
        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage =  flags & 0b0011000000000000
        name_length = flags & 0b0000111111111111
        idx += 62
        if name_length < 0xFFF:
            assert content[idx + name_length] == 0x00
            raw_name = content[idx:idx+name_length]
            idx += name_length + 1
        else:
            # handle rare case where filename >= 4095 bytes (0xFFF is the sentinel value)
            print(f"Notice: Name is 0x{name_length:X} bytes long.")
            null_idx = content.find(b'\x00', idx + 0xFFF)
            raw_name = content[idx: null_idx]
            idx = null_idx + 1
        name = raw_name.decode("utf8")
        idx = 8 * ceil(idx / 8)
        entries.append(GitIndexEntry(ctime=(ctime_s, ctime_ns), mtime=(mtime_s,  mtime_ns), dev=dev, ino=ino, mode_type=mode_type, mode_perms=mode_perms, uid=uid, gid=gid, fsize=fsize, sha=sha, flag_assume_valid=flag_assume_valid, flag_stage=flag_stage, name=name))
    return GitIndex(version=version, entries=entries)

def index_write(r, index):
    index_file = repo.repo_file(r, "index")
    # atomic write: write to temp file, then rename
    dirname = os.path.dirname(index_file)
    fd, tmp_path = tempfile.mkstemp(dir=dirname)

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(b"DIRC")
            f.write(index.version.to_bytes(4, "big"))
            f.write(len(index.entries).to_bytes(4, "big"))
            idx = 0
            for e in index.entries:
                f.write(e.ctime[0].to_bytes(4, "big"))
                f.write(e.ctime[1].to_bytes(4, "big"))
                f.write(e.mtime[0].to_bytes(4, "big"))
                f.write(e.mtime[1].to_bytes(4, "big"))
                f.write(e.dev.to_bytes(4, "big"))
                f.write(e.ino.to_bytes(4, "big"))
                mode = (e.mode_type << 12) | e.mode_perms
                f.write(mode.to_bytes(4, "big"))
                f.write(e.uid.to_bytes(4, "big"))
                f.write(e.gid.to_bytes(4, "big"))
                f.write(e.fsize.to_bytes(4, "big"))
                f.write(int(e.sha, 16).to_bytes(20, "big"))
                flag_assume_valid = 0x1 << 15 if e.flag_assume_valid else 0
                name_bytes = e.name.encode("utf8")
                bytes_len = len(name_bytes)
                name_length = 0xFFF if bytes_len >= 0xFFF else bytes_len
                f.write((flag_assume_valid | e.flag_stage | name_length).to_bytes(2, "big"))
                f.write(name_bytes)
                f.write((0).to_bytes(1, "big"))
                idx += 62 + len(name_bytes) + 1
                if idx % 8 != 0:
                    pad = 8 - (idx % 8)
                    f.write((0).to_bytes(pad, "big"))
                    idx += pad
        # atomic rename
        os.replace(tmp_path, index_file)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise e

def rm(repository, paths, delete=True, skip_missing=False):
    index = index_read(repository)
    worktree = repository.worktree + os.sep
    abspaths = set()
    for path in paths:
        abspath = os.path.abspath(path)
        if abspath.startswith(worktree) or abspath == repository.worktree:
            abspaths.add(abspath)
        else:
            raise Exception(f"Cannot remove paths outside of worktree: {paths}")
    kept_entries = list()
    remove = list()
    for e in index.entries:
        full_path = os.path.join(repository.worktree, e.name)
        if full_path in abspaths:
            remove.append(full_path)
            abspaths.remove(full_path)
        else:
            kept_entries.append(e)
    if len(abspaths) > 0 and not skip_missing:
        raise Exception(f"Cannot remove paths not in the index: {abspaths}")
    if delete:
        for path in remove:
            os.unlink(path)
    index.entries = kept_entries
    index_write(repository, index)

def add(repository, paths, delete=True, skip_missing=False):
    rm (repository, paths, delete=False, skip_missing=True)
    worktree = repository.worktree + os.sep
    gitdir_prefix = repository.gitdir + os.sep
    clean_paths = set()
    for path in paths:
        abspath = os.path.abspath(path)
        # handle directory paths - recursively add all files
        if os.path.isdir(abspath):
            if abspath == repository.worktree or abspath.startswith(worktree):
                for (root, dirs, files) in os.walk(abspath):
                    # skip .git directory
                    if root == repository.gitdir or root.startswith(gitdir_prefix):
                        continue
                    for f in files:
                        file_abspath = os.path.join(root, f)
                        relpath = os.path.relpath(file_abspath, repository.worktree)
                        clean_paths.add((file_abspath, relpath))
            else:
                raise Exception(f"Not in worktree: {paths}")
        elif os.path.isfile(abspath):
            if abspath.startswith(worktree) or abspath == repository.worktree:
                relpath = os.path.relpath(abspath, repository.worktree)
                # skip files in .git directory
                if not (relpath.startswith(".git" + os.sep) or relpath == ".git"):
                    clean_paths.add((abspath, relpath))
            else:
                raise Exception(f"Not a file, or outside the worktree: {paths}")
        else:
            raise Exception(f"Not a file, or outside the worktree: {paths}")
    index = index_read(repository)
    for (abspath, relpath) in clean_paths:
        with open(abspath, "rb") as fd:
            sha = objects.object_hash(fd, b"blob", repository)
            stat = os.stat(abspath)
            ctime_s = int(stat.st_ctime)
            ctime_ns = stat.st_ctime_ns % 10**9
            mtime_s = int(stat.st_mtime)
            mtime_ns = stat.st_mtime_ns % 10**9
            entry = GitIndexEntry(ctime=(ctime_s, ctime_ns), mtime=(mtime_s, mtime_ns), dev=stat.st_dev, ino=stat.st_ino,
                                  mode_type=0b1000, mode_perms=0o644, uid=stat.st_uid, gid=stat.st_gid,
                                  fsize=stat.st_size, sha=sha, flag_assume_valid=False,
                                  flag_stage=False, name=relpath)
            index.entries.append(entry)
    index_write(repository, index)

def tree_from_index(repository, index):
    # convert index entries into tree objects
    # tree objects are hierarchical: one per directory level
    # process bottom-up from deepest paths to root
    contents = dict()
    contents[""] = list()
    for entry in index.entries:
        dirname = os.path.dirname(entry.name)
        key = dirname
        while key != "":
            if not key in contents:
                contents[key] = list()
            key = os.path.dirname(key)
        contents[dirname].append(entry)
    sorted_paths = sorted(contents.keys(), key=len, reverse=True)
    sha = None
    for path in sorted_paths:
        # build tree bottom-up: deepest directories first, then combine into parents
        # this ensures child tree objects exist before parent references them
        tree = objects.GitTree()
        for entry in contents[path]:
            if isinstance(entry, GitIndexEntry):
                leaf_mode = f"{entry.mode_type:02o}{entry.mode_perms:04o}".encode("ascii")
                leaf = objects.GitTreeLeaf(mode = leaf_mode, path=os.path.basename(entry.name), sha=entry.sha)
            else:
                leaf = objects.GitTreeLeaf(mode = b"040000", path=entry[0], sha=entry[1])
            tree.items.append(leaf)
        sha = objects.object_write(tree, repository)
        parent = os.path.dirname(path)
        base = os.path.basename(path)
        contents[parent].append((base, sha))
    return sha
