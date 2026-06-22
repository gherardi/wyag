import hashlib
import os
import re
import sys
import zlib
import tempfile
from math import ceil

import repo

class GitObject(object):
    def __init__(self, data=None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self):
        raise Exception("Unimplemented!")

    def deserialize(self, data):
        raise Exception("Unimplemented!")

    def init(self):
        pass

class GitBlob(GitObject):
    fmt=b'blob'
    def serialize(self):
        return self.blobdata
    def deserialize(self, data):
        self.blobdata = data

class GitCommit(GitObject):
    fmt=b'commit'
    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)
    def serialize(self):
        return kvlm_serialize(self.kvlm)
    def init(self):
        self.kvlm = dict()

class GitTag(GitCommit):
    fmt = b'tag'

class GitTreeLeaf(object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

class GitTree(GitObject):
    fmt = b'tree'
    def deserialize(self, data):
        self.items = tree_parse(data)
    def serialize(self):
        return tree_serialize(self)
    def init(self):
        self.items = list()

def object_read(repository, sha):
    # decompress git object from disk and parse its header
    # format: type-name space size null-byte data
    path = repo.repo_file(repository, "objects", sha[0:2], sha[2:])
    if not os.path.isfile(path):
        return None
    with open (path, "rb") as f:
        raw = zlib.decompress(f.read())
        x = raw.find(b' ')
        fmt = raw[0:x]
        y = raw.find(b'\x00', x)
        size = int(raw[x:y].decode("ascii"))
        if size != len(raw)-y-1:
            raise Exception(f"Malformed object {sha}: bad length")
        match fmt:
            case b'commit' : c=GitCommit
            case b'tree'   : c=GitTree
            case b'tag'    : c=GitTag
            case b'blob'   : c=GitBlob
            case _:
                raise Exception(f"Unknown type {fmt.decode('ascii')} for object {sha}")
        return c(raw[y+1:])

def object_write(obj, repository=None):
    """
    writes a git object to the repository with atomic write to prevent corruption.
    """
    data = obj.serialize()
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data
    sha = hashlib.sha1(result).hexdigest()

    if repository:
        path = repo.repo_file(repository, "objects", sha[0:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            # atomic write pattern: write to temp file then rename to avoid partial writes
            dirname = os.path.dirname(path)
            fd, tmp_path = tempfile.mkstemp(dir=dirname)
            
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(zlib.compress(result))
                # atomic rename operation is guaranteed to be safe
                os.replace(tmp_path, path)
            except Exception as e:
                # cleanup temp file on error
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise e

    return sha

def object_find(repository, name, fmt=None, follow=True):
    sha = object_resolve(repository, name)
    if not sha:
        raise Exception(f"No such reference {name}.")
    if len(sha) > 1:
        candidates = "\n - ".join(sha)
        raise Exception(f"Ambiguous reference {name}: Candidates are:\n - {candidates}.")
    sha = sha[0]
    if not fmt:
        return sha
    # follow object references through tags and commits to find requested type
    while True:
        obj = object_read(repository, sha)
        if obj is None:
            raise Exception(f"Object {sha} not found.")
        if obj.fmt == fmt:
            return sha
        if not follow:
            raise Exception(f"Object {sha} is a {obj.fmt.decode('ascii')}, not {fmt.decode('ascii')}.")
        if obj.fmt == b'tag':
            sha = obj.kvlm[b'object'].decode("ascii")
        elif obj.fmt == b'commit' and fmt == b'tree':
            sha = obj.kvlm[b'tree'].decode("ascii")
        else:
            raise Exception(f"Object {sha} is a {obj.fmt.decode('ascii')}, not {fmt.decode('ascii')}.")

def object_resolve(repository, name):
    candidates = list()
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")
    if not name.strip():
        return None
    if name == "HEAD":
        head = repo.ref_resolve(repository, "HEAD")
        return [ head ] if head else []
    if hashRE.match(name):
        name = name.lower()
        prefix = name[0:2]
        path = repo.repo_dir(repository, "objects", prefix, mkdir=False)
        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    candidates.append(prefix + f)
    as_tag = repo.ref_resolve(repository, "refs/tags/" + name)
    if as_tag: candidates.append(as_tag)
    as_branch = repo.ref_resolve(repository, "refs/heads/" + name)
    if as_branch: candidates.append(as_branch)
    as_remote_branch = repo.ref_resolve(repository, "refs/remotes/" + name)
    if as_remote_branch: candidates.append(as_remote_branch)
    return candidates

def object_hash(fd, fmt, repository=None):
    data = fd.read()
    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree'   : obj=GitTree(data)
        case b'tag'    : obj=GitTag(data)
        case b'blob'   : obj=GitBlob(data)
        case _: raise Exception(f"Unknown type {fmt}!")
    return object_write(obj, repository)

def kvlm_parse(raw, start=0, dct=None):
    # git commit/tag format: key-value list with multi-line values (continuation lines start with space)
    if dct is None: dct = dict()
    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)
    if (spc < 0) or (nl < spc):
        if nl != start:
            raise Exception("Malformed object: expected blank line before message body")
        dct[None] = raw[start+1:]
        return dct
    key = raw[start:spc]
    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if end == -1:
            # malformed: header value runs to the end with no terminating newline
            end = len(raw)
            break
        # a continuation line starts with a space; otherwise the value ends here
        if end + 1 >= len(raw) or raw[end+1] != ord(' '):
            break
    # unescape continuation lines by removing leading space
    value = raw[spc+1:end].replace(b'\n ', b'\n')
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value ]
    else:
        dct[key]=value
    return kvlm_parse(raw, start=end+1, dct=dct)

def kvlm_serialize(kvlm):
    # git commit/tag format serialization with continuation line escaping
    # multi-line values must have each newline followed by a space (escaped as \n )
    ret = b''
    for k in kvlm.keys():
        if k == None: continue
        val = kvlm[k]
        if type(val) != list: val = [ val ]
        for v in val:
            ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'
    ret += b'\n' + kvlm.get(None, b"")
    return ret

def tree_parse_one(raw, start=0):
    # git tree format: mode(5-6 bytes) space path null-terminated sha(20 bytes)
    x = raw.find(b' ', start)
    if x - start not in (5, 6):
        raise Exception(f"Malformed tree entry: bad mode width at offset {start}")
    mode = raw[start:x]
    if len(mode) == 5:
        mode = b"0" + mode
    y = raw.find(b'\x00', x)
    path = raw[x+1:y]
    raw_sha = int.from_bytes(raw[y+1:y+21], "big")
    sha = format(raw_sha, "040x")
    return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)

