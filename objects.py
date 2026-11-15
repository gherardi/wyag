import hashlib
import os
import re
import zlib
from datetime import datetime, timedelta, timezone

import repo
import refs

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

OBJECT_TYPES = {
    b'commit': GitCommit,
    b'tree':   GitTree,
    b'tag':    GitTag,
    b'blob':   GitBlob,
}

# first two digits of a tree leaf mode -> object type
TREE_LEAF_MODE_TYPES = {
    b'04': 'tree',
    b'10': 'blob',
    b'12': 'blob',
    b'16': 'commit',
}

def object_read(repository, sha):
    path = repo.repo_file(repository, "objects", sha[0:2], sha[2:])
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())
    # object format: "type size\x00content"
    x = raw.find(b' ')
    fmt = raw[0:x]
    y = raw.find(b'\x00', x)
    size = int(raw[x:y].decode("ascii"))
    if size != len(raw)-y-1:
        raise Exception(f"Malformed object {sha}: bad length")
    cls = OBJECT_TYPES.get(fmt)
    if cls is None:
        raise Exception(f"Unknown type {fmt.decode('ascii')} for object {sha}")
    return cls(raw[y+1:])

def object_write(obj, repository=None):
    data = obj.serialize()
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data
    sha = hashlib.sha1(result).hexdigest()
    if repository:
        path = repo.repo_file(repository, "objects", sha[0:2], sha[2:], mkdir=True)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(zlib.compress(result))
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
    # follow tags and commits until we reach the requested type
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
        head = refs.ref_resolve(repository, "HEAD")
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
    as_tag = refs.ref_resolve(repository, "refs/tags/" + name)
    if as_tag: candidates.append(as_tag)
    as_branch = refs.ref_resolve(repository, "refs/heads/" + name)
    if as_branch: candidates.append(as_branch)
    return candidates

def object_hash(fd, fmt, repository=None):
    data = fd.read()
    cls = OBJECT_TYPES.get(fmt)
    if cls is None:
        raise Exception(f"Unknown type {fmt}!")
    obj = cls(data)
    return object_write(obj, repository)

def kvlm_parse(raw, start=0, dct=None):
    # commits and tags are "key value" lines, a blank line, then the message.
    # a value continues on the next line if that line starts with a space.
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
            end = len(raw)
            break
        if end + 1 >= len(raw) or raw[end+1] != ord(' '):
            break
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
    # tree entry: mode, space, path, null byte, 20-byte binary sha
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
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)
    return ret

def is_tree(mode):
    return mode.startswith(b"04")

def tree_leaf_sort_key(leaf):
    # git sorts directories as if their name ended with "/"
    if is_tree(leaf.mode):
        return leaf.path + "/"
    else:
        return leaf.path

def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        # git writes modes without the leading zero (040000 -> 40000)
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
    for item in obj.items:
        type = item.mode[0:2]
        if type not in TREE_LEAF_MODE_TYPES:
            raise Exception(f"Weird tree leaf mode {item.mode}")
        type = TREE_LEAF_MODE_TYPES[type]
        if not (recursive and type=='tree'):
            print(f"{item.mode.decode('ascii')} {type} {item.sha}\t{os.path.join(prefix, item.path)}")
        else:
            ls_tree(repository, item.sha, recursive, os.path.join(prefix, item.path))

def tree_checkout(repository, tree, path):
    for item in tree.items:
        obj = object_read(repository, item.sha)
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
        if is_tree(leaf.mode):
            ret.update(tree_to_dict(repository, leaf.sha, full_path))
        else:
            ret[full_path] = leaf.sha
    return ret

def log(repository, sha):
    # walk the history following the first parent of each commit
    while sha:
        commit = object_read(repository, sha)
        assert commit.fmt == b'commit'
        # author line: "Name <email> timestamp +hhmm"
        author, ts, tz = commit.kvlm[b'author'].decode("utf8").rsplit(" ", 2)
        offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
        if tz[0] == "-":
            offset = -offset
        date = datetime.fromtimestamp(int(ts), timezone(offset))
        print(f"commit {sha}")
        print(f"Author: {author}")
        print(f"Date:   {date.strftime('%a %b %d %H:%M:%S %Y')} {tz}")
        print()
        for line in commit.kvlm[None].decode("utf8").strip().splitlines():
            print(f"    {line}")
        print()
        parents = commit.kvlm.get(b'parent')
        if type(parents) == list:
            parents = parents[0]
        sha = parents.decode("ascii") if parents else None

def commit_create(repository, tree, parent, author, timestamp, message):
    commit = GitCommit()
    commit.kvlm[b"tree"] = tree.encode("ascii")
    if parent:
        commit.kvlm[b"parent"] = parent.encode("ascii")
    message = message.strip() + "\n"
    # timezone offset in git format: +hhmm or -hhmm
    offset = int(timestamp.astimezone().utcoffset().total_seconds())
    sign = "+" if offset >= 0 else "-"
    hours, minutes = divmod(abs(offset) // 60, 60)
    tz = f"{sign}{hours:02d}{minutes:02d}"
    author = f"{author} {int(timestamp.timestamp())} {tz}"
    commit.kvlm[b"author"] = author.encode("utf8")
    commit.kvlm[b"committer"] = author.encode("utf8")
    commit.kvlm[None] = message.encode("utf8")
    return object_write(commit, repository)

def tag_create(repository, name, ref, create_tag_object=False):
    # a lightweight tag is just a ref; an annotated tag is a tag object the ref points to
    sha = object_find(repository, ref)
    if create_tag_object:
        tag = GitTag()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        tag.kvlm[b'tagger'] = f"Wyag <wyag@example.com> {int(datetime.now().timestamp())} +0000".encode()
        tag.kvlm[None] = b"A tag generated by wyag, which won't let you customize the message!\n"
        tag_sha = object_write(tag, repository)
        refs.ref_create(repository, "tags/" + name, tag_sha)
    else:
        refs.ref_create(repository, "tags/" + name, sha)
