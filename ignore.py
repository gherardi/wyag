import os
from fnmatch import fnmatch
import index
import objects

class GitIgnore(object):
    absolute = None
    scoped = None
    def __init__(self, absolute, scoped):
        self.absolute = absolute
        self.scoped = scoped

def gitignore_parse1(raw):
    raw = raw.strip()
    if not raw or raw[0] == "#": return None
    elif raw[0] == "!": return (raw[1:], False)
    elif raw[0] == "\\": return (raw[1:], True)
    else: return (raw, True)

def gitignore_parse(lines):
    ret = list()
    for line in lines:
        parsed = gitignore_parse1(line)
        if parsed: ret.append(parsed)
    return ret

def gitignore_read(repository):
    ret = GitIgnore(absolute=list(), scoped=dict())
    repo_file = os.path.join(repository.gitdir, "info/exclude")
    if os.path.exists(repo_file):
        with open(repo_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))
    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_file = os.path.join(config_home, "git/ignore")
    if os.path.exists(global_file):
        with open(global_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))
    idx = index.index_read(repository)
    for entry in idx.entries:
        if entry.name == ".gitignore" or entry.name.endswith("/.gitignore"):
            dir_name = os.path.dirname(entry.name)
            contents = objects.object_read(repository, entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scoped[dir_name] = gitignore_parse(lines)
    return ret

def check_ignore1(rules, path):
    result = None
    for (pattern, value) in rules:
        if fnmatch(path, pattern):
            result = value
    return result

def check_ignore_scoped(rules, path):
    # check ignore rules in .gitignore files from directories up to root
    # rules are ordered by directory depth
    parent = os.path.dirname(path)
    while True:
        if parent in rules:
            result = check_ignore1(rules[parent], path)
            if result != None: return result
        if parent == "": break
        parent = os.path.dirname(parent)
    return None

def check_ignore_absolute(rules, path):
    parent = os.path.dirname(path)
    for ruleset in rules:
        result = check_ignore1(ruleset, path)
        if result != None: return result
    return False

def check_ignore(rules, path):
    # evaluate ignore rules in order: scoped rules (.gitignore files) take precedence
    # this allows subdirectories to override parent ignore patterns
    if os.path.isabs(path):
        raise Exception("This function requires path to be relative to the repository's root")
    result = check_ignore_scoped(rules.scoped, path)
    if result != None: return result
    return check_ignore_absolute(rules.absolute, path)
