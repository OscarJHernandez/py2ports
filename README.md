# py2ports

Turn an independent Python/Pygame game into a self-contained ZIP for an ARM64
Knulli handheld. Each game stays in its own Git repository. py2ports builds the
runtime, generates its Ports launcher, and installs it over SSH.

## Deploy to your handheld

**The included example is private.** Your GitHub account needs access to
`OscarJHernandez/py2ports-example-game`; request access from the owner. Public
contributors can clone without submodules and [register their own game](#add-your-own-game).
The original `python_game` repository is left untouched.

You need **Python 3.11+**, **Docker with Compose running**, Make, SSH/SCP, and
Git. Turn on your handheld, enable SSH in Knulli, and connect it to the same
network as your computer. Docker Desktop supports ARM64 builds on macOS; Linux
on x86 needs ARM64 binfmt/QEMU support.

```sh
git clone --recurse-submodules https://github.com/OscarJHernandez/py2ports.git
cd py2ports
make setup
make deploy GAME=python_game
```

If your default Python is older, install a newer one and use
`make setup PYTHON=python3.12`. The deployment command checks the device **before
building**, builds/packages what is needed, and installs the game. The first
runtime build may take 5–20 minutes; unchanged runtimes and ZIPs are reused.
GitHub and package downloads are needed on your computer, not on the handheld.
The initial example ZIP is roughly 400 MiB, including dependency source archives
and licenses. Allow roughly 1 GiB of free device storage for staging an install;
upgrades also preserve a backup and may need more space. Deployment calculates
the required space and tells you if there is not enough.

By default, deployment connects to `root@knulli`, using your normal SSH keys or
an interactive password prompt. Check the connection on its own:

```sh
make check-device
```

If the name `knulli` is not found, use the IP shown in the device's network menu:

```sh
make check-device DEVICE_HOST=192.168.1.50
make deploy GAME=python_game DEVICE_HOST=192.168.1.50
```

After installation, open **Ports → python_game**. If it does not appear,
refresh the game list in Knulli. Logs are at
`/userdata/roms/ports/python_game/log.txt`.

### Connection problems

| Message | What to do |
| --- | --- |
| Cannot resolve hostname | Use `DEVICE_HOST=<IP>`; check the device's network menu. |
| Device unreachable | Wake the device and connect both machines to the same network. |
| SSH connection refused | Enable SSH and check the port. |
| Authentication failed | Try `ssh root@<IP>` and check your key/password. |
| Host-key verification failed | Verify the device identity with SSH before correcting known_hosts. |
| Docker unavailable | Start Docker Desktop and retry. |
| Insufficient space | Remove unused games or old `.py2ports-backup-*` directories you no longer need. |

`make check-device` checks SSH authentication, ARM64, required tools, kernel
SquashFS support, and Ports permissions. Deployment also checks storage before
uploading. These checks do not prove that your display driver or game is compatible.
Passwords are never saved, and a deployment reuses one SSH connection.

Override connection settings with `DEVICE_HOST`, `DEVICE_USER`, and `DEVICE_PORT`:

```sh
make deploy GAME=python_game DEVICE_HOST=my-handheld DEVICE_USER=root DEVICE_PORT=22
```

For persistent settings, use `~/.ssh/config`; port settings there are respected
unless `DEVICE_PORT` is explicitly supplied:

```sshconfig
Host my-handheld
    HostName 192.168.1.50
    User root
    Port 22
    IdentityFile ~/.ssh/id_ed25519
```

Then use `make deploy GAME=python_game DEVICE_HOST=my-handheld`. `DEVICE_USER`
defaults to root; set it explicitly if your SSH configuration uses another user.

## Other commands

```sh
make list
make validate
make build                      # stage every accessible registered game
make build GAME=python_game
make package                    # create dist/<id>.zip for every game
make package GAME=python_game
make deploy                     # install existing ZIPs for registered games
make test                       # no connection to a physical device
```

The CLI provides the same commands:

```sh
.venv/bin/py2ports deploy --game python_game --host 192.168.1.50
.venv/bin/py2ports check-device --host 192.168.1.50
.venv/bin/py2ports validate --metadata-only
```

### Install a ZIP manually

Extract `dist/<id>.zip` directly into `/userdata/roms/ports/`, retaining the
executable permission on `<id>.sh` (`chmod +x` if your extractor drops it).
Each ZIP contains its runtime and needs no Git, Python installation, internet,
or development tools on the device. Automated deployment additionally verifies
checksums, stages the installation, preserves `data/`, and retains the previous
installation in a hidden backup. It does not delete other games. Games should
store saves in `PY2PORTS_DATA_DIR`; arbitrary saves elsewhere remain in the backup.
Do not upgrade a game while it is running. Backups are retained until you remove
them, so check storage after repeated upgrades.

## Add your own game

Public contributors should start with a non-recursive clone:

```sh
git clone https://github.com/OscarJHernandez/py2ports.git
cd py2ports
make setup
.venv/bin/py2ports add https://github.com/YOU/YOUR-GAME.git \
    --name my_game --entrypoint src/main.py
# For a repository with its game under app/:
# .venv/bin/py2ports add <url> --name my_game --source app --entrypoint main.py
make validate GAME=my_game
make deploy GAME=my_game
```

Review the generated manifest's `include` paths before packaging; the default
includes every tracked regular file beneath `source`. Commit the manifest,
`.gitmodules`, and gitlink together. The platform never commits game edits for you.
Do not put secrets in tracked game files. Submodules are pinned to exact commits;
after an intentional update, stage the new gitlink in py2ports.

An example manifest:

```toml
schema = 1
id = "my_game"
name = "My Game"
submodule = "games/my_game"
source = "."
include = ["src", "assets"]  # literal files/directories, not glob patterns
entrypoint = "src/main.py"   # relative to source
working_directory = "."     # relative to source
runtime = "knulli-arm64"
publish = false

[environment]
SDL_VIDEODRIVER = "mali"
```

Paths must stay inside their source root. Source symlinks, untracked files,
dirty checkouts, and mismatched submodule pins are rejected. The platform reads
game source into ignored build artifacts; it never vendors it into platform code.

### Run the example independently

The fresh repository is a normal desktop game, even without py2ports:

```sh
git clone https://github.com/OscarJHernandez/py2ports-example-game.git
cd py2ports-example-game
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python src/run.py
python -m unittest discover -s tests
```

## Runtime and architecture

```text
catalog/*.toml → pinned games/* submodules
runtime/      → Docker ARM64 build → cached SquashFS
launcher/     → per-game shell launcher
py2ports/     → validate → build → ZIP → SSH/SCP install
tests/        → synthetic repositories and simulated devices
```

The device profile retains the reference's Python **3.12.8** and Pygame-CE
**2.5.6**. The game independently uses desktop `pygame==2.6.1`; py2ports never
mistakes that desktop requirement for the device runtime specification.

The profile pins the Docker image digest, Pygame source commit, and Debian
snapshot. Runtime cache keys include builder/profile content and dependency
hashes. Build provenance records exact runtime inputs, installed packages,
platform/game commits, and file checksums. This records reproducible inputs;
SquashFS/ZIP timestamps are not promised to be byte-for-byte reproducible.

For additional pure-Python dependencies, set `dependencies = "catalog/my_game.requirements.txt"`
in the manifest. Supply a fully pinned pip requirements file including all
transitive dependencies and `--hash=sha256:...` entries. Only pure-Python wheels
are accepted. Do not include pygame/pygame-ce; the runtime profile owns it.
Extra native dependencies fail clearly and require a separately engineered
runtime profile. No game build hooks run on the host or inside the builder.

The bundled interpreter and native libraries target ARM64 glibc Linux. Knulli
must provide a compatible libc and its SDL2/Mali stack. This is **not** a promise
of compatibility with every ARM64 device or firmware. Graphics, audio, inputs,
and actual Ports launch require hardware verification. The launcher logs errors
and releases its unique SquashFS mount on normal exit and handled signals.

## CI and releases

Public CI validates catalog metadata without fetching private submodules, runs
synthetic independent-game tests, and builds/packages a synthetic game with the
real ARM64 runtime. It never receives private-game credentials. Local private
verification uses `make validate`, `make package GAME=python_game`, and the
independent desktop smoke test above. CI explicitly reports private coverage as skipped.

Tags matching `v*` and manual release runs build only games explicitly marked
`publish = true` and eligible for public redistribution, along with the public
runtime. Private games are never checked out or uploaded. Set `publish = true`
only after the game owner authorizes redistribution of its source, assets, and
dependencies. Keep private dependencies out of public runtime profiles.

```sh
git tag v0.1.0
git push origin v0.1.0  # builds artifacts; does not publish a release
```

To publish, explicitly run the Release workflow for that tag with `publish`
enabled. Publication is disabled by default. Workflow artifacts include ZIPs,
checksums, and version/commit metadata. No workflow connects to a handheld.

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Original platform code is MIT;
games and dependencies keep their own licenses. This project is unofficial and
is not affiliated with or endorsed by Knulli.
