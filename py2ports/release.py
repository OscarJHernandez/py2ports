"""Prepare public release artifacts, refusing private game repositories."""
import argparse
import configparser
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.request

from .builder import sha256
from .catalog import discover
from .common import Error, git, run
from .packager import package


def public_repository(url):
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
    if not match:
        raise Error("Public releases currently require a GitHub repository URL without credentials.")
    request = urllib.request.Request(f"https://api.github.com/repos/{match[1]}", headers={"User-Agent": "py2ports-public-release"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            value = json.load(response)
    except (urllib.error.URLError, ValueError) as exc:
        raise Error("Cannot verify public access to a publication-enabled game. No private credentials are used.") from exc
    if value.get("private") is not False or value.get("visibility") != "public":
        raise Error("Refusing to publish a non-public game repository.")
    return f"https://github.com/{match[1]}.git"


def prepare(root, version, output):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?", version):
        raise Error("Release version must be a tag such as v0.1.0.")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise Error("Release output directory must be empty to prevent accidental upload of old/private files.")
    # Produces a public runtime using a synthetic game, never a private game.
    run([sys.executable, root / "tests/runtime_smoke.py", "--output", output], capture=False)
    modules = configparser.ConfigParser(interpolation=None)
    modules.read(root / ".gitmodules")
    records = []
    for game in discover(root):
        if not game.publish:
            print(f"Skipping {game.id}: publication disabled; no private checkout or artifact.")
            continue
        section = next((modules[name] for name in modules.sections() if modules[name].get("path") == game.submodule), None)
        if section is None:
            raise Error(f"Missing .gitmodules entry for {game.id}")
        public_repository(section["url"])
        git(root, "-c", "url.https://github.com/.insteadOf=git@github.com:",
            "submodule", "update", "--init", "--", game.submodule)
        archive = package(game)
        target = output / f"{game.id}-{version}.zip"
        shutil.copy2(archive, target)
        records.append({"id": game.id, "game_commit": game.commit(), "file": target.name, "sha256": sha256(target)})
    (output / "release.json").write_text(json.dumps({"version": version, "platform_commit": git(root, "rev-parse", "HEAD"), "games": records}, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(output.iterdir()) if path.is_file()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=Path("public-artifacts"))
    args = parser.parse_args()
    try:
        prepare(Path.cwd(), args.version, args.output.resolve())
    except Error as exc:
        parser.exit(1, f"py2ports release: {exc}\n")


if __name__ == "__main__":
    main()
