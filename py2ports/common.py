"""Small shared helpers. External commands always use argument lists."""
from pathlib import Path
import subprocess


class Error(Exception):
    """An actionable user-facing failure."""


def run(args, *, cwd=None, env=None, capture=True):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], cwd=cwd, env=env,
            text=True, capture_output=capture, check=False,
        )
    except FileNotFoundError as exc:
        raise Error(f"Required command not found: {args[0]}. Install it and retry.") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip() if capture else "See command output above."
        raise Error(f"{args[0]} failed (exit {result.returncode}): {detail[-2000:]}")
    return result.stdout.strip() if capture else ""


def inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise Error(f"Expected a relative path, got {relative!r}")
    if any(ord(character) < 32 or character == "\\" for character in relative):
        raise Error("Paths must use forward slashes and cannot contain control characters.")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise Error(f"Path escapes its root: {relative}")
    return candidate


def git(root, *args):
    return run(["git", "-C", root, *args])
