"""Checked SSH/SCP installation; no game code is executed remotely during checks."""
from contextlib import AbstractContextManager
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

from .common import Error
from .packager import package, validate_archive

PORTS = "/userdata/roms/ports"
PREFLIGHT = r'''
set -eu
fail() { echo "PY2PORTS_ERROR:$1"; exit 1; }
case "$(uname -m)" in aarch64|arm64) ;; *) fail architecture ;; esac
for tool in sh scp mount umount unzip sha256sum df du awk cp mv mkdir mktemp rmdir rm chmod grep readlink date; do
    command -v "$tool" >/dev/null 2>&1 || fail "tool:$tool"
done
[ -d "$PORTS" ] || fail ports_missing
[ ! -L "$PORTS" ] || fail ports_symlink
[ -w "$PORTS" ] && [ -x "$PORTS" ] || fail ports_permissions
[ -w /tmp ] || fail tmp_permissions
grep -qw squashfs /proc/filesystems || fail squashfs
echo PY2PORTS_OK
'''

# Every mutated remote path is either this game's destination/launcher, its
# unique staging tree, or a retained backup. Other games are never enumerated.
INSTALL = r'''
set -eu
id=$1
stage=$2
backup="$PORTS/.py2ports-backup-$id-$(date +%s)-$$"
destination="$PORTS/$id"
launcher="$PORTS/$id.sh"
old_game=0
old_launcher=0
new_game=0
new_launcher=0
committed=0
cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$committed" = 0 ]; then
        [ "$new_launcher" = 0 ] || rm -f "$launcher"
        [ "$new_game" = 0 ] || rm -rf "$destination"
        [ "$old_game" = 0 ] || mv "$backup/$id" "$destination"
        [ "$old_launcher" = 0 ] || mv "$backup/$id.sh" "$launcher"
    fi
    rm -rf "$stage"
    rmdir "$backup" 2>/dev/null || true
    exit "$status"
}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
[ "$(sha256sum "$stage/package.zip" | awk '{print $1}')" = "$3" ]
mkdir "$stage/extracted"
unzip -q "$stage/package.zip" -d "$stage/extracted"
cd "$stage/extracted"
sha256sum -c "$id/checksums.sha256" >/dev/null
[ ! -L "$destination" ]
[ ! -L "$launcher" ]
if [ -e "$destination" ]; then [ -d "$destination" ]; fi
if [ -e "$launcher" ]; then [ -f "$launcher" ]; fi
mkdir "$backup"
if [ -d "$destination" ]; then
    if [ -e "$destination/data" ]; then
        [ -d "$destination/data" ]
        [ ! -L "$destination/data" ]
        cp -a "$destination/data" "$stage/extracted/$id/data"
    fi
    mv "$destination" "$backup/$id"
    old_game=1
fi
if [ -f "$launcher" ]; then mv "$launcher" "$backup/$id.sh"; old_launcher=1; fi
mv "$stage/extracted/$id" "$destination"
new_game=1
chmod 755 "$stage/extracted/$id.sh"
mv "$stage/extracted/$id.sh" "$launcher"
new_launcher=1
committed=1
echo "Installed $id. Previous installation, if any: $backup"
'''


def connection_error(message):
    lower = message.lower()
    if "could not resolve hostname" in lower or "name or service not known" in lower:
        return "Cannot resolve the device hostname. Use DEVICE_HOST=<device-IP> (or --host) and check the network."
    if "connection refused" in lower:
        return "SSH connection refused. Enable SSH on the handheld and check DEVICE_PORT."
    if "timed out" in lower or "no route to host" in lower or "network is unreachable" in lower:
        return "Device unreachable. Wake the handheld and connect it to the same network; check its IP address."
    if "permission denied" in lower or "authentication failed" in lower:
        return "SSH authentication failed. Check DEVICE_USER and your password/key with ssh first."
    if "host key verification failed" in lower or "remote host identification has changed" in lower:
        return "SSH host-key verification failed. Verify the device's identity using ssh before retrying."
    errors = {"architecture": "Device is not ARM64. This profile requires an ARM64 Knulli handheld.",
              "ports_missing": "Ports directory is missing. Check that this device runs Knulli.",
              "ports_symlink": "Ports directory is a symlink; use a normal Knulli Ports directory for safe installation.",
              "ports_permissions": "Ports directory is not writable. Check the SSH user and device filesystem permissions.",
              "tmp_permissions": "Device /tmp is not writable. Check device permissions.",
              "squashfs": "Device kernel does not report SquashFS support. Check the firmware/runtime compatibility."}
    for key, value in errors.items():
        if f"PY2PORTS_ERROR:{key}" in message:
            return value
    match = re.search(r"PY2PORTS_ERROR:tool:([a-z0-9_-]+)", message)
    if match:
        return f"Device is missing required command {match[1]}. Use a Knulli firmware providing this utility."
    # Do not echo remote output: games, shell startup files, and remote command
    # failures can print secrets. Detailed troubleshooting uses ssh directly.
    return "SSH/device command failed. Check connectivity with ssh and inspect the device filesystem; no installation was assumed successful."


