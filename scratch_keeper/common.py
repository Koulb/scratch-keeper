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
