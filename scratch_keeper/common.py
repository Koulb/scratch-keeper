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
