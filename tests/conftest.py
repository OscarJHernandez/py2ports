"""Synthetic games are created as independent Git repositories, never copied from private games."""
from pathlib import Path
import shutil
import subprocess

import pytest

PLATFORM = Path(__file__).resolve().parents[1]


def command(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def initialize(path):
    path.mkdir(parents=True, exist_ok=True)
    command(path, "init", "-b", "main")
    command(path, "config", "user.name", "Synthetic Test")
    command(path, "config", "user.email", "tests@example.invalid")


def make_project(base):
    root = base / "platform"
    initialize(root)
    for folder in ("runtime", "launcher"):
        shutil.copytree(PLATFORM / folder, root / folder)
    shutil.copy2(PLATFORM / "THIRD_PARTY_NOTICES.md", root)
    (root / "catalog").mkdir()
    command(root, "add", ".")
    command(root, "commit", "-m", "Synthetic platform")
    return root


def add_game(root, identity="alpha", source=".", entrypoint="src/start.py"):
    repository = root.parent / f"independent-{identity}"
    initialize(repository)
    game_root = repository / source
    (game_root / Path(entrypoint).parent).mkdir(parents=True, exist_ok=True)
    (game_root / entrypoint).write_text("print('synthetic game')\n")
    (game_root / "assets").mkdir()
    (game_root / "assets/example.txt").write_text("synthetic asset\n")
    command(repository, "add", ".")
    command(repository, "commit", "-m", "Independent synthetic game")
    command(root, "-c", "protocol.file.allow=always", "submodule", "add", str(repository), f"games/{identity}")
    (root / "catalog" / f"{identity}.toml").write_text(
        f'schema = 1\nid = "{identity}"\nname = "{identity.title()}"\nsubmodule = "games/{identity}"\n'
        f'source = "{source}"\ninclude = ["."]\nentrypoint = "{entrypoint}"\n'
        'working_directory = "."\nruntime = "knulli-arm64"\npublish = false\n')
    command(root, "add", ".gitmodules", f"games/{identity}", "catalog")
    command(root, "commit", "-m", f"Register {identity}")
    return repository


@pytest.fixture
def project(tmp_path):
    root = make_project(tmp_path)
    add_game(root)
    return root


@pytest.fixture
def fake_docker(monkeypatch):
    from py2ports import builder
    calls = []

    def fake(args, **kwargs):
        calls.append(args)
        if "run" in args:
            (Path(kwargs["env"]["PY2PORTS_OUTPUT"]) / "runtime.squashfs").write_bytes(b"hsqs" + b"\0" * 124)
        return "Docker test double"

    monkeypatch.setattr(builder, "run", fake)
    return calls
