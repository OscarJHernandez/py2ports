"""Manifest validation and Git-pinned source selection."""
from dataclasses import dataclass
import configparser
from pathlib import Path
import re
import tomllib

from .common import Error, git, inside

ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


@dataclass(frozen=True)
class Game:
    root: Path
    manifest: Path
    id: str
    name: str
    submodule: str
    source: str
    include: tuple[str, ...]
    entrypoint: str
    working_directory: str
    runtime: str
    dependencies: str | None
    environment: dict[str, str]
    publish: bool

    @property
    def repository(self):
        return inside(self.root, self.submodule)

    @property
    def source_path(self):
        return inside(self.repository, self.source)

    def commit(self):
        modules = configparser.ConfigParser(interpolation=None)
        try:
            modules.read(self.root / ".gitmodules")
            entries = [modules[name] for name in modules.sections()
                       if modules[name].get("path") == self.submodule]
        except configparser.Error as exc:
            raise Error("Invalid .gitmodules configuration.") from exc
        if len(entries) != 1 or not entries[0].get("url"):
            raise Error(f"{self.id}: missing or duplicate .gitmodules registration for {self.submodule}.")
        entry = git(self.root, "ls-files", "--stage", "--", self.submodule).split()
        if len(entry) != 4 or entry[0] != "160000" or entry[2] != "0":
            raise Error(f"{self.id}: {self.submodule} is not a staged/committed Git submodule (mode 160000).")
        return entry[1]

    def validate_checkout(self):
        expected = self.commit()
        if not (self.repository / ".git").exists():
            raise Error(f"{self.id}: submodule is missing. Run git submodule update --init -- {self.submodule}; private games require access.")
        if git(self.repository, "rev-parse", "HEAD") != expected:
            raise Error(f"{self.id}: checkout differs from pinned commit. Run git submodule update --init -- {self.submodule}.")
        if git(self.repository, "status", "--porcelain", "--untracked-files=all"):
            raise Error(f"{self.id}: game checkout is dirty. Commit changes and update the superproject pin before building.")
        if not inside(self.source_path, self.entrypoint).is_file():
            raise Error(f"{self.id}: entrypoint does not exist: {self.entrypoint}")
        if not inside(self.source_path, self.working_directory).is_dir():
            raise Error(f"{self.id}: working_directory is missing.")
        selected = self.files()
        if self.entrypoint not in selected:
            raise Error(f"{self.id}: include must contain the entrypoint {self.entrypoint}.")
        return expected

    def files(self):
        """Only tracked regular files; symlinks and untracked secrets never ship."""
        tracked = git(self.repository, "ls-files", "-z").split("\0")
        source = Path(self.source)
        selected = {}
        for relative in filter(None, tracked):
            try:
                name = Path(relative).relative_to(source).as_posix()
            except ValueError:
                continue
            if not any(item == "." or name == item or name.startswith(item.rstrip("/") + "/") for item in self.include):
                continue
            if any(character in name for character in ("\n", "\r", "\\")):
                raise Error(f"{self.id}: unsupported filename in source (newline or backslash).")
            path = self.source_path / name
            if path.is_symlink() or not path.is_file():
                raise Error(f"{self.id}: only regular tracked files can be packaged: {name}")
            inside(self.source_path, name)
            selected[name] = path
        return dict(sorted(selected.items()))


def load(root: Path, path: Path) -> Game:
    try:
        value = tomllib.loads(path.read_text())
        if value.get("schema") != 1:
            raise Error(f"{path.name}: schema must be 1.")
        required = ("id", "name", "submodule", "source", "include", "entrypoint", "runtime")
        for key in required:
            if key not in value:
                raise Error(f"{path.name}: missing {key}.")
        if not isinstance(value["id"], str) or not ID.fullmatch(value["id"]):
            raise Error(f"{path.name}: invalid game ID; use lowercase letters, numbers, underscores, and hyphens.")
        if not isinstance(value["name"], str) or not value["name"].strip():
            raise Error(f"{path.name}: name must be nonempty text.")
        include = value["include"]
        if not isinstance(include, list) or not include or not all(isinstance(x, str) for x in include):
            raise Error(f"{path.name}: include must be a nonempty list of file/directory paths.")
        if not isinstance(value["runtime"], str) or not ID.fullmatch(value["runtime"]):
            raise Error(f"{path.name}: invalid runtime profile.")
        if not isinstance(value.get("publish", False), bool):
            raise Error(f"{path.name}: publish must be a boolean.")
        environment = value.get("environment", {})
        if not isinstance(environment, dict) or not all(
            re.fullmatch(r"[A-Z_][A-Z0-9_]*", k) and isinstance(v, str) and "\n" not in v and "\0" not in v
            for k, v in environment.items()
        ):
            raise Error(f"{path.name}: environment must contain shell variable names and single-line string values.")
        reserved = {"PATH", "PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "ENV", "BASH_ENV", "LD_PRELOAD"}
        if reserved.intersection(environment):
            raise Error(f"{path.name}: environment overrides reserved runtime variables.")
        game = Game(root.resolve(), path, value["id"], value["name"], value["submodule"], value["source"],
                    tuple(include), value["entrypoint"], value.get("working_directory", "."), value["runtime"],
                    value.get("dependencies"), environment, value.get("publish", False))
        repository = inside(root, game.submodule)
        if not Path(game.submodule).parts or Path(game.submodule).parts[0] != "games":
            raise Error(f"{path.name}: submodule must be under games/.")
        source = inside(repository, game.source)
        for item in (*game.include, game.entrypoint, game.working_directory):
            inside(source, item)
        if game.dependencies is not None:
            inside(root, game.dependencies)
        if not (root / "runtime" / f"{game.runtime}.toml").is_file():
            raise Error(f"{path.name}: missing runtime profile {game.runtime}.")
        return game
    except (tomllib.TOMLDecodeError, TypeError, KeyError, OSError) as exc:
        raise Error(f"{path.name}: invalid manifest: {exc}") from exc


def discover(root: Path, game_id=None):
    games = [load(root, path) for path in sorted((root / "catalog").glob("*.toml"))]
    if len({game.id for game in games}) != len(games) or len({game.submodule for game in games}) != len(games):
        raise Error("Catalog has duplicate game IDs or submodule destinations.")
    if game_id:
        games = [game for game in games if game.id == game_id]
        if not games:
            raise Error(f"Unknown game {game_id!r}. Run py2ports list.")
    return games
