"""The portable runtime must preserve the handheld's hardware graphics stack."""
from pathlib import Path
import runpy
import subprocess
import sys


def test_device_graphics_libraries_not_bundled(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "lib").mkdir()
    (runtime / "bin/python").write_bytes(b"\x7fELF")
    libraries = ("libSDL2-2.0.so.0", "libEGL.so.1", "libGLESv2.so.2", "libgbm.so.1", "libdrm.so.2")
    monkeypatch.setattr(sys, "argv", ["bundle-libraries.py", str(runtime)])
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "Machine: AArch64\n")

    def ldd(args, **kwargs):
        assert args[0] == "ldd", "Host graphics libraries must not be copied or queried for Debian sources"
        output = "\n".join(f"{name} => /device/{name} (0x0000)" for name in libraries)
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(subprocess, "run", ldd)
    runpy.run_path(str(Path(__file__).parents[1] / "runtime/bundle-libraries.py"), run_name="__main__")
    assert not list((runtime / "lib").iterdir())
    assert set(libraries).issubset((runtime / "host-libraries.txt").read_text().splitlines())
