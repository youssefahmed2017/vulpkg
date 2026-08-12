"""Vulp CLI - Command-line interface."""
import argparse
import sys
import os

from .core import VulpCore
from .config import VULP_DIR, CONFIG_FILE


def main():
    parser = argparse.ArgumentParser(
        prog="vulp",
        description="Package manager for the Vulpin programming language",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a new Vulpin package")
    p_init.add_argument("--name", default=None, help="Package name")

    # add
    p_add = sub.add_parser("add", help="Add a dependency")
    p_add.add_argument("package", help="Package name (e.g., 'user/repo' or 'repo')")
    p_add.add_argument("--version", "-v", default="latest", help="Version or tag")

    # install
    p_install = sub.add_parser("install", help="Install dependencies from vulpin.toml")
    p_install.add_argument("--no-cache", action="store_true", help="Skip local cache")

    # remove
    p_remove = sub.add_parser("remove", help="Remove a dependency")
    p_remove.add_argument("package", help="Package name")

    # list
    p_list = sub.add_parser("list", help="List installed dependencies")

    # search
    p_search = sub.add_parser("search", help="Search local package index")
    p_search.add_argument("query", nargs="?", default="", help="Search query")

    # update
    p_update = sub.add_parser("update", help="Update local package index from GitHub")

    # publish
    p_publish = sub.add_parser("publish", help="Publish current package to GitHub Releases")
    p_publish.add_argument("--tag", "-t", required=True, help="Release tag (e.g., v1.0.0)")
    p_publish.add_argument("--token", "-k", default=None, help="GitHub personal access token")

    # run
    p_run = sub.add_parser("run", help="Run a Vulpin file with dependencies")
    p_run.add_argument("file", help="Vulpin source file")

    # cache
    p_cache = sub.add_parser("cache", help="Cache management")
    p_cache_sub = p_cache.add_subparsers(dest="cache_cmd", required=True)
    p_cache_sub.add_parser("clear", help="Clear local cache")
    p_cache_sub.add_parser("list", help="List cached packages")

    args = parser.parse_args()
    core = VulpCore()

    if args.cmd == "init":
        core.init(args.name)
    elif args.cmd == "add":
        core.add(args.package, args.version)
    elif args.cmd == "install":
        core.install(skip_cache=args.no_cache)
    elif args.cmd == "remove":
        core.remove(args.package)
    elif args.cmd == "list":
        core.list_deps()
    elif args.cmd == "search":
        core.search(args.query)
    elif args.cmd == "update":
        core.update_index()
    elif args.cmd == "publish":
        core.publish(args.tag, args.token)
    elif args.cmd == "run":
        core.run(args.file)
    elif args.cmd == "cache":
        if args.cache_cmd == "clear":
            core.cache_clear()
        elif args.cache_cmd == "list":
            core.cache_list()


if __name__ == "__main__":
    main()
