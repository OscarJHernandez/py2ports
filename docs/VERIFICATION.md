# Implementation verification

Verified locally on Apple ARM64 macOS with Python 3.12.15 and Docker 28.3.2.
No check connected to a physical handheld.

| Check | Result |
| --- | --- |
| Documented `make setup` with Python 3.12 | Passed |
| `make list`, `make validate` | Passed with the actual private game submodule |
| `make test` | 59 passed |
| Independent private-game desktop smoke | 1 passed with pygame 2.6.1 and dummy SDL drivers |
| Fresh game repository history | One new root commit; no original history inherited |
| Original versus fresh game source | Both source Git blob hashes match the authorized original revision |
| Fresh remote visibility | Private |
| Submodule representation | Git mode 160000, pinned to the fresh game commit |
| Actual recursive GitHub clone | Passed; fresh private submodule initialized and independent desktop smoke passed |
| Real Docker/SquashFS build | Passed: ARM64 Python 3.12.8 and Pygame-CE 2.5.6 |
| Runtime library audit and dependency sources | Passed; corresponding Debian/Pygame sources included |
| Extracted runtime display/audio/font smoke | Passed in a separate ARM64 container using dummy SDL drivers |
| Runtime reuse | Repeated builds used the unchanged cache entry |
| Actual private-game ZIP | Built locally and validated; about 415 MiB; no public upload |
| Package extraction | Synthetic game automated tests and actual private ZIP extraction passed |
| Device connection errors and install/upgrade/rollback | Simulated transport/shell tests passed |
| Python compilation and shell syntax | Passed |
| Public-source review | Game represented only by gitlink; build/dist artifacts ignored |
| Actual public artifact preparation | Passed; runtime, provenance, release metadata and checksums only; private game excluded |

The suite creates real temporary independent repositories and recursive clean
clones. It tests different game layouts, assets, malformed configuration, dirty
and mismatched pins, missing checkouts, unsafe paths, failed builds, corrupt
caches, altered packages, launcher failures/signals, SSH diagnostics, storage
checks, installation rollback, preserved saves, and unrelated installed games.
Release tests verify that private games and pre-existing private ZIPs are
excluded from public artifacts and that public-repository checks use no token.

## Repository structure

```text
py2ports/
├── games/python_game/       # fresh private repository, real pinned submodule
├── catalog/python_game.toml
├── py2ports/                # CLI, catalog, runtime builder, ZIP packager, SSH installer, releases
├── runtime/                 # pinned ARM64 profile, Compose, build and library-audit scripts
├── launcher/                # generated per-game shell launcher template
├── tests/                   # synthetic independent repositories and simulated devices
├── .github/workflows/       # public CI and opt-in release publication
├── docs/VERIFICATION.md
├── Makefile
├── pyproject.toml
├── README.md
├── CONTRIBUTING.md
├── THIRD_PARTY_NOTICES.md
└── LICENSE
```

## Build and deploy

```sh
make package GAME=python_game
make check-device DEVICE_HOST=192.168.1.50
make deploy GAME=python_game DEVICE_HOST=192.168.1.50
```

The last command performs the connection check automatically and builds missing
or stale inputs. Credentials for the private example are required only on the
development machine. Public CI uses synthetic games and reports private coverage
as skipped.

## Hardware checks still required

Actual SSH authentication to the user's handheld, kernel loop mounting,
Ports-menu discovery, Mali display behavior, physical controls, audio output,
and firmware/ABI compatibility have not been tested. The profile requires a
compatible ARM64 Knulli libc and SDL2/Mali stack. Dummy-driver container tests
do not establish hardware compatibility.

Additional native dependencies require a separately engineered runtime profile.
Byte-for-byte reproducibility of ZIP/SquashFS timestamps is not guaranteed.
Backups are retained until removed by the user, and saves outside the documented
`data/` directory remain in the previous installation backup.
