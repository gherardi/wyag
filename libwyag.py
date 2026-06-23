import argparse
import sys
import os
import pwd
import grp
from datetime import datetime

import repo
import objects
import index
import ignore
import refs
import status

def cmd_init(args):
    repo.repo_create(args.path)

def cmd_cat_file(args):
    repository = repo.repo_find()
    # object data serialized to stdout
    obj = objects.object_read(repository, objects.object_find(repository, args.object, fmt=args.type.encode()))
    sys.stdout.buffer.write(obj.serialize())

def cmd_log(args):
    repository = repo.repo_find()
    print("digraph wyaglog{")
    print("  node[shape=rect]")
    objects.log_graphviz(repository, objects.object_find(repository, args.commit), set())
    print("}")

def cmd_hash_object(args):
    if args.write:
        repository = repo.repo_find()
    else:
        repository = None
    with open(args.path, "rb") as fd:
        sha = objects.object_hash(fd, args.type.encode(), repository)
        print(sha)

def cmd_ls_tree(args):
    repository = repo.repo_find()
    objects.ls_tree(repository, args.tree, args.recursive)

def cmd_checkout(args):
    repository = repo.repo_find()
    # resolve to a tree, following annotated tags and commits
    obj = objects.object_read(repository, objects.object_find(repository, args.commit, fmt=b'tree'))

    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception(f"Not a directory {args.path}!")
        if os.listdir(args.path):
            raise Exception(f"Not empty {args.path}!")
    else:
        os.makedirs(args.path)
    
    objects.tree_checkout(repository, obj, os.path.realpath(args.path))

def cmd_show_ref(args):
    repository = repo.repo_find()
    rfs = refs.ref_list(repository)
    refs.show_ref(repository, rfs, prefix="refs")

def cmd_tag(args):
    repository = repo.repo_find()
    if args.name:
        refs.tag_create(repository, args.name, args.object, create_tag_object=args.create_tag_object)
    else:
        rfs = refs.ref_list(repository)
        refs.show_ref(repository, rfs["tags"], with_hash=False)

def cmd_rev_parse(args):
    if args.type:
        fmt = args.type.encode()
    else:
        fmt = None
    repository = repo.repo_find()
    print(objects.object_find(repository, args.name, fmt, follow=True))

def cmd_ls_files(args):
    repository = repo.repo_find()
    idx = index.index_read(repository)
    if args.verbose:
        print(f"Index file format v{idx.version}, containing {len(idx.entries)} entries.")
    
    for e in idx.entries:
        print(e.name)
        if args.verbose:
            entry_type = {0b1000: "regular file", 0b1010: "symlink", 0b1110: "git link"}[e.mode_type]
            print(f"  {entry_type} with perms: {e.mode_perms:o}")
            print(f"  on blob: {e.sha}")
            print(f"  created: {datetime.fromtimestamp(e.ctime[0])}.{e.ctime[1]}, modified: {datetime.fromtimestamp(e.mtime[0])}.{e.mtime[1]}")
            print(f"  device: {e.dev}, inode: {e.ino}")
            print(f"  user: {pwd.getpwuid(e.uid).pw_name} ({e.uid})  group: {grp.getgrgid(e.gid).gr_name} ({e.gid})")
            print(f"  flags: stage={e.flag_stage} assume_valid={e.flag_assume_valid}")

def cmd_check_ignore(args):
    repository = repo.repo_find()
    rules = ignore.gitignore_read(repository)
    for path in args.path:
        if ignore.check_ignore(rules, path):
            print(path)

def cmd_status_branch(repository):
    branch = refs.branch_get_active(repository)
    if branch:
        print(f"On branch {branch}.")
    else:
        print(f"HEAD detached at {objects.object_find(repository, 'HEAD')}")

def render_status(st):
    # render a WorktreeStatus value; all classification lives in the status module
    print("Changes to be committed:")
    for name in st.staged_modified:
        print("  modified:", name)
    for name in st.staged_added:
        print("  added:   ", name)
    for name in st.staged_deleted:
        print("  deleted: ", name)
    print()
    print("Changes not staged for commit:")
    for name in st.unstaged_modified:
        print("  modified:", name)
    for name in st.unstaged_deleted:
        print("  deleted: ", name)
    print()
    print("Untracked files:")
    for f in st.untracked:
        print(" ", f)

def cmd_status(_):
    repository = repo.repo_find()
    idx = index.index_read(repository)
    cmd_status_branch(repository)
    render_status(status.compute(repository, idx))

def cmd_rm(args):
    repository = repo.repo_find()
    index.rm(repository, args.path)

def cmd_add(args):
    repository = repo.repo_find()
    index.add(repository, args.path)

