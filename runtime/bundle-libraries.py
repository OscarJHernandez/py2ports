"""Bundle ELF dependencies, keeping the device's SDL/Mali and libc ABI.

Knulli's libSDL2 supplies its Mali driver; substituting Debian's libSDL2 would
remove that backend. All other discovered shared-library dependencies are copied.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
verify = "--verify" in sys.argv
host = {"libSDL2-2.0.so.0", "libc.so.6", "libm.so.6", "libdl.so.2",
        "libpthread.so.0", "librt.so.1", "ld-linux-aarch64.so.1"}
queue = [root / "bin/python"] + list(root.rglob("*.so")) + list(root.rglob("*.so.*"))
seen = set()
sources = {}
while queue:
    path = queue.pop()
    if path in seen or not path.is_file():
        continue
    seen.add(path)
    if path.read_bytes()[:4] != b"\x7fELF":
        continue
    headers = subprocess.check_output(["readelf", "-h", str(path)], text=True)
    if "AArch64" not in headers:
        raise SystemExit(f"Non-ARM64 binary: {path}")
    result = subprocess.run(["ldd", str(path)], text=True, capture_output=True)
    if "not found" in result.stdout:
        raise SystemExit(f"Unresolved native dependency for {path}: {result.stdout}")
    for line in result.stdout.splitlines():
        match = re.search(r"(?:=>\s+)?(/[^\s]+)", line)
        if not match:
            continue
        dependency = Path(match[1])
        if dependency.name in host or dependency.is_relative_to(root):
            continue
        if verify:
            raise SystemExit(f"Unbundled native dependency: {path}: {dependency}")
        target = root / "lib" / dependency.name
        if not target.exists():
            shutil.copy2(dependency.resolve(), target)
            queue.append(target)
        candidates = {str(dependency), str(dependency.resolve())}
        candidates.update('/usr' + name for name in list(candidates) if name.startswith('/lib/'))
        candidates.update(name[4:] for name in list(candidates) if name.startswith('/usr/lib/'))
        package = None
        for candidate in sorted(candidates):
            owner = subprocess.run(['dpkg-query', '-S', candidate], text=True, capture_output=True)
            if owner.returncode == 0:
                package = owner.stdout.splitlines()[0].rsplit(': ', 1)[0]
                break
        if package is None:
            raise SystemExit(f'Cannot identify corresponding source package for {dependency}')
        source = subprocess.check_output(['dpkg-query', '-W', '-f=${source:Package} ${source:Version}', package], text=True).strip()
        name, version = source.split()
        sources[name] = version
(root / "host-libraries.txt").write_text("\n".join(sorted(host)) + "\n")
if not verify:
    (root / 'debian-sources.json').write_text(json.dumps(sources, indent=2) + '\n')
