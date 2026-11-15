import os

import repo

def ref_resolve(repository, ref):
    # follow symbolic refs, e.g. HEAD -> refs/heads/master -> sha
    path = repo.repo_file(repository, ref)
    if not os.path.isfile(path):
        return None
    with open(path, 'r') as fp:
        data = fp.read()[:-1]
    if data.startswith("ref: "):
        return ref_resolve(repository, data[5:])
    else:
        return data

def ref_list(repository, path=None):
    if not path:
        path = repo.repo_dir(repository, "refs")
    ret = dict()
    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repository, can)
        else:
            ret[f] = ref_resolve(repository, can)
    return ret

def ref_create(repository, ref_name, sha):
    with open(repo.repo_file(repository, "refs/" + ref_name), 'w') as fp:
        fp.write(sha + "\n")

def branch_get_active(repository):
    with open(repo.repo_file(repository, "HEAD"), "r") as f:
        head = f.read()
    if head.startswith("ref: refs/heads/"):
        return(head[16:-1])
    else:
        return False

def show_ref(repository, refs, with_hash=True, prefix=""):
    if prefix:
        prefix = prefix + '/'
    for k, v in refs.items():
        if type(v) == str and with_hash:
            print (f"{v} {prefix}{k}")
        elif type(v) == str:
            print (f"{prefix}{k}")
        else:
            show_ref(repository, v, with_hash=with_hash, prefix=f"{prefix}{k}")
