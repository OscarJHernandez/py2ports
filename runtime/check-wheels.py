"""Fail closed for extra native dependencies; the base profile owns Pygame."""
from pathlib import Path
import sys
import zipfile

for wheel in Path(sys.argv[1]).glob("*.whl"):
    if not wheel.name.endswith("-none-any.whl") or wheel.name.lower().startswith(("pygame-", "pygame_ce-")):
        raise SystemExit(f"Unsupported native/runtime dependency {wheel.name}; use pure-Python dependencies and the profile's Pygame-CE.")
    with zipfile.ZipFile(wheel) as archive:
        if any(name.endswith((".so", ".dll", ".dylib", ".pyd")) for name in archive.namelist()):
            raise SystemExit(f"Unsupported native library in {wheel.name}.")
