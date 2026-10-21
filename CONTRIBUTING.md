# Contributing

Use Python 3.11+, Git, and Make. Run `make setup` and `make test`. Unit/integration
tests use temporary independent repositories and simulated devices; they do not
need private game access, Docker, or a handheld. All current submodules are public. Contributors can use
`.venv/bin/py2ports validate --metadata-only` without initializing games.
Snake and Breakout each have standalone `make setup`, `make run` and `make test`.

Keep game-specific behavior in catalog manifests. Never vendor game source into
the platform. Commit submodule pins, not copied checkout contents. Preserve
independent desktop execution when adding a game.

For runtime changes, run `python tests/runtime_smoke.py` after setup. This builds
a synthetic game with the real ARM64 Docker runtime, imports pygame from the
extracted SquashFS, checks its ZIP, and confirms runtime cache reuse. Docker
must be running; x86 Linux additionally needs ARM64 emulation. Report Docker
checks separately from physical-device display/input/audio testing.

After initializing the two public game submodules, run
`.venv/bin/python tests/public_games_smoke.py` to test both actual ARM64 games,
packages and simulated independent installs/upgrades/rollback.

Do not add private-source credentials to public workflows, logs, caches, or
artifacts. Do not mark a game publishable without its owner's authorization and
a dependency/assets license review. Respect upstream copyright and attribution.
