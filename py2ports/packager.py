"""Stage pinned game files and produce checked, independently installable ZIPs."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import stat
import tempfile
import zipfile

from . import __version__
from .builder import build_runtime, runtime_inputs, sha256
from .common import Error, git


def launcher(game, profile):
    template = (game.root / "launcher/game.sh.in").read_text()
    values = {"ID": game.id, "PYTHONLIB": "python" + ".".join(profile["python"].split(".")[:2]),
              "WORKDIR": shlex.quote(game.working_directory), "ENTRYPOINT": shlex.quote(game.entrypoint),
              "ENVIRONMENT": "\n".join(f"export {key}={shlex.quote(value)}" for key, value in sorted(game.environment.items()))}
    for key, value in values.items():
        template = template.replace(f"@{key}@", value)
    return template


def fingerprint(game):
    commit = game.validate_checkout()
    _, _, runtime_key, _ = runtime_inputs(game)
    inputs = {"manifest": sha256(game.manifest), "commit": commit, "runtime": runtime_key,
              "launcher": sha256(game.root / "launcher/game.sh.in"), "platform_version": __version__,
              "packager": sha256(Path(__file__)), "catalog": sha256(Path(__file__).with_name("catalog.py")),
              "notices": sha256(game.root / "THIRD_PARTY_NOTICES.md"),
              "platform_commit": git(game.root, "rev-parse", "HEAD")}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(), commit


def build(game):
    stamp, commit = fingerprint(game)
    runtime, runtime_meta = build_runtime(game)
    destination = game.root / "build/staging" / game.id
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=f".{game.id}-") as temporary:
        stage = Path(temporary) / "stage"
        folder = stage / game.id
        for name, source in game.files().items():
            target = folder / "game" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for name in ("runtime", "data", "cache"):
            (folder / name).mkdir(parents=True, exist_ok=True)
        shutil.copy2(runtime, folder / "runtime/runtime.squashfs")
        (folder / "runtime/runtime.json").write_text(json.dumps(runtime_meta, indent=2) + "\n")
        (folder / "THIRD_PARTY_NOTICES.md").write_text((game.root / "THIRD_PARTY_NOTICES.md").read_text())
        script = stage / f"{game.id}.sh"
        script.write_text(launcher(game, runtime_meta["profile"]))
        script.chmod(0o755)
        provenance = {"schema": 1, "id": game.id, "name": game.name, "version": __version__,
                      "game_commit": commit, "platform_commit": git(game.root, "rev-parse", "HEAD"),
                      "platform_dirty": bool(git(game.root, "status", "--porcelain")),
                      "runtime_key": runtime_meta["key"], "fingerprint": stamp, "publish": game.publish,
                      "entrypoint": game.entrypoint,
                      "checksums": {path.relative_to(stage).as_posix(): sha256(path)
                                    for path in sorted(stage.rglob("*")) if path.is_file()}}
        (folder / "package.json").write_text(json.dumps(provenance, indent=2) + "\n")
        # Remote installation uses only shell tools, not Python, to verify files.
        (folder / "checksums.sha256").write_text("".join(
            f"{digest}  {name}\n" for name, digest in provenance["checksums"].items()))
        if destination.exists():
            shutil.rmtree(destination)
        stage.rename(destination)
    print(f"Built {game.id} at pinned commit {commit[:12]}")
    return destination


def validate_archive(path, game_id):
    """Reject extra roots, traversal, links, duplicate names and altered payloads."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set()
            for info in archive.infolist():
                name = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (info.filename in names or "\\" in info.filename or "\n" in info.filename
                        or name.is_absolute() or ".." in name.parts or not name.parts
                        or name.parts[0] not in (game_id, f"{game_id}.sh")
                        or (name.parts[0] == f"{game_id}.sh" and len(name.parts) != 1)
                        or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                    raise Error(f"Unsafe package member: {info.filename}")
                names.add(info.filename)
            metadata_name = f"{game_id}/package.json"
            metadata = json.loads(archive.read(metadata_name))
            if metadata["id"] != game_id:
                raise Error("Package ID does not match its destination.")
            required = {f"{game_id}.sh", f"{game_id}/runtime/runtime.squashfs",
                        f"{game_id}/game/{metadata['entrypoint']}", f"{game_id}/checksums.sha256"}
            if not required.issubset(names) or not archive.getinfo(f"{game_id}.sh").external_attr >> 16 & 0o111:
                raise Error("Package is missing its entrypoint, runtime, checksum list, or executable launcher.")
            checksums = metadata["checksums"]
            expected = set(checksums) | {metadata_name, f"{game_id}/checksums.sha256"}
            if {name for name in names if not name.endswith("/")} != expected:
                raise Error("Package contains missing or unlisted files.")
            for name, digest in checksums.items():
                with archive.open(name) as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != digest:
                    raise Error(f"Package checksum mismatch: {name}")
            checksum_text = "".join(f"{digest}  {name}\n" for name, digest in checksums.items())
            if archive.read(f"{game_id}/checksums.sha256").decode() != checksum_text:
                raise Error("Package checksum list does not match provenance.")
            with archive.open(f"{game_id}/runtime/runtime.squashfs") as stream:
                if stream.read(4) != b"hsqs":
                    raise Error("Package runtime is not SquashFS.")
            return metadata, sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, TypeError, AttributeError) as exc:
        raise Error(f"Invalid package {path}: {exc}") from exc


def package(game):
    stamp, _ = fingerprint(game)
    output = game.root / "dist" / f"{game.id}.zip"
    if output.is_file():
        try:
            metadata, _ = validate_archive(output, game.id)
            if metadata["fingerprint"] == stamp:
                print(f"Package cache hit: {game.id}")
                return output
        except Error:
            pass
    stage = build(game)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temporary:
        temp = Path(temporary.name)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())
        validate_archive(temp, game.id)
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Packaged {output.name}")
    return output
