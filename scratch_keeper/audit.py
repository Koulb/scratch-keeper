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
    load_manifests, write_json, get_logger, lfs_quota,
    timestamp_now, human_bytes,
)


_CATEGORIES = ("keeper", "delete-candidate", "system", "unknown")
_CAT_KEY = {
    "keeper": "keepers",
    "delete-candidate": "delete_candidates",
    "system": "system",
    "unknown": "unknown",
}


def _summarize(rows: list[dict], warn_threshold: int) -> dict:
    out: dict = {}
    for cat in _CATEGORIES:
        key = _CAT_KEY[cat]
        cat_rows = [r for r in rows if r["category"] == cat]
        out[f"n_{key}"] = len(cat_rows)
        out[f"bytes_{key}"] = sum(r["size_bytes"] for r in cat_rows)
        out[f"files_{key}"] = sum(r["n_files"] for r in cat_rows)
    out["n_at_risk"] = sum(1 for r in rows
                          if r["days_until_reap"] is not None
                          and r["days_until_reap"] <= warn_threshold)
    out["total_bytes"] = sum(r["size_bytes"] for r in rows)
    out["total_files"] = sum(r["n_files"] for r in rows)
    out["total_subdirs"] = sum(r["n_dirs"] for r in rows)
    out["total_dirs"] = len(rows)
    return out


def _print_summary(payload: dict) -> None:
    s = payload["summary"]
    print(f"=== Scratch audit {payload['created_at']} ===")
    print(f"Total: {s['total_dirs']} dirs, {human_bytes(s['total_bytes'])}, "
          f"{s['total_files']} files")
    print(f"Keepers          ({s['n_keepers']:>2}): "
          f"{human_bytes(s['bytes_keepers'])}, {s['files_keepers']} files")
    print(f"Delete cand      ({s['n_delete_candidates']:>2}): "
          f"{human_bytes(s['bytes_delete_candidates'])}, "
          f"{s['files_delete_candidates']} files")
    print(f"System           ({s['n_system']:>2}): "
          f"{human_bytes(s['bytes_system'])}, {s['files_system']} files")
    print(f"Unknown          ({s['n_unknown']:>2}): "
          f"{human_bytes(s['bytes_unknown'])}, {s['files_unknown']} files")
    if s["n_at_risk"]:
        print(f"At-risk dirs (mtime within warn window): {s['n_at_risk']}")
    q = payload.get("quota")
    if q and q.get("files_limit"):
        warn = ""
        if q.get("files_pct") is not None and q["files_pct"] >= q.get(
            "warn_threshold_pct", 80
        ):
            warn = "  WARNING"
        print(f"Inode quota: {q['files_used']:,} / {q['files_limit']:,} "
              f"({q['files_pct']:.1f}%){warn}")


def _detect_quota(config: dict, scratch: Path) -> dict | None:
    qcfg = config.get("quota") or {}
    if not qcfg.get("auto_detect", True):
        return None
    override = qcfg.get("max_inodes_override")
    warn_pct = float(qcfg.get("warn_threshold_pct", 80))
    if override:
        return {
            "files_used": None,
            "files_limit": int(override),
            "files_pct": None,
            "warn_threshold_pct": warn_pct,
            "source": "override",
        }
    raw = lfs_quota(scratch)
    if not raw:
        return None
    files_used = raw["files_used"]
    files_limit = raw["files_limit"]
    pct = (files_used / files_limit * 100.0) if files_limit else None
    return {
        "files_used": files_used,
        "files_limit": files_limit,
        "files_pct": round(pct, 2) if pct is not None else None,
        "kbytes_used": raw["kbytes_used"],
        "kbytes_limit": raw["kbytes_limit"],
        "warn_threshold_pct": warn_pct,
        "source": "lfs",
    }


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
    quota = _detect_quota(config, scratch)
    ts = timestamp_now()
    payload = {
        "created_at": ts,
        "scratch_root": str(scratch),
        "rows": rows,
        "summary": summary,
        "quota": quota,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"audit_{ts}.json"
    write_json(out_path, payload)
    _print_summary(payload)
    return {"audit_path": str(out_path), "summary": summary}