def tree_parse(raw):
    # parse variable-length entries from tree object binary data
    # each entry: mode path(null-terminated) 20-byte binary sha
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)
    return ret

def is_tree(mode):
    # tree (directory) entries have mode 040000; blobs, symlinks (120000) and
    # gitlinks (160000) are all leaves
    return mode.startswith(b"04")

def tree_leaf_sort_key(leaf):
    # git sorts tree entries by name, treating a directory as if its name ended
    # in "/" so a subtree sorts before a file sharing its prefix; only trees get
    # the implicit slash (symlinks/gitlinks sort as plain names)
    if is_tree(leaf.mode):
        return leaf.path + "/"
    else:
        return leaf.path

def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        # git stores modes as octal with no leading zero (tree 040000 -> 40000)
        ret += i.mode.lstrip(b"0")
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder="big")
    return ret

def ls_tree(repository, ref, recursive=None, prefix=""):
    sha = object_find(repository, ref, fmt=b"tree")
    obj = object_read(repository, sha)
    if obj is None:
        raise Exception(f"Object {sha} not found.")
    for item in obj.items:
        # mode is normalized to 6 bytes on parse, so the type prefix is the first 2
        type = item.mode[0:2]
        match type:
            case b'04': type = "tree"
            case b'10': type = "blob"
            case b'12': type = "blob"
            case b'16': type = "commit"
            case _: raise Exception(f"Weird tree leaf mode {item.mode}")
        if not (recursive and type=='tree'):
            print(f"{item.mode.decode('ascii')} {type} {item.sha}\t{os.path.join(prefix, item.path)}")
        else:
            ls_tree(repository, item.sha, recursive, os.path.join(prefix, item.path))

def tree_checkout(repository, tree, path):
    for item in tree.items:
        obj = object_read(repository, item.sha)
        if obj is None:
            raise Exception(f"Object {item.sha} not found.")
        dest = os.path.join(path, item.path)
        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repository, obj, dest)
        elif obj.fmt == b'blob':
            with open(dest, 'wb') as f:
                f.write(obj.blobdata)

def tree_to_dict(repository, ref, prefix=""):
    ret = dict()
    tree_sha = object_find(repository, ref, fmt=b"tree")
    tree = object_read(repository, tree_sha)
    for leaf in tree.items:
        full_path = os.path.join(prefix, leaf.path)
        is_subtree = is_tree(leaf.mode)
        if is_subtree:
            ret.update(tree_to_dict(repository, leaf.sha, full_path))
        else:
            ret[full_path] = leaf.sha
    return ret

def log_graphviz(repository, sha, seen):
    # depth-first traversal of commit graph with cycle detection
    # 'seen' set prevents infinite loops on circular commit history (shouldn't happen in valid repos)
    if sha in seen: return
    seen.add(sha)
    commit = object_read(repository, sha)
    if commit is None:
        raise Exception(f"Object {sha} not found.")
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\", "\\\\").replace("\"", "\\\"")
    if "\n" in message:
        message = message[:message.index("\n")]
    print(f"  c_{sha} [label=\"{sha[0:7]}: {message}\"]")
    assert commit.fmt==b'commit'
    if not b'parent' in commit.kvlm.keys(): return
    parents = commit.kvlm[b'parent']
    if type(parents) != list: parents = [ parents ]
    for p in parents:
        p = p.decode("ascii")
        print (f"  c_{sha} -> c_{p};")
        log_graphviz(repository, p, seen)
