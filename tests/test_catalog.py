import shutil

import pytest

from py2ports.catalog import discover
from py2ports.cli import main, register
from py2ports.common import Error
from py2ports.common import inside
from conftest import add_game, command


def test_genuine_pin_and_clean_checkout(project, tmp_path):
    game = discover(project)[0]
    assert game.validate_checkout() == command(game.repository, "rev-parse", "HEAD")
    assert command(project, "ls-files", "--stage", "games/alpha").startswith("160000 ")
    clone = tmp_path / "clean"
    command(tmp_path, "-c", "protocol.file.allow=always", "clone", "--recurse-submodules", str(project), str(clone))
    assert discover(clone)[0].validate_checkout() == game.commit()


def test_second_independent_layout(project):
    add_game(project, "beta", "application", "play.py")
    games = discover(project)
    assert len(games) == 2
    assert games[1].validate_checkout()
    assert set(games[1].files()) == {"assets/example.txt", "play.py"}


@pytest.mark.parametrize("replacement,expected", [
    ('entrypoint = "../secret.py"', "escapes"),
    ('entrypoint = "missing.py"', "entrypoint"),
])
def test_bad_paths(project, replacement, expected):
    manifest = project / "catalog/alpha.toml"
    manifest.write_text(manifest.read_text().replace('entrypoint = "src/start.py"', replacement))
    with pytest.raises(Error, match=expected):
        discover(project)[0].validate_checkout()


def test_missing_checkout_metadata_only(project):
    shutil.rmtree(project / "games/alpha")
    assert main(["--root", str(project), "validate", "--metadata-only"]) == 0
    with pytest.raises(Error, match="submodule is missing"):
        discover(project)[0].validate_checkout()


def test_dirty_and_wrong_pin(project):
    game = discover(project)[0]
    (game.repository / "src/start.py").write_text("changed\n")
    with pytest.raises(Error, match="dirty"):
        game.validate_checkout()
    command(game.repository, "config", "user.name", "Test")
    command(game.repository, "config", "user.email", "test@example.invalid")
    command(game.repository, "add", ".")
    command(game.repository, "commit", "-m", "change")
    with pytest.raises(Error, match="pinned commit"):
        game.validate_checkout()


def test_unknown_and_malformed(project):
    with pytest.raises(Error, match="Unknown game"):
        discover(project, "absent")
    (project / "catalog/alpha.toml").write_text("not valid = [")
    with pytest.raises(Error, match="invalid manifest"):
        discover(project)


def test_gitlink_requires_gitmodules_registration(project):
    (project / ".gitmodules").unlink()
    with pytest.raises(Error, match=".gitmodules registration"):
        discover(project)[0].commit()


def test_control_characters_rejected_in_paths(project):
    with pytest.raises(Error, match="control characters"):
        inside(project, "src/\0broken.py")


def test_duplicate_id(project):
    (project / "catalog/duplicate.toml").write_text((project / "catalog/alpha.toml").read_text())
    with pytest.raises(Error, match="duplicate"):
        discover(project)


def test_symlink_source_rejected(project, tmp_path):
    repository = project / "games/alpha"
    command(repository, "config", "user.name", "Test")
    command(repository, "config", "user.email", "test@example.invalid")
    (repository / "escape").symlink_to(tmp_path)
    command(repository, "add", ".")
    command(repository, "commit", "-m", "symlink")
    command(project, "add", "games/alpha")
    with pytest.raises(Error, match="regular tracked files"):
        discover(project)[0].validate_checkout()


def test_register_with_https_transport_test_double(project, monkeypatch):
    from py2ports import cli
    original = cli.run
    repository = project.parent / "independent-alpha"

    def substitute(args, **kwargs):
        if "submodule" in args:
            args = ["git", "-c", "protocol.file.allow=always", *args[1:]]
            args[args.index("https://example.invalid/game.git")] = str(repository)
        return original(args, **kwargs)

    monkeypatch.setattr(cli, "run", substitute)
    register(project, "https://example.invalid/game.git", "added", "src/start.py")
    assert discover(project, "added")[0].validate_checkout()
    # Start a new registration only with committed metadata.
    command(project, "add", ".")
    command(project, "commit", "-m", "added game")
    before = (project / ".gitmodules").read_bytes()
    with pytest.raises(Error, match="entrypoint"):
        register(project, "https://example.invalid/game.git", "broken", "missing.py")
    assert (project / ".gitmodules").read_bytes() == before
    assert not (project / "games/broken").exists()
    assert not (project / "catalog/broken.toml").exists()
    assert "games/broken" not in command(project, "ls-files")


@pytest.mark.parametrize("url", ["file:///tmp/game", "https://token@example.com/game", "--bad"])
def test_registration_rejects_unsafe_urls(project, url):
    with pytest.raises(Error):
        register(project, url, "added", "main.py")
