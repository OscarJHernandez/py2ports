# py2ports guide

[Back to the quickstart](../README.md#deploy-to-your-handheld)

Detailed configuration and reference for deploying Python games to ARM64 Knulli.

- [Device connection and troubleshooting](#device-connection-and-troubleshooting)
- [Commands and manual installation](#other-commands)
- [Register a game or use the template](#add-your-own-game)
- [Runtime and dependencies](#runtime-and-dependencies)
- [CI and releases](#ci-and-releases)

## Device connection and troubleshooting

Docker must support ARM64 builds. Docker Desktop provides this on macOS; Linux
on x86 needs ARM64 binfmt/QEMU support.

Connections default to `root@knulli`, using normal SSH keys or an interactive
password prompt. Use `make check-device` for a standalone connection check.

If your default Python is older, install a newer one and use
`make setup PYTHON=python3.12`. The deployment command checks the device **before
building**, builds/packages what is needed, and installs the game. The first
runtime build may take 5–20 minutes; unchanged runtimes and ZIPs are reused.
GitHub and package downloads are needed on your computer, not on the handheld.
Each playable game ZIP is roughly 400 MiB, including dependency source archives
and licenses. Allow roughly 1 GiB of free device storage for staging an install;
upgrades also preserve a backup and may need more space. Deployment calculates
the required space and tells you if there is not enough.

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
make deploy GAME=py2ports_snake DEVICE_HOST=my-handheld DEVICE_USER=root DEVICE_PORT=22
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

Then use `make deploy GAME=py2ports_snake DEVICE_HOST=my-handheld`. `DEVICE_USER`
defaults to root; set it explicitly if your SSH configuration uses another user.

## Other commands

```sh
make list
make validate
make build                      # stage every accessible registered game
make build GAME=py2ports_snake
make package                    # create dist/<id>.zip for every game
make package GAME=py2ports_snake
make deploy                     # install existing ZIPs for registered games
make test                       # no connection to a physical device
```

The CLI provides the same commands:

```sh
.venv/bin/py2ports deploy --game py2ports_snake --host 192.168.1.50
.venv/bin/py2ports check-device --host 192.168.1.50
.venv/bin/py2ports validate --metadata-only
```

### Install a ZIP manually

Build locally with `make package GAME=py2ports_snake` or
`make package GAME=py2ports_breakout`, or download the public CI artifact described
below. After a release is explicitly published, its versioned game ZIPs and
`SHA256SUMS` are available from GitHub Releases. No release is published automatically.

Verify downloaded files before extraction, from the directory containing the ZIPs:

```sh
sha256sum -c public-games-SHA256SUMS  # CI artifact
# For a release: sha256sum -c SHA256SUMS
# macOS alternative: shasum -a 256 -c public-games-SHA256SUMS
```

Extract `dist/<id>.zip` directly into `/userdata/roms/ports/`, retaining the
executable permission on `<id>.sh` (`chmod +x` if your extractor drops it).
Each ZIP contains its runtime and needs no Git, Python installation, internet,
or development tools on the device. Automated deployment additionally verifies
checksums, stages the installation, preserves `data/`, and retains the previous
installation in a hidden backup. It does not delete other games. Games should
store saves in `PY2PORTS_DATA_DIR`; arbitrary saves elsewhere remain in the backup.
Snake installs under `/userdata/roms/ports/py2ports_snake/` and Breakout under
`/userdata/roms/ports/py2ports_breakout/`, each with its own matching launcher.
Their high scores are stored separately in `<game-id>/data/scores.json` and
logs in `<game-id>/log.txt`. Any previous `python_game` installation remains separate;
there is no automatic deletion or migration.
Do not upgrade a game while it is running. Backups are retained until you remove
them, so check storage after repeated upgrades.

## Add your own game

To register a game without downloading the included games, use a non-recursive clone:

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

### Start from the Pygame template

From the public, MIT-licensed [py2port_pygame_template repository](https://github.com/OscarJHernandez/py2port_pygame_template),
select **Use this template → Create a new repository**. Choose your own game name
and choose public or private visibility. It starts with independent Git history.
Clone it, run `make setup`, `make run`, and `make test`, then customize the game
loop and add assets. Preserve the template's MIT license and origin attribution.
Both included games were generated from the same public template revision; each
records that revision and its generated root in `TEMPLATE_ORIGIN.json`.

From your py2ports checkout, register the repository you created:

```sh
.venv/bin/py2ports add https://github.com/YOU/YOUR-GAME.git \
    --name my_game --entrypoint src/run.py
make deploy GAME=my_game
```

In its catalog manifest, select `include = ["src", "assets", "README.md", "LICENSE"]` to
package the game, its asset directory, and origin notices. Leave `publish = false`.
All Knulli runtime, launcher, and SSH configuration stays in the superproject.

### Run the template independently

The template itself is a normal desktop game, even without py2ports:

```sh
git clone https://github.com/OscarJHernandez/py2port_pygame_template.git
cd py2port_pygame_template
make setup
make run
make test
```

These commands use the template's own Makefile and desktop `pygame==2.6.1`.
The template README covers controls and customization. No Docker or device is
needed for desktop play or the headless smoke test.

## Runtime and dependencies

See the [deployment pipeline diagram](../README.md#how-it-works).

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

Public CI validates catalog metadata without fetching private submodules and runs
synthetic independent-game tests. The ARM64 job also initializes only Snake and
Breakout, packages both with the same runtime, executes their headless entrypoints
and game tests, and simulates installs/upgrades/rollback locally. The separate game
repositories test desktop pygame on Python 3.11 and 3.12. CI receives no private-game
credentials and never connects to a handheld.

Run the public-game integration check locally with Docker running:

```sh
.venv/bin/python tests/public_games_smoke.py
```

Successful ARM64 CI runs upload `public-playable-games`, containing only the two
public game ZIPs and `public-games-SHA256SUMS`. Download the artifact from the
workflow run, extract that outer artifact ZIP, then follow the manual install
instructions. These are CI build artifacts, not a published GitHub release.

Tags matching `v*` and manual release runs build only games explicitly marked
`publish = true` and eligible for public redistribution, along with the public
runtime. The template is public but has publication disabled. Snake and Breakout
are publication-enabled; private games are never checked out or uploaded. Set `publish = true`
only after the game owner authorizes redistribution of its source, assets, and
dependencies. Keep private dependencies out of public runtime profiles.

```sh
git tag v0.1.0
git push origin v0.1.0  # builds artifacts; does not publish a release
```

To publish, explicitly run the Release workflow for that tag with `publish`
enabled. Publication is disabled by default. Workflow artifacts include ZIPs,
checksums, and version/commit metadata. No workflow connects to a handheld.

See [CONTRIBUTING.md](../CONTRIBUTING.md) and
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Original platform code is MIT;
games and dependencies keep their own licenses. This project is unofficial and
is not affiliated with or endorsed by Knulli.
