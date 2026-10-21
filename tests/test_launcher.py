import os
import signal
import subprocess
import time

import pytest

from py2ports.catalog import discover
from py2ports.packager import launcher


@pytest.mark.parametrize("failure,expected", [("", 0), ("mount", 1), ("python", 7)])
def test_launcher_paths_and_cleanup(project, tmp_path, failure, expected):
    install = tmp_path / "path with spaces"
    (install / "alpha/game/src").mkdir(parents=True)
    (install / "alpha/runtime").mkdir()
    (install / "alpha/game/src/start.py").write_text("# fixture\n")
    script = install / "alpha.sh"
    script.write_text(launcher(discover(project)[0], {"python": "3.12.8"}))
    tools = tmp_path / "tools"
    tools.mkdir()
    trace = tmp_path / "trace"
    stubs = {
        "uname": "echo aarch64\n",
        "mount": 'echo mount >> "$TRACE"\n[ "$FAIL" != mount ] || exit 1\nfor item in "$@"; do target=$item; done\nmkdir -p "$target/bin"\ncp "$TOOLS/python" "$target/bin/python"\n',
        "umount": 'echo umount >> "$TRACE"\n',
        "python": 'echo "$PWD|$1|$PYTHONHOME|$PY2PORTS_DATA_DIR" >> "$TRACE"\n[ "$FAIL" != python ] || exit 7\n',
    }
    for name, content in stubs.items():
        path = tools / name
        path.write_text("#!/bin/sh\n" + content)
        path.chmod(0o755)
    environment = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", TRACE=str(trace), TOOLS=str(tools), FAIL=failure)
    result = subprocess.run(["sh", str(script)], cwd=tmp_path, env=environment)
    assert result.returncode == expected
    text = trace.read_text()
    if failure == "mount":
        assert "umount" not in text
    else:
        assert str(install / "alpha/game/src/start.py") in text
        assert str(install / "alpha/game") + "|" in text
        assert "umount" in text


def test_launcher_termination_cleans_mount(project, tmp_path):
    install = tmp_path / "install"
    (install / "alpha/game/src").mkdir(parents=True)
    (install / "alpha/runtime").mkdir()
    script = install / "alpha.sh"
    script.write_text(launcher(discover(project)[0], {"python": "3.12.8"}))
    tools = tmp_path / "tools"
    tools.mkdir()
    trace = tmp_path / "trace"
    stubs = {
        "uname": "echo aarch64\n",
        "mount": 'for item in "$@"; do target=$item; done\nmkdir -p "$target/bin"\ncp "$TOOLS/python" "$target/bin/python"\n',
        "umount": 'echo clean >> "$TRACE"\n',
        "python": 'echo started >> "$TRACE"\nexec sleep 30\n',
    }
    for name, content in stubs.items():
        path = tools / name
        path.write_text("#!/bin/sh\n" + content)
        path.chmod(0o755)
    environment = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", TRACE=str(trace), TOOLS=str(tools))
    child = subprocess.Popen(["sh", str(script)], env=environment)
    try:
        deadline = time.monotonic() + 5
        while not trace.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert trace.exists()
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=5) == 143
        assert "clean" in trace.read_text()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
