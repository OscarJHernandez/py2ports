import io
import json
import urllib.error

import pytest

from py2ports import release
from py2ports.common import Error


def test_release_excludes_private_game_even_if_zip_exists(project, tmp_path, monkeypatch):
    (project / "dist").mkdir()
    (project / "dist/alpha.zip").write_bytes(b"private bytes must never upload")
    output = tmp_path / "public"

    def synthetic_runtime(args, **kwargs):
        (output / "runtime.squashfs").write_bytes(b"public synthetic runtime")
        (output / "runtime.json").write_text("{}")

    monkeypatch.setattr(release, "run", synthetic_runtime)
    monkeypatch.setattr(release, "package", lambda *_: pytest.fail("Private game was packaged"))
    monkeypatch.setattr(release, "public_repository", lambda *_: pytest.fail("Private game was accessed"))
    release.prepare(project, "v0.1.0", output)
    assert not list(output.glob("*.zip"))
    assert json.loads((output / "release.json").read_text())["games"] == []
    assert "runtime.squashfs" in (output / "SHA256SUMS").read_text()


def test_release_rejects_existing_output(project, tmp_path):
    (tmp_path / "private.zip").write_bytes(b"private")
    with pytest.raises(Error, match="empty"):
        release.prepare(project, "v0.1.0", tmp_path)


@pytest.mark.parametrize("version", ["main", "v1;echo bad", "../v1", "v1"])
def test_bad_release_version(project, tmp_path, version):
    with pytest.raises(Error, match="version"):
        release.prepare(project, version, tmp_path)


def test_private_repository_never_uses_authentication(monkeypatch):
    def reject(request, **kwargs):
        assert not request.has_header("Authorization")
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
    monkeypatch.setattr(release.urllib.request, "urlopen", reject)
    with pytest.raises(Error, match="public access"):
        release.public_repository("https://github.com/example/private.git")


def test_public_repository_accepted_and_private_denied(monkeypatch):
    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b'{"private": false, "visibility": "public"}'))
    assert release.public_repository("git@github.com:example/game.git") == "https://github.com/example/game.git"
    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b'{"private": true, "visibility": "private"}'))
    with pytest.raises(Error, match="non-public"):
        release.public_repository("https://github.com/example/game.git")


def test_release_includes_two_public_games_and_excludes_private(project, fake_docker, tmp_path, monkeypatch):
    from conftest import add_game, command
    identities = ("py2ports_snake", "py2ports_breakout")
    for identity in identities:
        add_game(project, identity)
        manifest = project / "catalog" / f"{identity}.toml"
        manifest.write_text(manifest.read_text().replace("publish = false", "publish = true"))
    command(project, "add", "catalog")
    command(project, "commit", "-m", "Enable authorized synthetic public games")
    output = tmp_path / "public"
    checked = []

    def synthetic_runtime(args, **kwargs):
        (output / "runtime.squashfs").write_bytes(b"public runtime")
        (output / "runtime.json").write_text("{}")

    monkeypatch.setattr(release, "run", synthetic_runtime)
    monkeypatch.setattr(release, "public_repository", lambda url: checked.append(url) or url)
    release.prepare(project, "v0.1.0", output)
    records = json.loads((output / "release.json").read_text())["games"]
    assert {record["id"] for record in records} == set(identities)
    assert len(checked) == 2
    assert all("alpha" not in url for url in checked)
    assert {path.name for path in output.glob("*.zip")} == {f"{identity}-v0.1.0.zip" for identity in identities}
    for record in records:
        assert release.sha256(output / record["file"]) == record["sha256"]
