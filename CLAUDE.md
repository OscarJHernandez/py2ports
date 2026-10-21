# Claude repository instructions

Before working in this repository, read and follow [AGENTS.md](AGENTS.md).
It is the shared source of development commands, architecture, private-submodule
rules, deployment contracts and verification requirements. Keep shared guidance
there so agents use the same instructions.

Use the repository's `.venv` for Python commands. Start with the
[README](README.md) for usage and [guide](docs/GUIDE.md) for detailed configuration.
Routine tests use synthetic games and simulated devices; private game access,
Docker builds and physical-device checks are separate verification steps.
