"""Content-addressed Docker/SquashFS runtime builds."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
import tomllib

from .common import Error, inside, run


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_inputs(game):
    profile_path = game.root / "runtime" / f"{game.runtime}.toml"
    try:
        profile = tomllib.loads(profile_path.read_text())
        if (profile.get("schema") != 1 or profile["platform"] != "linux/arm64"
                or not isinstance(profile["image"], str)
                or not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", profile["image"])):
            raise Error("Runtime must use linux/arm64 and an image pinned by sha256 digest.")
        for key in ("python", "pygame", "pygame_commit", "debian_snapshot"):
            if not isinstance(profile[key], str):
                raise Error(f"Runtime profile {key} must be text.")
        if not re.fullmatch(r"[0-9a-f]{40}", profile["pygame_commit"]):
            raise Error("Runtime pygame_commit must be a full 40-character Git commit.")
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", profile["debian_snapshot"]):
            raise Error("Runtime debian_snapshot must use YYYYMMDDTHHMMSSZ.")
    except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        raise Error(f"Invalid runtime profile {game.runtime}: {exc}") from exc
    dependency = inside(game.root, game.dependencies) if game.dependencies else None
    if dependency and not dependency.is_file():
        raise Error(f"Missing hash-locked dependencies: {game.dependencies}")
    inputs = {path.name: sha256(path) for path in sorted((game.root / "runtime").iterdir()) if path.is_file()}
    inputs["dependencies"] = sha256(dependency) if dependency else None
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return profile, dependency, key, inputs


def build_runtime(game):
    profile, dependency, key, inputs = runtime_inputs(game)
    destination = game.root / "build" / "runtimes" / key
    runtime = destination / "runtime.squashfs"
    metadata = destination / "runtime.json"
    if runtime.is_file() and metadata.is_file():
        try:
            saved = json.loads(metadata.read_text())
            if saved["key"] == key and saved["sha256"] == sha256(runtime):
                print(f"Runtime cache hit: {key[:12]}")
                return runtime, saved
        except (ValueError, KeyError):
            pass
    try:
        run(["docker", "info", "--format", "{{.ServerVersion}}"])
        run(["docker", "compose", "version"])
    except Error as exc:
        raise Error("Docker is unavailable. Start Docker Desktop (including Compose) and retry. " + str(exc)) from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".runtime-", dir=destination.parent) as temporary:
        temporary = Path(temporary)
        output = temporary / "output"
        output.mkdir()
        requirements = temporary / "requirements.txt"
        requirements.write_bytes(dependency.read_bytes() if dependency else b"")
        environment = dict(os.environ, PY2PORTS_IMAGE=profile["image"],
                           PY2PORTS_PYTHON=profile["python"], PY2PORTS_PYGAME=profile["pygame"],
                           PY2PORTS_PYGAME_COMMIT=profile["pygame_commit"],
                           PY2PORTS_DEBIAN_SNAPSHOT=profile["debian_snapshot"],
                           PY2PORTS_RUNTIME_DIR=str(game.root / "runtime"),
                           PY2PORTS_OUTPUT=str(output), PY2PORTS_REQUIREMENTS=str(requirements))
        print(f"Building ARM64 runtime {key[:12]} (the first build can take several minutes)...", flush=True)
        run(["docker", "compose", "-p", f"py2ports-{key[:12]}", "-f", game.root / "runtime/compose.yml",
             "run", "--rm", "-T", "builder"], env=environment, capture=False)
        built = output / "runtime.squashfs"
        if not built.is_file() or built.stat().st_size < 96:
            raise Error("Docker did not produce a valid SquashFS runtime; inspect build output.")
        with built.open("rb") as stream:
            if stream.read(4) != b"hsqs":
                raise Error("Docker did not produce a valid SquashFS runtime; inspect build output.")
        saved = {"key": key, "sha256": sha256(built), "profile": profile, "inputs": inputs}
        (output / "runtime.json").write_text(json.dumps(saved, indent=2) + "\n")
        if destination.exists():
            shutil.rmtree(destination)
        output.rename(destination)
    return runtime, saved
