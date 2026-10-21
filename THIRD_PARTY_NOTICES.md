# Licensing and runtime dependencies

Original py2ports platform code is MIT licensed. The Docker/SquashFS build
and launcher approach is generalized with authorization from Oscar Javier
Hernandez's private python_game project. Game logic remains in an independent
private submodule and is not licensed by the platform's MIT license.

The device runtime contains Python 3.12.8 (PSF License Agreement and included
third-party notices), Pygame-CE 2.5.6 (LGPL 2.1), and their dependencies. Python
license texts are retained in its standard library. Pygame-CE's LGPL text,
unmodified corresponding source snapshot, and runtime build scripts are included
inside the SquashFS under `notices/` and `sources/`. Shared libraries remain
dynamically linked; rebuilt runtimes can replace the bundled SquashFS.

System library copyright/license texts and an exact Debian package inventory
are included under `notices/system-packages/` and `notices/debian-packages.txt`.
Matching Debian source archives for bundled shared libraries are included under
`sources/debian/`, with source versions in `debian-sources.json`. The pinned
Debian snapshot also provides the matching source packages.
Check those component-specific licenses before redistributing a new profile.
The runtime records Python package versions under `notices/python-packages.txt`.
Additional dependencies must retain their own license notices and satisfy their
own redistribution terms; a successful build does not authorize publication.

Upstream sources:

- Python: https://www.python.org/downloads/release/python-3128/
- Pygame-CE: https://github.com/pygame-community/pygame-ce/tree/a17caaef2ae155713b0f6de77cbb4998446e8b2e
- Debian source archive: https://snapshot.debian.org/
- Docker Python image: https://github.com/docker-library/python

Knulli supplies libc and its SDL2/Mali/EGL/GBM/DRM graphics stack on the device. These host
components are not included in game ZIPs; required library names are recorded
inside the runtime's `host-libraries.txt`. This is an ARM64 Knulli profile,
not a universal Linux runtime.

`publish = false` is the default for every registered game. Before enabling
publication, the owner must authorize redistribution of its source, assets,
and dependencies. The private example is never included in public CI or releases.
