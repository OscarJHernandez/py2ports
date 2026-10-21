from pathlib import Path
import subprocess
import zipfile

import pytest

from py2ports import builder, packager
from py2ports.catalog import discover
from py2ports.common import Error
from conftest import add_game


def test_zip_extract_smoke_and_independent_paths(project, fake_docker, tmp_path):
    add_game(project, "beta", "application", "play.py")
    install = tmp_path / "installed"
    for game in discover(project):
        output = packager.package(game)
        metadata, size = packager.validate_archive(output, game.id)
        assert metadata["game_commit"] == game.commit()
        assert size > 128
        with zipfile.ZipFile(output) as archive:
            archive.extractall(install)
        assert (install / game.id / "game" / game.entrypoint).is_file()
        assert (install / game.id / "game/assets/example.txt").read_text() == "synthetic asset\n"
        assert (install / game.id / "runtime/runtime.squashfs").is_file()
        subprocess.run(["sh", "-n", str(install / f"{game.id}.sh")], check=True)
    assert (install / "alpha/game/src/start.py").is_file()
    assert (install / "beta/game/play.py").is_file()
    # Identical profiles share one runtime, including across independent games.
    assert len([call for call in fake_docker if "run" in call]) == 1


def test_runtime_cache_and_invalidation(project, fake_docker):
    game = discover(project)[0]
    first, meta = builder.build_runtime(game)
    assert builder.build_runtime(game)[0] == first
    assert len([call for call in fake_docker if "run" in call]) == 1
    # A corrupt artifact must never be reused.
    first.write_bytes(b"broken")
    builder.build_runtime(game)
    assert len([call for call in fake_docker if "run" in call]) == 2
    with (project / "runtime/build-runtime.sh").open("a") as stream:
        stream.write("\n# changed builder\n")
    assert builder.build_runtime(game)[1]["key"] != meta["key"]


def test_package_cache_and_launcher_change(project, fake_docker):
    game = discover(project)[0]
    output = packager.package(game)
    stamp = output.stat().st_mtime_ns
    assert packager.package(game).stat().st_mtime_ns == stamp
    with (project / "launcher/game.sh.in").open("a") as stream:
        stream.write("\n# changed launcher\n")
    packager.package(game)
    assert output.stat().st_mtime_ns != stamp


def test_failed_docker_no_cache(project, monkeypatch):
    def fail(*args, **kwargs):
        raise Error("daemon unavailable")
    monkeypatch.setattr(builder, "run", fail)
    with pytest.raises(Error, match="Start Docker"):
        builder.build_runtime(discover(project)[0])
    assert not list((project / "build").glob("**/runtime.json"))


def test_incomplete_build_rejected(project, monkeypatch):
    monkeypatch.setattr(builder, "run", lambda *args, **kwargs: "")
    with pytest.raises(Error, match="valid SquashFS"):
        builder.build_runtime(discover(project)[0])


@pytest.mark.parametrize("member", ["../escape", "/absolute", "another_game/source", "alpha.sh/evil"])
def test_archive_rejects_unsafe_member(project, fake_docker, member):
    output = packager.package(discover(project)[0])
    with zipfile.ZipFile(output, "a") as archive:
        archive.writestr(member, "bad")
    with pytest.raises(Error, match="Unsafe"):
        packager.validate_archive(output, "alpha")


def test_archive_rejects_modified_payload(project, fake_docker, tmp_path):
    output = packager.package(discover(project)[0])
    altered = tmp_path / "altered.zip"
    with zipfile.ZipFile(output) as source, zipfile.ZipFile(altered, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            target.writestr(item, b"altered" if item.filename == "alpha/game/assets/example.txt" else data)
    with pytest.raises(Error, match="checksum mismatch"):
        packager.validate_archive(altered, "alpha")


def test_extra_native_wheel_rejected(tmp_path):
    wheel = tmp_path / "native-1.0-cp312-linux_aarch64.whl"
    wheel.write_bytes(b"placeholder")
    result = subprocess.run(["python3", str(Path(__file__).parents[1] / "runtime/check-wheels.py"), str(tmp_path)], text=True, capture_output=True)
    assert result.returncode != 0
    assert "Unsupported native" in result.stderr
