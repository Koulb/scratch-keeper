"""Propose-delete verb: read audit JSON, build a delete proposal JSON
with per-candidate score and default action. Never deletes anything."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from scratch_keeper.audit import DEFAULT_DELETE_CANDIDATES
from scratch_keeper.common import (
    read_json, write_json, timestamp_now, human_bytes, get_logger,
)


CACHE_NAME_HINTS: tuple[str, ...] = (
    "pip_cache", "julia_depot", "sssp-cache", "qeclaw_pseudo",
    "venvs", "deephe3_venv",
)


def _days_old(row: dict) -> int:
    if row.get("newest_mtime") is None:
        return 0
    try:
        newest = _dt.datetime.fromisoformat(row["newest_mtime"])
    except ValueError:
        return 0
    return max(0, (_dt.datetime.now() - newest).days)


def score_row(row: dict, weights: dict[str, float],
              name_match_set: set[str]) -> float:
    days = _days_old(row)
    age_n = min(1.0, days / 90.0)
    repro_n = 1.0 if row.get("reproducible") else 0.0
    size_gb = row.get("size_bytes", 0) / (1024 ** 3)
    size_n = min(1.0, size_gb / 1000.0)
    name = Path(row["path"]).name
    name_n = 1.0 if name in name_match_set else 0.0
    raw = (
        weights.get("age_days", 0.0) * age_n
        + weights.get("reproducible", 0.0) * repro_n
        + weights.get("size_gb", 0.0) * size_n
        + weights.get("name_match", 0.0) * name_n
    )
    total_w = sum(weights.values()) or 1.0
    return round(100.0 * raw / total_w, 1)


def _reason_for(row: dict) -> str:
    name = Path(row["path"]).name
    bits = []
    if row["category"] == "delete-candidate":
        bits.append("delete-candidate by manifest/heuristic")
    if name in DEFAULT_DELETE_CANDIDATES:
        bits.append(f"name in default delete set ({name})")
    if name in CACHE_NAME_HINTS:
        bits.append("looks like a regenerable cache")
    if row["category"] == "unknown":
        bits.append("unknown — REVIEW before delete")
    return "; ".join(bits) or "—"


def build_candidates(
    rows: list[dict],
    *,
    include_unknown: bool,
    min_size_gb: float,
    score_weights: dict[str, float],
) -> list[dict]:
    name_match = set(DEFAULT_DELETE_CANDIDATES) | set(CACHE_NAME_HINTS)
    out: list[dict] = []
    for r in rows:
        if r["category"] == "keeper" or r["category"] == "system":
            continue
        is_unknown_bulk = (
            r["category"] == "unknown"
            and _days_old(r) > 60
            and r["n_files"] > 1000
        )
        if r["category"] != "delete-candidate" and not include_unknown:
            if not is_unknown_bulk:
                continue
        if r["size_bytes"] < min_size_gb * (1024 ** 3):
            continue
        action = "delete" if (r["category"] == "delete-candidate"
                              and r.get("reproducible")) else "keep"
        out.append({
            "path": r["path"],
            "size_bytes": r["size_bytes"],
            "size_human": human_bytes(r["size_bytes"]),
            "n_files": r["n_files"],
            "oldest_mtime": r.get("oldest_mtime"),
            "newest_mtime": r.get("newest_mtime"),
            "reason": _reason_for(r),
            "reproducible": r.get("reproducible"),
            "score": score_row(r, score_weights, name_match),
            "action": action,
        })
    out.sort(key=lambda c: -c["score"])
    return out


def run(config: dict, *, audit_path: Path,
        include_unknown: bool = False,
        auto_mark_reproducible: bool = False,
        min_size_gb: float = 0.0,
        out_path: Path | None = None) -> dict:
    log = get_logger("scratch_keeper.propose_delete")
    audit = read_json(audit_path)
    weights = config.get("delete", {}).get("score_weights", {
        "age_days": 0.4, "reproducible": 0.3,
        "size_gb": 0.2, "name_match": 0.1,
    })
    cands = build_candidates(
        audit["rows"],
        include_unknown=include_unknown,
        min_size_gb=min_size_gb,
        score_weights=weights,
    )
    if auto_mark_reproducible:
        for c in cands:
            if c.get("reproducible"):
                c["action"] = "delete"

    summary = {
        "total_candidates": len(cands),
        "default_delete": sum(1 for c in cands if c["action"] == "delete"),
        "default_keep_for_review": sum(1 for c in cands if c["action"] == "keep"),
        "bytes_if_all_delete": sum(c["size_bytes"] for c in cands),
    }
    proposal = {
        "audit_ref": str(audit_path),
        "created_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "candidates": cands,
        "summary": summary,
    }
    log_dir = Path(config["log_dir"]).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    target = out_path or (log_dir / f"delete_proposal_{timestamp_now()}.json")
    write_json(target, proposal)
    log.info("wrote proposal with %d candidates to %s", len(cands), target)
    print(f"Wrote proposal: {target} (candidates={len(cands)}, "
          f"default delete={summary['default_delete']})")
    return {"proposal_path": str(target), "summary": summary}
