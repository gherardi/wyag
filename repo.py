import os
import configparser

class GitRepository(object):
    """
    Representation of a Git repository: holds worktree, gitdir, and configuration.
    """
    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git repository {path}")
        
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")
        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatversion: {vers}")

def repo_path(repository, *path):
    """
    Compute path under repository's gitdir ensuring no path traversal occurs.
    """
    destination = os.path.join(repository.gitdir, *path)
    destination = os.path.abspath(destination)
    gitdir_abs = os.path.abspath(repository.gitdir)

    # path traversal security check: ensure destination stays within gitdir
    if not destination.startswith(gitdir_abs):
        raise Exception(f"Potential Path Traversal Detected: {destination} is outside {gitdir_abs}")
    
    return destination

def repo_file(repository, *path, mkdir=False):
    if repo_dir(repository, *path[:-1], mkdir=mkdir):
        return repo_path(repository, *path)
    
def repo_dir(repository, *path, mkdir=False):
    path = repo_path(repository, *path)
    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception(f"Not a directory {path}")
    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None

def repo_create(path):
    repo = GitRepository(path, True)
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception (f"{path} is not a directory!")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception (f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", "tags", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)

    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo

def repo_default_config():
    ret = configparser.ConfigParser()
    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")
    return ret

def repo_find(path=".", required=True):
    # search upward through directory tree for .git folder
    # allows commands to work from any subdirectory in the repository
    path = os.path.realpath(path)
    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)
    parent = os.path.realpath(os.path.join(path, ".."))
    if parent == path:
        if required:
            raise Exception("No git directory.")
        else:
            return None
    return repo_find(parent, required)

def gitconfig_read():
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    configfiles = [
        os.path.expanduser(os.path.join(xdg_config_home, "git/config")),
        os.path.expanduser("~/.gitconfig")
    ]
    config = configparser.ConfigParser()
    config.read(configfiles)
    return config

def gitconfig_user_get(config):
    if "user" in config:
        if "name" in config["user"] and "email" in config["user"]:
            return f"{config['user']['name']} <{config['user']['email']}>"
    return None

def ref_resolve(repository, ref):
    # recursively dereference symbolic refs (refs that point to other refs)
    # this allows HEAD -> refs/heads/master -> commit-sha chain
    path = repo_file(repository, ref)
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
        path = repo_dir(repository, "refs")
    ret = dict()
    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repository, can)
        else:
            ret[f] = ref_resolve(repository, can)
    return ret

def ref_create(repository, ref_name, sha):
    with open(repo_file(repository, "refs/" + ref_name), 'w') as fp:
        fp.write(sha + "\n")

def branch_get_active(repository):
    with open(repo_file(repository, "HEAD"), "r") as f:
        head = f.read()
    if head.startswith("ref: refs/heads/"):
        return(head[16:-1])
    else:
        return False
