"""Command-line entrypoint and safe registration of independent submodules."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse

from . import __version__
from .catalog import ID, discover, load
from .common import Error, git, inside, run


def register(root, url, name, entrypoint, source="."):
    if not ID.fullmatch(name):
        raise Error("Game name must use lowercase letters, digits, hyphens, and underscores.")
    if not (url.startswith("https://") or url.startswith("ssh://") or url.startswith("git@")):
        raise Error("Use an HTTPS or SSH repository URL without embedded passwords/tokens.")
    parsed = urllib.parse.urlsplit(url)
    if ("\n" in url or "\r" in url or parsed.password or parsed.query or parsed.fragment
            or (url.startswith("https://") and parsed.username)):
        raise Error("Repository URLs must not contain credentials or newlines.")
    path = root / "games" / name
    manifest = root / "catalog" / f"{name}.toml"
    if path.exists() or manifest.exists():
        raise Error(f"{name} already exists; choose a different name.")
    gitdir = Path(git(root, "rev-parse", "--absolute-git-dir")) / "modules/games" / name
    if gitdir.exists():
        raise Error(f"Git metadata for {name} already exists. Inspect it or choose a different name; it will not be deleted.")
    inside(path, source)
    inside(inside(path, source), entrypoint)
    if git(root, "status", "--porcelain", "--", ".gitmodules", f"games/{name}", f"catalog/{name}.toml"):
        raise Error("Commit existing submodule metadata changes before registering another game.")
    # JSON strings are valid TOML basic strings for these path values.
    import json
    def quoted(value):
        return json.dumps(value, ensure_ascii=False)
    text = (f'schema = 1\nid = {quoted(name)}\nname = {quoted(name)}\nsubmodule = "games/{name}"\n'
            f'source = {quoted(source)}\ninclude = ["."]\nentrypoint = {quoted(entrypoint)}\n'
            'working_directory = "."\nruntime = "knulli-arm64"\npublish = false\n')
    original_modules = (root / ".gitmodules").read_bytes() if (root / ".gitmodules").exists() else None
    try:
        run(["git", "-C", root, "submodule", "add", "--", url, f"games/{name}"])
        manifest.parent.mkdir(exist_ok=True)
        manifest.write_text(text)
        load(root, manifest).validate_checkout()
    except (Error, OSError):
        import shutil
        subprocess.run(["git", "-C", str(root), "submodule", "deinit", "-f", "--", f"games/{name}"], capture_output=True)
        subprocess.run(["git", "-C", str(root), "rm", "--cached", "-f", "--", f"games/{name}"], capture_output=True)
        shutil.rmtree(path, ignore_errors=True)
        manifest.unlink(missing_ok=True)
        modules = root / ".gitmodules"
        if original_modules is None:
            modules.unlink(missing_ok=True)
            subprocess.run(["git", "-C", str(root), "rm", "--cached", "-f", "--ignore-unmatch", ".gitmodules"], capture_output=True)
        else:
            modules.write_bytes(original_modules)
            git(root, "add", ".gitmodules")
        # Remove only this newly-created module's private Git directory.
        shutil.rmtree(gitdir, ignore_errors=True)
        raise
    print(f"Registered {name}. Review {manifest.relative_to(root)} include paths and commit the manifest, .gitmodules, and gitlink.")


def parser():
    value = argparse.ArgumentParser(description="Build standalone games for ARM64 Knulli handhelds.")
    value.add_argument("--version", action="version", version=__version__)
    value.add_argument("--root", type=Path, help="Superproject root (otherwise discovered from current directory)")
    sub = value.add_subparsers(dest="command", required=True)
    for command in ("list", "validate", "build", "package", "deploy", "check-device"):
        item = sub.add_parser(command)
        if command != "check-device":
            item.add_argument("--game")
        if command == "validate":
            item.add_argument("--metadata-only", action="store_true", help="Validate manifests/gitlinks without accessing private checkouts")
        if command in ("deploy", "check-device"):
            item.add_argument("--host", default=os.environ.get("DEVICE_HOST", "knulli"))
            item.add_argument("--user", default=os.environ.get("DEVICE_USER", "root"))
            item.add_argument("--port", type=int, default=os.environ.get("DEVICE_PORT") or None)
    item = sub.add_parser("add")
    item.add_argument("repository_url")
    item.add_argument("--name", required=True)
    item.add_argument("--entrypoint", required=True)
    item.add_argument("--source", default=".")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "check-device":
            from .deployer import Device
            with Device(args.host, args.user, args.port) as device:
                device.check()
            return 0
        root = args.root.resolve() if args.root else Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
        if args.command == "add":
            register(root, args.repository_url, args.name, args.entrypoint, args.source)
            return 0
        games = discover(root, args.game)
        if args.command == "list":
            for game in games:
                print(f"{game.id}\t{game.name}\t{'publication enabled' if game.publish else 'local/private packages only'}")
        elif args.command == "validate":
            for game in games:
                game.commit() if args.metadata_only else game.validate_checkout()
                print(f"Valid: {game.id}" + (" (metadata only; checkout not tested)" if args.metadata_only else ""))
        elif args.command in ("build", "package"):
            from .packager import build, package
            for game in games:
                (build if args.command == "build" else package)(game)
        elif args.command == "deploy":
            from .deployer import deploy
            deploy(root, games, args.game, host=args.host, user=args.user, port=args.port)
        return 0
    except (Error, OSError) as exc:
        print(f"py2ports: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
