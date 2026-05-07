"""Backup verb: build a per-project file list from globs and stream a
tar archive into the long-term store."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from scratch_keeper.common import Manifest


DEFAULT_BACKUP_GLOBS: tuple[str, ...] = (
    "**/*.in", "**/*.cif", "**/*.UPF", "**/*.upf",
    "**/*.xml", "**/*.out",
    "**/summary.json", "**/parsed/**", "**/plots/**",
    "**/*.png", "**/*.pdf", "**/*.ipynb",
    "**/run.sh", "**/*.slurm",
)
DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    "**/out/**", "**/*.wfc*", "**/*.save/**",
    "**/tmp/**", "**/__pycache__/**", "**/.git/**",
)


def _match_any(rel: str, patterns: list[str]) -> bool:
    rel_posix = rel.replace(os.sep, "/")
    for pat in patterns:
        if fnmatch.fnmatchcase(rel_posix, pat):
            return True
        # `**/` prefix should also match top-level files; emulate.
        if pat.startswith("**/") and fnmatch.fnmatchcase(rel_posix, pat[3:]):
            return True
    return False


def build_file_list(root: str | os.PathLike, manifest: Manifest) -> list[Path]:
    """Walk `root` (a project directory) and return all files matching
    `manifest.backup_globs` minus `manifest.exclude_globs`. Empty
    `backup_globs` falls back to DEFAULT_BACKUP_GLOBS, empty
    `exclude_globs` falls back to DEFAULT_EXCLUDE_GLOBS.
    """
    root_path = Path(root)
    includes = list(manifest.backup_globs) or list(DEFAULT_BACKUP_GLOBS)
    excludes = list(manifest.exclude_globs) or list(DEFAULT_EXCLUDE_GLOBS)

    out: list[Path] = []
    for dirpath, _dirs, files in os.walk(root_path, followlinks=False):
        for name in files:
            full = Path(dirpath) / name
            rel = full.relative_to(root_path).as_posix()
            if not _match_any(rel, includes):
                continue
            if _match_any(rel, excludes):
                continue
            out.append(full)
    return out