def cmd_commit(args):
    repository = repo.repo_find()
    idx = index.index_read(repository)
    if not status.compute(repository, idx).has_staged_changes:
        print("nothing to commit")
        return
    tree = index.tree_from_index(repository, idx)
    commit = objects.commit_create(repository, tree, refs.ref_resolve(repository, "HEAD"), repo.gitconfig_user_get(repo.gitconfig_read()), datetime.now(), args.message)
    active_branch = refs.branch_get_active(repository)
    if active_branch:
        refs.ref_create(repository, "heads/" + active_branch, commit)
    else:
        with open(repo.repo_file(repository, "HEAD"), "w") as fd:
            fd.write(commit + "\n")

def main():
    argparser = argparse.ArgumentParser(description="wyag - the stupidest content tracker")
    argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
    argsubparsers.required = True
    
    argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")
    argsp.add_argument("path", metavar="directory", nargs="?", default=".", help="Where to create the repository.")

    argsp = argsubparsers.add_parser("cat-file", help="Provide content of repository objects")
    argsp.add_argument("type", metavar="type", choices=["blob", "commit", "tag", "tree"], help="Specify the type")
    argsp.add_argument("object", metavar="object", help="The object to display")

    argsp = argsubparsers.add_parser("hash-object", help="Compute object ID and optionally creates a blob from a file")
    argsp.add_argument("-t", metavar="type", dest="type", choices=["blob", "commit", "tag", "tree"], default="blob", help="Specify the type")
    argsp.add_argument("-w", dest="write", action="store_true", help="Actually write the object into the database")
    argsp.add_argument("path", help="Read object from <file>")

    argsp = argsubparsers.add_parser("log", help="Display history of a given commit.")
    argsp.add_argument("commit", default="HEAD", nargs="?", help="Commit to start at.")

    argsp = argsubparsers.add_parser("ls-tree", help="Pretty-print a tree object.")
    argsp.add_argument("-r", dest="recursive", action="store_true", help="Recurse into sub-trees")
    argsp.add_argument("tree", help="A tree-ish object.")

    argsp = argsubparsers.add_parser("checkout", help="Checkout a commit inside of a directory.")
    argsp.add_argument("commit", help="The commit or tree to checkout.")
    argsp.add_argument("path", help="The EMPTY directory to checkout on.")

    argsp = argsubparsers.add_parser("show-ref", help="List references.")

    argsp = argsubparsers.add_parser("tag", help="List and create tags")
    argsp.add_argument("-a", action="store_true", dest="create_tag_object", help="Whether to create a tag object")
    argsp.add_argument("name", nargs="?", help="The new tag's name")
    argsp.add_argument("object", default="HEAD", nargs="?", help="The object the new tag will point to")

    argsp = argsubparsers.add_parser("rev-parse", help="Parse revision (or other objects) identifiers")
    argsp.add_argument("--wyag-type", metavar="type", dest="type", choices=["blob", "commit", "tag", "tree"], default=None, help="Specify the expected type")
    argsp.add_argument("name", help="The name to parse")

    argsp = argsubparsers.add_parser("ls-files", help="List all the stage files")
    argsp.add_argument("--verbose", action="store_true", help="Show everything.")

    argsp = argsubparsers.add_parser("check-ignore", help="Check path(s) against ignore rules.")
    argsp.add_argument("path", nargs="+", help="Paths to check")

    argsp = argsubparsers.add_parser("status", help="Show the working tree status.")

    argsp = argsubparsers.add_parser("rm", help="Remove files from the working tree and the index.")
    argsp.add_argument("path", nargs="+", help="Files to remove")

    argsp = argsubparsers.add_parser("add", help="Add files contents to the index.")
    argsp.add_argument("path", nargs="+", help="Files to add")

    argsp = argsubparsers.add_parser("commit", help="Record changes to the repository.")
    argsp.add_argument("-m", metavar="message", dest="message", help="Message to associate with this commit.")

    args = argparser.parse_args()

    match args.command:
        case "add"          : cmd_add(args)
        case "cat-file"     : cmd_cat_file(args)
        case "check-ignore" : cmd_check_ignore(args)
        case "checkout"     : cmd_checkout(args)
        case "commit"       : cmd_commit(args)
        case "hash-object"  : cmd_hash_object(args)
        case "init"         : cmd_init(args)
        case "log"          : cmd_log(args)
        case "ls-files"     : cmd_ls_files(args)
        case "ls-tree"      : cmd_ls_tree(args)
        case "rev-parse"    : cmd_rev_parse(args)
        case "rm"           : cmd_rm(args)
        case "show-ref"     : cmd_show_ref(args)
        case "status"       : cmd_status(args)
        case "tag"          : cmd_tag(args)
        case _              : print("Bad command.")
