# Repository guidance for coding agents

## Purpose and layout

py2ports packages independent Python/Pygame games for ARM64 Knulli handhelds.
It validates pinned game sources, builds a cached runtime, produces self-contained
ZIPs and installs them over SSH. Keep game-specific behavior in manifests rather
than adding special cases to platform code.

| Path | Responsibility |
| --- | --- |
| `py2ports/cli.py`, `catalog.py` | Commands, game registration and manifest validation |
| `py2ports/builder.py`, `runtime/` | Pinned Docker Compose ARM64 runtime and cache |
| `py2ports/packager.py`, `launcher/game.sh.in` | ZIP validation, provenance and launchers |
| `py2ports/deployer.py` | SSH checks, staging, upgrades and rollback |
| `py2ports/release.py`, `.github/workflows/` | Public CI and eligible release artifacts |
| `catalog/`, `games/` | TOML manifests and genuine Git submodules |
| `tests/` | Synthetic games, simulated devices and runtime smoke test |

Read the [README](README.md) for the quickstart, the [guide](docs/GUIDE.md) for
configuration and the [contribution guidelines](CONTRIBUTING.md) for development.

## Local development

Use Python 3.11+ and the repository's virtual environment:

```sh
make setup                         # use PYTHON=python3.12 if needed
make test
.venv/bin/py2ports validate --metadata-only
```

These tests and metadata checks require neither private game access nor Docker
nor a handheld. Clone without `--recurse-submodules` when private access is
unavailable. Do not treat a missing private checkout as a platform defect.
For focused checks, use `.venv/bin/python -m pytest tests/test_device.py` or the
relevant test module. Keep new platform dependencies deliberate; the CLI currently
uses the standard library and has no installed runtime dependencies.

## Games and privacy

- `games/py2port_pygame_template` is a private GitHub template submodule. Its
  catalog ID is `py2port_pygame_template`, with entrypoint `src/run.py` and explicit
  `src`, `assets` and origin README inclusion. Do not copy its source into this repo.
- Keep games independently runnable on desktop. Desktop `pygame==2.6.1` and the
  device profile's Python 3.12.8 / Pygame-CE 2.5.6 are separate environments.
- Register games with `.venv/bin/py2ports add <repository-url> --name <id>
  --entrypoint <relative-path>`. Review the generated manifest's `include` paths;
  registration initially includes all tracked files beneath its source root.
  Commit the catalog, `.gitmodules` and pinned gitlink together.
- Preserve checkout validation: sources must match their pins and be clean;
  reject unsafe paths, untracked source files and symlink escapes.
- Keep private code, packages and credentials out of public logs, artifacts,
  caches and releases. `build/` and `dist/` stay ignored. Public CI uses synthetic
  games and metadata-only validation, without fetching private submodules.
- Leave `publish = false` unless redistribution is authorized and source, assets
  and dependencies are eligible. Platform MIT licensing does not license games.

## Build and deployment contracts

```sh
make package GAME=py2port_pygame_template
make check-device DEVICE_HOST=192.168.1.50
make deploy GAME=py2port_pygame_template DEVICE_HOST=192.168.1.50
```

Packaging needs Docker with Compose and ARM64 execution support. The connection
check and deployment commands contact a real device; use simulated tests for
routine development. Deployment defaults to `root@knulli` and also supports
`DEVICE_HOST`, `DEVICE_USER`, `DEVICE_PORT` and CLI `--host`, `--user`, `--port`.

- Preserve device preflight before expensive builds, normal SSH host-key checks,
  bounded connection timeouts and one shared deployment SSH connection. Never
  store passwords or log credentials. Check storage before uploading.
- `make deploy GAME=<id>` builds/packages stale inputs and installs that game.
  `make deploy` without `GAME` installs existing packages only.
- Validate ZIPs before upload and verify staged extraction before promotion.
  Preserve `data/` (`PY2PORTS_DATA_DIR`), retain the previous installation backup,
  roll back failed promotion and leave unrelated games untouched. An old
  `python_game` installation is separate; do not implicitly migrate or delete it.
- Launchers must resolve relative paths, honor the working directory, use unique
  mount directories, handle signals, preserve exit status and clean up mounts.
  Retain the template's Mali setting and the device-supplied graphics libraries.
- Keep runtime inputs pinned and cache keys sensitive to build/dependency inputs.
  Additional dependencies currently require locked, hashed pure-Python wheels;
  native additions need an engineered runtime profile. Include dependency
  notices, redistribution materials, provenance and checksums in packages.

## Verification and delivery

Run focused tests for code changes, then `make test`. For runtime, builder,
launcher or packaging changes, also run the real ARM64 synthetic smoke check:

```sh
.venv/bin/python tests/runtime_smoke.py
```

This needs Docker and may take longer on the first build. Preserve its cache-reuse
check. For documentation-only edits, check links, commands and diagram rendering;
a runtime rebuild is unnecessary.

Use synthetic fixtures for automated device checks; never make tests contact a
physical handheld. Container smoke tests do not establish Ports-menu, graphics,
controls, audio or firmware compatibility. Report actual automated results and
hardware checks separately, including anything skipped. See
[verification notes](docs/VERIFICATION.md) for prior coverage and limitations.

Before committing, run `git diff --check` and inspect staged files for private
contents or build artifacts. Keep the README concise and put detailed reference
material in the guide. Release publication is disabled by default; creating a PR
does not authorize merging it or publishing a release.
