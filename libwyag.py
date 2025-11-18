import argparse
import configparser
from datetime import datetime
import grp, pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

# argparse library documentation: https://docs.python.org/3/library/argparse.html
# create the main parser for arguments
argparser = argparse.ArgumentParser(description="The stupidest content tracker")

# add subparser to catch commands and make it mandatory
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

# process and validate commands
def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        # case "add"          : cmd_add(args)
        # case "cat-file"     : cmd_cat_file(args)
        # case "check-ignore" : cmd_check_ignore(args)
        # case "checkout"     : cmd_checkout(args)
        # case "commit"       : cmd_commit(args)
        # case "hash-object"  : cmd_hash_object(args)
        # case "init"         : cmd_init(args)
        # case "log"          : cmd_log(args)
        # case "ls-files"     : cmd_ls_files(args)
        # case "ls-tree"      : cmd_ls_tree(args)
        # case "rev-parse"    : cmd_rev_parse(args)
        # case "rm"           : cmd_rm(args)
        # case "show-ref"     : cmd_show_ref(args)
        # case "status"       : cmd_status(args)
        # case "tag"          : cmd_tag(args)
        case _              : print("Bad command.")