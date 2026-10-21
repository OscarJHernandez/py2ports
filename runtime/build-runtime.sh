#!/usr/bin/env bash
# Generalized from Oscar Javier Hernandez's authorized python_game build script.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PY_VER="${PYTHON_VERSION%.*}"
test "$(uname -m)" = aarch64
test "$(python -c 'import platform; print(platform.python_version())')" = "$PYTHON_VERSION"

# A dated package snapshot keeps apt dependencies from silently changing.
rm -f /etc/apt/sources.list.d/debian.sources
printf 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/%s/ bookworm main\n' "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list
printf 'deb-src [check-valid-until=no] https://snapshot.debian.org/archive/debian/%s/ bookworm main\n' "$DEBIAN_SNAPSHOT" >> /etc/apt/sources.list
apt-get -o Acquire::Retries=3 update
apt-get upgrade -y --no-install-recommends
apt-get install -y --no-install-recommends build-essential git rsync squashfs-tools \
  libfreetype6-dev libportmidi-dev libsdl2-dev libsdl2-image-dev \
  libsdl2-mixer-dev libsdl2-ttf-dev patchelf

python -m venv --copies /runtime
export PATH="/runtime/bin:$PATH"
/runtime/bin/python -m pip install 'pip==25.0.1' 'setuptools==75.8.0' 'wheel==0.45.1' \
  'meson-python==0.18.0' 'meson==1.9.1' 'ninja==1.13.0' 'Cython==3.1.4' \
  'sphinx==8.2.3' 'astroid==3.3.11' 'sphinx-autoapi==3.6.0' 'pyproject-metadata==0.9.0'
git init /pygame-ce
git -C /pygame-ce remote add origin https://github.com/pygame-community/pygame-ce.git
git -C /pygame-ce fetch --depth 1 origin "$PYGAME_COMMIT"
git -C /pygame-ce checkout --detach FETCH_HEAD
/runtime/bin/python -m pip install --no-build-isolation --no-deps /pygame-ce

# Extra dependencies must be hash-locked pure Python wheels. Never execute an
# arbitrary game's build script or silently compile extra native extensions.
mkdir /wheels
if grep -q '[^[:space:]#]' /requirements.txt; then
  /runtime/bin/python -m pip download --require-hashes --only-binary=:all: --dest /wheels -r /requirements.txt
  python /input/check-wheels.py /wheels
  /runtime/bin/python -m pip install --no-index --find-links /wheels --require-hashes -r /requirements.txt
fi

cp "/usr/local/lib/libpython${PY_VER}.so.1.0" /runtime/lib/
rsync -a --exclude='site-packages/' "/usr/local/lib/python${PY_VER}/" "/runtime/lib/python${PY_VER}/"
python /input/bundle-libraries.py /runtime
find /runtime -type d -name __pycache__ -prune -exec rm -rf '{}' +
mkdir -p /runtime/notices /runtime/sources
mkdir /runtime/sources/debian
# Ship corresponding source archives for bundled Debian libraries, alongside
# the Pygame source, instead of treating upstream links as a source offer.
python - <<'PY'
import json
import subprocess
for name, version in json.load(open('/runtime/debian-sources.json')).items():
    subprocess.run(['apt-get', 'source', '--download-only', '-y', f'{name}={version}'],
                   cwd='/runtime/sources/debian', check=True)
PY
cp /pygame-ce/docs/LGPL.txt /runtime/notices/pygame-ce-LGPL-2.1.txt
cp -a /usr/share/doc /runtime/notices/system-packages
cp -a /input /runtime/sources/builder
git -C /pygame-ce archive HEAD | gzip -n > /runtime/sources/pygame-ce.tar.gz
/runtime/bin/python -m pip freeze > /runtime/notices/python-packages.txt
dpkg-query -W > /runtime/notices/debian-packages.txt
printf 'Python: https://www.python.org/downloads/source/ (%s)\nPygame-CE commit: %s\nDebian source snapshot: https://snapshot.debian.org/archive/debian/%s/\n' "$PYTHON_VERSION" "$PYGAME_COMMIT" "$DEBIAN_SNAPSHOT" > /runtime/notices/SOURCES.txt
export PYTHONHOME=/runtime LD_LIBRARY_PATH=/runtime/lib
/runtime/bin/python -c 'import platform, pygame; assert platform.machine() == "aarch64"; print(platform.python_version(), pygame.version.ver)'
python /input/bundle-libraries.py /runtime --verify
mksquashfs /runtime /output/runtime.squashfs -noappend -comp xz -b 1M -processors 2 -all-root
unsquashfs -d /verify /output/runtime.squashfs >/dev/null
PYTHONHOME=/verify LD_LIBRARY_PATH=/verify/lib /verify/bin/python -c 'import pygame, platform; print("Extracted runtime:", platform.machine(), pygame.version.ver)'
