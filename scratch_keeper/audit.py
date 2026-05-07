"""Audit verb: walk scratch root one level deep, classify each top-level
entry, write logs/audit_<ts>.json + a printed summary.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from scratch_keeper.common import Manifest


DEFAULT_DELETE_CANDIDATES: tuple[str, ...] = (
    "qe-agent", "qe", "cp2k_tst", "yambo_tst", "reg_tests",
    "dielectric", "phonons", "epw", "daint", "backup_data",
    "probe_logs", "pip_cache", "sssp-cache", "qeclaw_pseudo",
    "venvs", "julia_depot", "deephe3_venv",
)


def categorize(
    name: str,
    *,
    manifests: dict[str, Manifest],
    protected_dotfiles: list[str] | None = None,
) -> tuple[str, Optional[bool], str]:
    """Decide (category, reproducible, notes) for a scratch top-level dir.

    Order:
      1. Manifest match by directory name.
      2. Dotfile in `protected_dotfiles` -> system.
      3. Name in DEFAULT_DELETE_CANDIDATES -> delete-candidate.
      4. Unknown.
    """
    protected = list(protected_dotfiles or [])
    m = manifests.get(name)
    if m is not None:
        repro = m.category == "delete-candidate"
        return m.category, repro, m.notes
    if name in protected:
        return "system", False, "protected dotfile cache"
    if name in DEFAULT_DELETE_CANDIDATES:
        return "delete-candidate", True, "matched default delete-candidate set"
    return "unknown", None, ""


import datetime as _dt
from scratch_keeper.common import (
    du_bytes, count_files_dirs, mtime_extremes,
)


def scan_dir(
    path: str | os.PathLike,
    *,
    manifests: dict[str, Manifest],
    reaper_max_days: int,
    protected_dotfiles: list[str],
) -> dict:
    """Build one audit row for a top-level scratch dir."""
    p = Path(path)
    name = p.name
    cat, repro, notes = categorize(
        name, manifests=manifests, protected_dotfiles=protected_dotfiles,
    )
    size = du_bytes(p)
    n_files, n_dirs = count_files_dirs(p)
    oldest_ts, newest_ts = mtime_extremes(p)
    now = _dt.datetime.now().timestamp()
    days_since_newest = int((now - newest_ts) // 86400)
    days_until_reap = reaper_max_days - days_since_newest
    return {
        "name": name,
        "path": str(p),
        "category": cat,
        "reproducible": repro,
        "size_bytes": size,
        "n_files": n_files,
        "n_dirs": n_dirs,
        "oldest_mtime": _dt.datetime.fromtimestamp(oldest_ts).isoformat()
                       if oldest_ts else None,
        "newest_mtime": _dt.datetime.fromtimestamp(newest_ts).isoformat()
                        if newest_ts else None,
        "days_until_reap": days_until_reap,
        "notes": notes,
    }