class Device(AbstractContextManager):
    def __init__(self, host="knulli", user="root", port=None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", host) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", user):
            raise Error("Invalid SSH host/user. Supply a hostname, IP, or SSH config alias; passwords are never command-line arguments.")
        if port is not None and not 1 <= port <= 65535:
            raise Error("SSH port must be between 1 and 65535.")
        self.host, self.user, self.port = host, user, port
        self.temporary = None

    def __enter__(self):
        for command in ("ssh", "scp"):
            if not shutil.which(command):
                raise Error(f"Install OpenSSH: required command {command} is missing.")
        self.temporary = tempfile.TemporaryDirectory(prefix="p2p-")
        return self

    def options(self):
        if self.temporary is None:
            raise Error("SSH session is not open.")
        return ["-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1",
                "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2",
                "-o", "ControlMaster=auto", "-o", "ControlPersist=60",
                "-o", f"ControlPath={self.temporary.name}/ssh"]

    @property
    def target(self):
        return f"{self.user}@{self.host}"

    def ssh(self, script, *arguments):
        args = ["ssh", *self.options(), *(["-p", str(self.port)] if self.port else []), self.target,
                "sh -s -- " + " ".join(shlex.quote(str(value)) for value in arguments)]
        result = subprocess.run(args, input=f"PORTS={shlex.quote(PORTS)}\n" + script,
                                text=True, capture_output=True)
        if result.returncode:
            raise Error(connection_error(result.stdout + result.stderr))
        return result.stdout.strip()

    def check(self):
        print(f"Checking SSH and device requirements at {self.target}...", flush=True)
        if "PY2PORTS_OK" not in self.ssh(PREFLIGHT):
            raise Error("Device check did not return its success marker; check the remote shell.")
        print("Device ready: ARM64, SSH, Ports permissions, utilities, and SquashFS checked.")

    def space(self, path, required):
        value = self.ssh('set -eu\ndf -Pk "$1" | awk \'NR==2 {print $4}\'\n', path)
        try:
            available = int(value.strip()) * 1024
        except ValueError as exc:
            raise Error("Cannot read available device storage; inspect df -Pk over SSH.") from exc
        if available < required:
            raise Error(f"Insufficient device space at {path}: need {required // (1024 * 1024) + 1} MiB free, have {available // (1024 * 1024)} MiB. Remove old backups or unused games and retry.")

    def install(self, game_id, archive):
        from .builder import sha256
        from .catalog import ID
        if not ID.fullmatch(game_id):
            raise Error("Unsafe installation ID.")
        _, unpacked = validate_archive(archive, game_id)
        # Retaining the old installation and copying its data can require another
        # game's worth of space. Account for existing data explicitly.
        existing = self.ssh('set -eu\nif [ -d "$PORTS/$1/data" ]; then du -sk "$PORTS/$1/data" | awk \'{print $1}\'; else echo 0; fi\n', game_id)
        try:
            data_size = int(existing) * 1024
        except ValueError as exc:
            raise Error("Could not measure existing game data.") from exc
        self.space(PORTS, Path(archive).stat().st_size + unpacked + data_size + 16 * 1024 * 1024)
        stage = self.ssh('set -eu\n[ ! -L "$PORTS/$1" ]\n[ ! -L "$PORTS/$1.sh" ]\nmktemp -d "$PORTS/.py2ports-$1.XXXXXX"\n', game_id)
        if not re.fullmatch(re.escape(PORTS) + r"/\.py2ports-" + re.escape(game_id) + r"\.[A-Za-z0-9]+", stage):
            raise Error("Device returned an unsafe staging path.")
        print(f"Uploading and installing {game_id}...", flush=True)
        try:
            # -O uses the SCP protocol supported by older Knulli SSH servers.
            args = ["scp", "-O", *self.options(), *(["-P", str(self.port)] if self.port else []),
                    str(Path(archive).resolve()),
                    f"{self.user}@{'[' + self.host + ']' if ':' in self.host else self.host}:{stage}/package.zip"]
            result = subprocess.run(args, text=True, capture_output=True)
            if result.returncode:
                raise Error(connection_error(result.stderr))
            self.ssh(INSTALL, game_id, stage, sha256(archive))
        finally:
            self.ssh('set -eu\nrm -rf -- "$1"\n', stage)
        print(f"Installed {PORTS}/{game_id}/\nOpen Ports → {game_id}\nGame log: {PORTS}/{game_id}/log.txt")

    def __exit__(self, *exc):
        if self.temporary:
            subprocess.run(["ssh", *self.options(), "-O", "exit", self.target],
                           text=True, capture_output=True)
            self.temporary.cleanup()
        return False


def deploy(root, games, game_id=None, **connection):
    # Deliberately check the device before package() can start Docker.
    with Device(**connection) as device:
        device.check()
        if game_id:
            archives = [(games[0].id, package(games[0]))]
        else:
            archives = [(game.id, root / "dist" / f"{game.id}.zip") for game in games
                        if (root / "dist" / f"{game.id}.zip").is_file()]
            if not archives:
                raise Error("No packaged games found. Run make package, or make deploy GAME=<id> to build and deploy one game.")
        for identity, archive in archives:
            device.install(identity, archive)
