"""Status verb: print a one-screen summary of last audit, last delete,
backup archives in the store, and rotation warnings."""
from __future__ import annotations

import json
from pathlib import Path

from scratch_keeper.common import human_bytes


def _last_audit(log_dir: Path) -> Path | None:
    files = sorted(log_dir.glob("audit_*.json"))
    return files[-1] if files else None


def _archives(backup_dir: Path) -> list[Path]:
    return sorted(
        list(backup_dir.glob("scratch_backup_*.tar.zst"))
        + list(backup_dir.glob("scratch_backup_*.tar.gz")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _last_delete(log_dir: Path) -> dict | None:
    p = log_dir / "delete_log.jsonl"
    if not p.exists():
        return None
    last = None
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    return last


def run(config: dict) -> dict:
    log_dir = Path(config["log_dir"]).expanduser()
    backup_dir = Path(config["backup_dir"]).expanduser()
    keep_last = int(config.get("backup", {}).get("keep_last", 3))
    last_audit = _last_audit(log_dir) if log_dir.exists() else None
    archives = _archives(backup_dir) if backup_dir.exists() else []
    last_del = _last_delete(log_dir) if log_dir.exists() else None

    print("=== scratch-keeper status ===")
    if last_audit is not None:
        payload = json.loads(last_audit.read_text())
        s = payload["summary"]
        print(f"Last audit:        {last_audit.name}")
        print(f"Total:             {s['total_dirs']} dirs, "
              f"{human_bytes(s['total_bytes'])}")
        print(f"Keepers:           {s['n_keepers']:>2}  "
              f"{human_bytes(s['bytes_keepers'])}")
        print(f"Delete cand:       {s['n_delete_candidates']:>2}  "
              f"{human_bytes(s['bytes_delete_candidates'])}")
        print(f"System:            {s['n_system']:>2}  "
              f"{human_bytes(s['bytes_system'])}")
        print(f"Unknown:           {s['n_unknown']:>2}  "
              f"{human_bytes(s['bytes_unknown'])}")
        if s["n_at_risk"]:
            print(f"At-risk dirs:      {s['n_at_risk']}")
    else:
        print("No audit yet. Run: cluster-manage audit")

    print()
    print(f"Backup archives in {backup_dir}: {len(archives)}")
    for a in archives:
        print(f"  - {a.name}  ({human_bytes(a.stat().st_size)})")
    if len(archives) > keep_last:
        print(f"WARNING: more than keep_last={keep_last} archives present")

    print()
    if last_del is not None:
        print(f"Last delete: {last_del['path']} "
              f"({human_bytes(last_del['freed_bytes'])})")
    else:
        print("No deletions yet.")

    return {
        "last_audit": str(last_audit) if last_audit else None,
        "n_archives": len(archives),
        "last_delete": last_del,
    }
