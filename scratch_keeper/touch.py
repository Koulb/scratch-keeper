"""Touch verb: refresh atime+mtime on files matching per-project
touch_globs, only when older than `max_age_days`. Manifest-driven."""
from __future__ import annotations

import datetime as _dt
import os
import time
from pathlib import Path

from scratch_keeper.backup import _match_any  # reuse shared globber
from scratch_keeper.common import (
    PathOutsideRootError, ensure_under_root, load_manifests,
    get_logger, write_json,
)


def _walk_match(
    root: Path,
    includes: list[str],
    excludes: list[str],
):
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            full = Path(dirpath) / name
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                continue
            if not _match_any(rel, includes):
                continue
            if _match_any(rel, excludes):
                continue
            yield full


def run(
    config: dict,
    *,
    only_project: str | None = None,
    max_age_days: int | None = None,
    dry_run: bool = False,
) -> dict:
    log = get_logger("scratch_keeper.touch")
    scratch_root = Path(config["scratch_root"])
    projects_dir = Path(config["projects_dir"]).expanduser()
    log_dir = Path(config["log_dir"]).expanduser()
    age_cutoff = max_age_days if max_age_days is not None else int(
        config.get("touch", {}).get("max_age_days", 20)
    )
    cutoff_ts = time.time() - age_cutoff * 86400

    manifests = load_manifests(projects_dir) if projects_dir.exists() else {}
    if only_project:
        manifests = {k: m for k, m in manifests.items() if m.name == only_project}

    per_project_results: list[dict] = []
    touched_total = 0
    would_total = 0

    for path_key, m in manifests.items():
        if not m.touch_globs:
            log.info("skipping %s (no touch_globs)", m.name)
            continue
        try:
            proj_root = ensure_under_root(m.path, scratch_root)
        except PathOutsideRootError as exc:
            log.warning("skipping %s: %s", m.name, exc)
            continue
        if not proj_root.exists():
            log.warning("skipping %s: %s missing", m.name, proj_root)
            continue

        seen = 0
        touched = 0
        would = 0
        slowest = (None, 0.0)
        t0 = time.time()
        for f in _walk_match(proj_root, m.touch_globs, m.touch_exclude_globs):
            seen += 1
            try:
                st = f.lstat()
            except FileNotFoundError:
                continue
            if st.st_mtime >= cutoff_ts:
                continue
            if dry_run:
                would += 1
                continue
            try:
                os.utime(f, None)
            except (PermissionError, FileNotFoundError):
                continue
            touched += 1
        elapsed = time.time() - t0
        per_project_results.append({
            "name": m.name, "path": str(proj_root),
            "files_seen": seen, "touched": touched,
            "would_touch": would, "elapsed_s": round(elapsed, 2),
        })
        touched_total += touched
        would_total += would
        log.info("project=%s seen=%d touched=%d would=%d elapsed=%.2fs",
                 m.name, seen, touched, would, elapsed)

    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "touch_log.jsonl").open("a") as fh:
        fh.write(__import__("json").dumps({
            "ts_utc": _dt.datetime.utcnow().isoformat() + "Z",
            "max_age_days": age_cutoff,
            "dry_run": dry_run,
            "projects": per_project_results,
            "touched_total": touched_total,
            "would_touch_total": would_total,
        }) + "\n")

    return {
        "projects": per_project_results,
        "touched_total": touched_total,
        "would_touch_total": would_total,
    }
