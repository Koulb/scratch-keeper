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
