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


from concurrent.futures import ThreadPoolExecutor

from scratch_keeper.common import (
    load_manifests, write_json, get_logger,
    timestamp_now, human_bytes,
)


def _summarize(rows: list[dict], warn_threshold: int) -> dict:
    n_keepers = sum(1 for r in rows if r["category"] == "keeper")
    n_del = sum(1 for r in rows if r["category"] == "delete-candidate")
    n_sys = sum(1 for r in rows if r["category"] == "system")
    n_unk = sum(1 for r in rows if r["category"] == "unknown")
    bytes_keepers = sum(r["size_bytes"] for r in rows if r["category"] == "keeper")
    bytes_del = sum(r["size_bytes"] for r in rows if r["category"] == "delete-candidate")
    bytes_sys = sum(r["size_bytes"] for r in rows if r["category"] == "system")
    bytes_unk = sum(r["size_bytes"] for r in rows if r["category"] == "unknown")
    n_at_risk = sum(1 for r in rows
                    if r["days_until_reap"] is not None
                    and r["days_until_reap"] <= warn_threshold)
    return {
        "n_keepers": n_keepers, "bytes_keepers": bytes_keepers,
        "n_delete_candidates": n_del, "bytes_delete_candidates": bytes_del,
        "n_system": n_sys, "bytes_system": bytes_sys,
        "n_unknown": n_unk, "bytes_unknown": bytes_unk,
        "n_at_risk": n_at_risk,
        "total_bytes": sum(r["size_bytes"] for r in rows),
        "total_dirs": len(rows),
    }


def _print_summary(payload: dict) -> None:
    s = payload["summary"]
    print(f"=== Scratch audit {payload['created_at']} ===")
    print(f"Total: {s['total_dirs']} dirs, {human_bytes(s['total_bytes'])}")
    print(f"Keepers          ({s['n_keepers']:>2}): {human_bytes(s['bytes_keepers'])}")
    print(f"Delete cand      ({s['n_delete_candidates']:>2}): {human_bytes(s['bytes_delete_candidates'])}")
    print(f"System           ({s['n_system']:>2}): {human_bytes(s['bytes_system'])}")
    print(f"Unknown          ({s['n_unknown']:>2}): {human_bytes(s['bytes_unknown'])}")
    if s["n_at_risk"]:
        print(f"At-risk dirs (mtime within warn window): {s['n_at_risk']}")


def run(config: dict, *, quick: bool = False) -> dict:
    """Walk scratch_root one level deep, scan each top-level dir, write JSON."""
    log = get_logger("scratch_keeper.audit")
    scratch = Path(config["scratch_root"])
    log_dir = Path(config["log_dir"]).expanduser()
    projects_dir = Path(config["projects_dir"]).expanduser()
    workers = int(config.get("audit", {}).get("parallel_workers", 4))
    reaper_max = int(config.get("reaper", {}).get("max_days_idle", 30))
    warn_thr = int(config.get("reaper", {}).get("warn_threshold_days", 7))
    protected = list(config.get("delete", {}).get("protected_dotfiles", []))

    if not scratch.exists():
        raise FileNotFoundError(f"scratch_root not found: {scratch}")

    manifests = load_manifests(projects_dir) if projects_dir.exists() else {}

    top_level = sorted(p for p in scratch.iterdir() if p.is_dir())
    log.info("scanning %d top-level dirs in %s", len(top_level), scratch)

    rows: list[dict] = []
    if workers <= 1 or quick:
        for p in top_level:
            rows.append(scan_dir(
                p, manifests=manifests,
                reaper_max_days=reaper_max,
                protected_dotfiles=protected,
            ))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(scan_dir, p,
                              manifests=manifests,
                              reaper_max_days=reaper_max,
                              protected_dotfiles=protected)
                    for p in top_level]
            rows = [f.result() for f in futs]

    rows.sort(key=lambda r: -r["size_bytes"])
    summary = _summarize(rows, warn_thr)
    ts = timestamp_now()
    payload = {
        "created_at": ts,
        "scratch_root": str(scratch),
        "rows": rows,
        "summary": summary,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"audit_{ts}.json"
    write_json(out_path, payload)
    _print_summary(payload)
    return {"audit_path": str(out_path), "summary": summary}
