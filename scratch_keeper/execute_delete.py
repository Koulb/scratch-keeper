"""Execute-delete verb: read a delete_proposal JSON edited by a human or
agent and delete every row whose `action == "delete"`. Hard guards
prevent accidents."""
from __future__ import annotations

import datetime as _dt
import os
import shutil
from pathlib import Path

from scratch_keeper.common import (
    PathOutsideRootError, ensure_under_root, get_logger,
    human_bytes, load_manifests, read_json, du_bytes,
)


def _drift_ok(claimed_bytes: int, real_bytes: int) -> bool:
    if claimed_bytes <= 0:
        return real_bytes == 0
    ratio = real_bytes / claimed_bytes
    return 0.9 <= ratio <= 1.1


def run(
    config: dict,
    *,
    proposal_path: Path,
    confirm: bool = False,
    max_rows: int | None = None,
    max_bytes_gb: int | None = None,
    allow_dotfiles: bool = False,
) -> dict:
    log = get_logger("scratch_keeper.execute_delete")
    if not confirm:
        return {"deleted": 0, "freed_bytes": 0, "errors": [],
                "status": "missing --confirm flag; refusing to delete"}

    proposal = read_json(proposal_path)
    rows = [c for c in proposal["candidates"] if c.get("action") == "delete"]

    scratch_root = Path(config["scratch_root"])
    dcfg = config.get("delete", {})
    cap_rows = max_rows if max_rows is not None else int(dcfg.get("default_max_rows", 50))
    cap_bytes = (max_bytes_gb if max_bytes_gb is not None
                 else int(dcfg.get("default_max_bytes_gb", 5000))) * (1024 ** 3)
    protected = list(dcfg.get("protected_dotfiles", []))

    keepers: set[str] = set()
    pdir_str = config.get("projects_dir", "")
    if pdir_str:
        pdir = Path(pdir_str).expanduser()
        if pdir.exists():
            for path_key, m in load_manifests(pdir).items():
                if m.category == "keeper":
                    keepers.add(path_key)

    log_dir = Path(config["log_dir"]).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_jsonl = log_dir / "delete_log.jsonl"

    deleted = 0
    freed = 0
    errors: list[str] = []

    for row in rows:
        if deleted >= cap_rows:
            errors.append(f"max-rows cap ({cap_rows}) reached; stopping")
            break
        if freed >= cap_bytes:
            errors.append(f"max-bytes-gb cap reached; stopping")
            break

        path_raw = row["path"]
        try:
            resolved = ensure_under_root(path_raw, scratch_root)
        except PathOutsideRootError as exc:
            errors.append(f"{path_raw}: outside scratch_root ({exc})")
            continue

        if resolved.parent != scratch_root.resolve():
            errors.append(f"{resolved}: not a direct child of scratch_root")
            continue

        name = resolved.name
        if name in keepers:
            errors.append(f"{resolved}: refused; manifest marks as keeper")
            continue

        if name.startswith(".") and not allow_dotfiles:
            errors.append(f"{resolved}: refused; dotfile ({name}) without --allow-dotfiles")
            continue
        if name in protected and not allow_dotfiles:
            errors.append(f"{resolved}: refused; in protected_dotfiles list")
            continue

        if not resolved.exists():
            errors.append(f"{resolved}: missing on disk")
            continue

        real_size = du_bytes(resolved)
        if not _drift_ok(row.get("size_bytes", 0), real_size):
            errors.append(
                f"{resolved}: drift > 10% "
                f"(claimed={row.get('size_bytes')} real={real_size})"
            )
            continue

        log.info("removing %s (%s)", resolved, human_bytes(real_size))
        shutil.rmtree(resolved)
        deleted += 1
        freed += real_size

        with log_jsonl.open("a") as fh:
            fh.write(__import__("json").dumps({
                "ts_utc": _dt.datetime.utcnow().isoformat() + "Z",
                "path": str(resolved),
                "freed_bytes": real_size,
                "proposal_ref": str(proposal_path),
            }) + "\n")

    print(f"Deleted {deleted} rows, freed {human_bytes(freed)}.")
    if errors:
        print("Issues:")
        for e in errors:
            print(f"  - {e}")
    return {"deleted": deleted, "freed_bytes": freed,
            "errors": errors, "status": "ok"}
