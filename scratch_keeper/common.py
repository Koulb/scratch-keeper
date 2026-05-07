"""Shared helpers for the scratch_keeper package.

Path safety, JSON I/O, glob expansion, du wrapper, mtime helpers.
Stdlib only.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path


class PathOutsideRootError(ValueError):
    """Raised when a candidate path is not strictly inside the configured root."""


def ensure_under_root(path: str | os.PathLike, root: str | os.PathLike) -> Path:
    """Resolve `path` (relative paths anchored at `root`) and verify it is
    strictly inside `root`. Symlinks are followed: a symlink that escapes
    the root is refused. Returns the resolved absolute Path.
    """
    root_resolved = Path(root).expanduser().resolve()
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = root_resolved / p
    p_resolved = p.resolve()
    try:
        p_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathOutsideRootError(
            f"{p_resolved} is not under {root_resolved}"
        ) from exc
    if p_resolved == root_resolved:
        raise PathOutsideRootError(
            f"{p_resolved} equals root {root_resolved}; refusing"
        )
    return p_resolved


from dataclasses import dataclass, field


@dataclass(frozen=True)
class Manifest:
    name: str
    path: str
    category: str
    backup_globs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    touch_globs: list[str] = field(default_factory=list)
    touch_exclude_globs: list[str] = field(default_factory=list)
    notes: str = ""


REQUIRED_MANIFEST_FIELDS = ("name", "path", "category")


def _expand_user(value: object) -> object:
    if isinstance(value, str):
        return os.path.expanduser(value)
    if isinstance(value, list):
        return [_expand_user(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_user(v) for k, v in value.items()}
    return value


def load_config(path: "str | os.PathLike") -> dict:
    """Load config.json. `~` is expanded recursively for any string value."""
    raw = json.loads(Path(path).read_text())
    return _expand_user(raw)


def load_manifests(projects_dir: "str | os.PathLike") -> "dict[str, Manifest]":
    """Load every `*.json` file in `projects_dir` into a Manifest.
    Keyed by manifest['path'] (the directory name on scratch).
    """
    pdir = Path(projects_dir).expanduser()
    out: dict[str, Manifest] = {}
    for jp in sorted(pdir.glob("*.json")):
        data = json.loads(jp.read_text())
        missing = [f for f in REQUIRED_MANIFEST_FIELDS if f not in data]
        if missing:
            raise ValueError(
                f"{jp}: manifest missing required field(s): {missing}"
            )
        m = Manifest(
            name=data["name"],
            path=data["path"],
            category=data["category"],
            backup_globs=list(data.get("backup_globs", [])),
            exclude_globs=list(data.get("exclude_globs", [])),
            touch_globs=list(data.get("touch_globs", [])),
            touch_exclude_globs=list(data.get("touch_exclude_globs", [])),
            notes=str(data.get("notes", "")),
        )
        out[m.path] = m
    return out


import datetime as _dt
from typing import Iterator


def du_bytes(path: str | os.PathLike) -> int:
    """Sum apparent size of all regular files under `path` (recursive)."""
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            fp = os.path.join(root, name)
            try:
                total += os.lstat(fp).st_size
            except (FileNotFoundError, PermissionError):
                continue
    return total


def count_files_dirs(path: str | os.PathLike) -> tuple[int, int]:
    """Return (n_regular_files, n_subdirs) recursively under `path`."""
    n_files = 0
    n_dirs = 0
    for _root, dirs, files in os.walk(path, followlinks=False):
        n_dirs += len(dirs)
        n_files += len(files)
    return n_files, n_dirs


def _iter_mtimes(path: str | os.PathLike) -> Iterator[float]:
    p = Path(path)
    yielded = False
    for root, _dirs, files in os.walk(p, followlinks=False):
        for name in files:
            fp = os.path.join(root, name)
            try:
                yield os.lstat(fp).st_mtime
                yielded = True
            except (FileNotFoundError, PermissionError):
                continue
    if not yielded:
        try:
            yield p.stat().st_mtime
        except FileNotFoundError:
            yield 0.0


def mtime_extremes(path: str | os.PathLike) -> tuple[float, float]:
    """Return (oldest_mtime, newest_mtime) over all files under `path`.
    For an empty dir, returns (dir_mtime, dir_mtime)."""
    oldest = float("inf")
    newest = float("-inf")
    for m in _iter_mtimes(path):
        if m < oldest:
            oldest = m
        if m > newest:
            newest = m
    if oldest == float("inf"):
        return 0.0, 0.0
    return oldest, newest


def write_json(path: str | os.PathLike, payload: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str))


def read_json(path: str | os.PathLike) -> object:
    return json.loads(Path(path).read_text())


def human_bytes(n: int) -> str:
    if n < 1024:
        return f"{int(n)} B"
    units = ["KB", "MB", "GB", "TB", "PB"]
    f = float(n) / 1024.0
    for u in units:
        if f < 1024.0 or u == units[-1]:
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} PB"


def timestamp_now() -> str:
    """Local time in YYYYMMDD_HHMMSS form (mirrors QEClaw convention)."""
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str = "scratch_keeper") -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    lg = logging.getLogger(name)
    if not lg.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        lg.addHandler(h)
        lg.setLevel(logging.INFO)
        lg.propagate = False
    _LOGGERS[name] = lg
    return lg
