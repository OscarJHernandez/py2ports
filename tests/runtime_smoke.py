"""Real ARM64 runtime/package verification using only a synthetic game."""
import argparse
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from py2ports.builder import build_runtime, runtime_inputs
from py2ports.catalog import discover
from py2ports.common import run
from py2ports.packager import package, validate_archive
from conftest import add_game, make_project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Export only the public runtime and its provenance")
    args = parser.parse_args()
    platform = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="py2ports-smoke-") as temporary:
        root = make_project(Path(temporary))
        add_game(root, "synthetic", source="app", entrypoint="start.py")
        # A local cache is shared with ordinary builds. Public CI never has any
        # private runtime cache mounted or credentials for private repositories.
        (root / "build").mkdir()
        cache = platform / "build/runtimes"
        cache.mkdir(parents=True, exist_ok=True)
        (root / "build/runtimes").symlink_to(cache, target_is_directory=True)
        game = discover(root)[0]
        archive = package(game)
        metadata, _ = validate_archive(archive, game.id)
        with zipfile.ZipFile(archive) as contents:
            installed = root / "extracted"
            contents.extractall(installed)
        assert (installed / "synthetic/game/assets/example.txt").is_file()
        runtime, provenance = build_runtime(game)
        before = runtime.stat().st_mtime_ns
        assert build_runtime(game)[0].stat().st_mtime_ns == before
        profile, _, _, _ = runtime_inputs(game)
        # The production builder already imports from the extracted SquashFS.
        # Independently extract it here and run the bundled interpreter again.
        run(["docker", "run", "--rm", "--platform", "linux/arm64", "-v", f"{runtime.parent}:/input:ro",
             profile["image"], "bash", "-ec",
             "apt-get update -qq && apt-get install -y -qq squashfs-tools libsdl2-2.0-0 >/dev/null && "
             "unsquashfs -d /runtime /input/runtime.squashfs >/dev/null && "
             "PYTHONHOME=/runtime LD_LIBRARY_PATH=/runtime/lib SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy "
             "/runtime/bin/python -c 'import pygame, platform; assert platform.machine() == \"aarch64\"; "
             "pygame.init(); pygame.display.set_mode((8,8)); pygame.mixer.init(); "
             "pygame.mixer.Sound(buffer=bytes(128)); pygame.font.Font(None,12).render(\"ok\",True,(255,255,255)); "
             "pygame.quit(); print(\"ARM64 pygame display, audio buffer, and font smoke passed\")'"], capture=False)
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            shutil.copy2(runtime, args.output / "runtime.squashfs")
            shutil.copy2(runtime.parent / "runtime.json", args.output / "runtime.json")
        print(f"PASS: real ARM64 runtime, synthetic package extraction, pygame display, and cache reuse ({provenance['key'][:12]})")


if __name__ == "__main__":
    main()
