"""Package, ARM64-test and locally install only the two explicitly public games.

No SSH or physical device is used. Run with the development environment and
Docker; CI initializes these two public submodules explicitly, never all games.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from py2ports.builder import build_runtime, runtime_inputs, sha256
from py2ports.catalog import discover
from py2ports.common import git, run
from py2ports.deployer import INSTALL
from py2ports.packager import package, validate_archive

GAMES = ("py2ports_snake", "py2ports_breakout")


def simulated_installs(archives, temporary):
    """Execute the production install script, substituting local files for SSH."""
    ports = temporary / "ports"
    ports.mkdir()
    tools = temporary / "tools"
    tools.mkdir()
    if not shutil.which("sha256sum"):
        checksum = tools / "sha256sum"
        checksum.write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n')
        checksum.chmod(0o755)
    move = tools / "mv"
    move.write_text('#!/bin/sh\ncase "$1" in */extracted/"$PY2PORTS_TEST_FAIL_ID".sh) exit 1;; esac\nexec /bin/mv "$@"\n')
    move.chmod(0o755)
    other = ports / "unrelated"
    other.mkdir()
    (other / "save.txt").write_text("untouched")

    def install(identity, archive, fail=False):
        stage = Path(tempfile.mkdtemp(prefix=f".py2ports-{identity}.", dir=ports))
        shutil.copyfile(archive, stage / "package.zip")
        environment = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}",
                           PY2PORTS_TEST_FAIL_ID=identity if fail else "none")
        result = subprocess.run(["sh", "-s", "--", identity, str(stage), sha256(archive)],
                                input=f"PORTS={shlex.quote(str(ports))}\n" + INSTALL,
                                text=True, capture_output=True, env=environment)
        assert (result.returncode != 0) == fail, result.stdout + result.stderr
        assert not stage.exists(), "Installation left a staging directory"

    for identity, archive in archives.items():
        install(identity, archive)
        # The launcher creates data/ on first play; ZIPs omit empty directories.
        (ports / identity / "data").mkdir(exist_ok=True)
        (ports / identity / "data/save.txt").write_text(identity + " saved progress")
        (ports / identity / "old-version.txt").write_text("previous installation")
    for identity, archive in archives.items():
        install(identity, archive)
        assert (ports / identity / "data/save.txt").read_text() == identity + " saved progress"
        assert not (ports / identity / "old-version.txt").exists()
        assert list(ports.glob(f".py2ports-backup-{identity}-*/{identity}/old-version.txt"))
    before = {identity: sha256(ports / f"{identity}.sh") for identity in archives}
    install(GAMES[0], archives[GAMES[0]], fail=True)
    for identity in archives:
        assert sha256(ports / f"{identity}.sh") == before[identity]
        assert (ports / identity / "data/save.txt").read_text() == identity + " saved progress"
    assert (other / "save.txt").read_text() == "untouched"
    print("PASS: both actual ZIPs install/upgrade independently; saves, backups and rollback preserved")


def main():
    root = Path(__file__).resolve().parents[1]
    archives = {}
    runtime = None
    profile = None
    keys = set()
    with tempfile.TemporaryDirectory(prefix="py2ports-public-games-") as directory:
        temporary = Path(directory)
        game_files = temporary / "games"
        game_files.mkdir()
        for identity in GAMES:
            game = discover(root, identity)[0]
            assert game.publish
            runtime, metadata = build_runtime(game)
            before = runtime.stat().st_mtime_ns
            archive = package(game)
            provenance, _ = validate_archive(archive, identity)
            assert build_runtime(game)[0].stat().st_mtime_ns == before
            keys.add(provenance["runtime_key"])
            assert provenance["checksums"][f"{identity}/runtime/runtime.squashfs"] == sha256(runtime)
            origin = json.loads((game.repository / "TEMPLATE_ORIGIN.json").read_text())
            assert git(game.repository, "rev-list", "--max-parents=0", "HEAD") == origin["generated_root"]
            assert git(game.repository, "rev-parse", origin["generated_root"] + "^{tree}") == origin["initial_tree"]
            with zipfile.ZipFile(archive) as contents:
                required = [f"{identity}/game/{name}" for name in
                            ("src/run.py", "src/main.py", "src/app.py", "assets/README.md", "LICENSE", "TEMPLATE_ORIGIN.json")]
                assert set(required).issubset(contents.namelist())
                assert "MIT License" in contents.read(f"{identity}/game/LICENSE").decode()
                for member in contents.infolist():
                    if member.filename.startswith(f"{identity}/game/"):
                        contents.extract(member, game_files)
            archives[identity] = archive
            profile, _, _, _ = runtime_inputs(game)
        assert len(keys) == 1, "Games did not share the unchanged runtime"
        # Extract the shared cached runtime once. All device libraries used here
        # come from the container; this does not establish Knulli graphics support.
        arguments = ["docker", "run", "--rm", "--platform", "linux/arm64",
                     "-v", f"{runtime.parent}:/input:ro", "-v", f"{game_files}:/games:ro"]
        for identity in GAMES:
            arguments += ["-v", f"{root / 'games' / identity}:/checks/{identity}:ro"]
        script = ("set -eu\napt-get update -qq\n"
                  "apt-get install -y -qq squashfs-tools libsdl2-2.0-0 >/dev/null\n"
                  "unsquashfs -d /runtime /input/runtime.squashfs >/dev/null\n"
                  "export PYTHONHOME=/runtime LD_LIBRARY_PATH=/runtime/lib\n"
                  "export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYGAME_HIDE_SUPPORT_PROMPT=1\n"
                  "/runtime/bin/python -c 'import platform; assert platform.machine() == \"aarch64\"'\n")
        for identity in GAMES:
            script += f"/runtime/bin/python /games/{identity}/game/src/run.py --smoke-test\n"
            script += f"/runtime/bin/python -m unittest discover -s /checks/{identity}/tests\n"
        run([*arguments, profile["image"], "bash", "-ec", script], capture=False)
        simulated_installs(archives, temporary)
        checksums = root / "dist/public-games-SHA256SUMS"
        checksums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in archives.values()))
    print(f"PASS: both public games, actual ARM64 entrypoints, licenses, ZIPs and shared runtime {next(iter(keys))[:12]}")


if __name__ == "__main__":
    main()
