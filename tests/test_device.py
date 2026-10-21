from pathlib import Path
import shutil
import subprocess

import pytest

from py2ports import deployer, packager
from py2ports.catalog import discover
from py2ports.common import Error


@pytest.mark.parametrize("response,expected", [
    ("ssh: Could not resolve hostname knulli", "DEVICE_HOST"),
    ("ssh: Connection refused", "Enable SSH"),
    ("ssh: Connection timed out", "same network"),
    ("ssh: Permission denied", "authentication failed"),
    ("Host key verification failed", "identity"),
    ("PY2PORTS_ERROR:architecture", "ARM64"),
    ("PY2PORTS_ERROR:tool:unzip", "unzip"),
    ("PY2PORTS_ERROR:ports_permissions", "not writable"),
    ("PY2PORTS_ERROR:squashfs", "SquashFS"),
])
def test_connection_diagnostics(monkeypatch, response, expected):
    def fail(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, response, "")
    monkeypatch.setattr(deployer.subprocess, "run", fail)
    with deployer.Device() as device:
        with pytest.raises(Error, match=expected):
            device.check()


def test_success_reuses_connection_and_respects_hostkeys(monkeypatch):
    calls = []
    def success(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "PY2PORTS_OK\n", "")
    monkeypatch.setattr(deployer.subprocess, "run", success)
    with deployer.Device("device", "root", 2222) as device:
        device.check()
        device.check()
    paths = [next(arg for arg in args if arg.startswith("ControlPath=")) for args in calls]
    assert len(set(paths)) == 1
    assert not any("StrictHostKeyChecking=no" in arg for args in calls for arg in args)
    assert "2222" in calls[0]


def test_failed_preflight_prevents_build_and_upload(project, monkeypatch):
    def fail(self):
        raise Error("Device unreachable")
    monkeypatch.setattr(deployer.Device, "check", fail)
    monkeypatch.setattr(deployer, "package", lambda *_: pytest.fail("Build started before connection check"))
    monkeypatch.setattr(deployer.Device, "install", lambda *_: pytest.fail("Upload started before connection check"))
    monkeypatch.setattr(deployer.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    with pytest.raises(Error, match="unreachable"):
        deployer.deploy(project, discover(project), "alpha")


def test_selected_deploy_checks_then_builds_then_installs(project, monkeypatch):
    events = []
    monkeypatch.setattr(deployer.Device, "check", lambda *_: events.append("check"))
    monkeypatch.setattr(deployer, "package", lambda *_: events.append("package") or Path("alpha.zip"))
    monkeypatch.setattr(deployer.Device, "install", lambda *_: events.append("install"))
    monkeypatch.setattr(deployer.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    deployer.deploy(project, discover(project), "alpha")
    assert events == ["check", "package", "install"]


def test_insufficient_space_and_unknown_output(monkeypatch):
    device = deployer.Device()
    monkeypatch.setattr(device, "ssh", lambda *_: "1")
    with pytest.raises(Error, match="Insufficient device space"):
        device.space("/ports", 1024 * 1024)
    monkeypatch.setattr(device, "ssh", lambda *_: "not a number")
    with pytest.raises(Error, match="Cannot read"):
        device.space("/ports", 1)


def test_credentials_not_in_error(monkeypatch):
    secret = "EXAMPLE_PASSWORD_DO_NOT_PRINT"
    monkeypatch.setattr(deployer.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 1, secret, "remote failure " + secret))
    with deployer.Device() as device:
        with pytest.raises(Error) as caught:
            device.check()
    assert secret not in str(caught.value)


@pytest.mark.parametrize("host,user", [("-oProxyCommand=bad", "root"), ("host", "root;evil"), ("password@host", "root")])
def test_invalid_connection_inputs(host, user):
    with pytest.raises(Error):
        deployer.Device(host, user)


@pytest.fixture
def local_device(tmp_path, monkeypatch):
    """Run the actual installation shell script locally; substitute transport only."""
    ports = tmp_path / "ports"
    ports.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    if not shutil.which("sha256sum"):
        sha = tools / "sha256sum"
        sha.write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n')
        sha.chmod(0o755)
    import os
    monkeypatch.setenv("PATH", f"{tools}:{os.environ['PATH']}")
    monkeypatch.setattr(deployer, "PORTS", str(ports))
    original_run = subprocess.run

    def transport(args, **kwargs):
        if args[0] == "scp":
            shutil.copyfile(args[-2], args[-1].split(":", 1)[1])
            return subprocess.CompletedProcess(args, 0, "", "")
        return original_run(args, **kwargs)

    monkeypatch.setattr(deployer.subprocess, "run", transport)

    class LocalDevice(deployer.Device):
        def ssh(self, script, *arguments):
            result = original_run(["sh", "-s", "--", *map(str, arguments)],
                                  input=f"PORTS='{ports}'\n" + script,
                                  text=True, capture_output=True)
            if result.returncode:
                raise Error("Local install failed: " + result.stderr)
            return result.stdout.strip()

        def __exit__(self, *exc):
            self.temporary.cleanup()

    return LocalDevice, ports, tools


def test_install_upgrade_preserves_data_and_other_game(project, fake_docker, local_device):
    device_type, ports, _ = local_device
    other = ports / "other_game"
    other.mkdir()
    (other / "sentinel").write_text("untouched")
    output = packager.package(discover(project)[0])
    with device_type() as device:
        device.install("alpha", output)
        (ports / "alpha/data/save.txt").parent.mkdir(exist_ok=True)
        (ports / "alpha/data/save.txt").write_text("player progress")
        (ports / "alpha/old-only.txt").write_text("old version")
        device.install("alpha", output)
    assert (ports / "alpha/data/save.txt").read_text() == "player progress"
    assert not (ports / "alpha/old-only.txt").exists()
    assert (other / "sentinel").read_text() == "untouched"
    assert list(ports.glob(".py2ports-backup-alpha-*/alpha/old-only.txt"))
    assert not list(ports.glob(".py2ports-alpha.*"))


def test_failed_promotion_rolls_back(project, fake_docker, local_device):
    device_type, ports, tools = local_device
    output = packager.package(discover(project)[0])
    with device_type() as device:
        device.install("alpha", output)
        (ports / "alpha/data").mkdir(exist_ok=True)
        (ports / "alpha/data/save.txt").write_text("keep me")
        original = (ports / "alpha.sh").read_bytes()
        mv = tools / "mv"
        # Fail only the new launcher's promotion; permit rollback commands.
        mv.write_text('#!/bin/sh\ncase "$1" in */extracted/alpha.sh) exit 1;; esac\nexec /bin/mv "$@"\n')
        mv.chmod(0o755)
        with pytest.raises(Error, match="Local install failed"):
            device.install("alpha", output)
    assert (ports / "alpha.sh").read_bytes() == original
    assert (ports / "alpha/data/save.txt").read_text() == "keep me"


def test_symlink_destination_rejected(project, fake_docker, local_device, tmp_path):
    device_type, ports, _ = local_device
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("safe")
    (ports / "alpha").symlink_to(outside)
    output = packager.package(discover(project)[0])
    with device_type() as device:
        with pytest.raises(Error):
            device.install("alpha", output)
    assert (outside / "sentinel").read_text() == "safe"
