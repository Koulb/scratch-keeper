import json
import time
from pathlib import Path
from scratch_keeper.status import run as status_run


def test_status_summarizes_last_audit_and_archives(tmp_path, capsys):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "audit_20260507_140000.json").write_text(json.dumps({
        "created_at": "20260507_140000",
        "rows": [],
        "summary": {
            "n_keepers": 6, "bytes_keepers": 4 * 1024**4,
            "n_delete_candidates": 15, "bytes_delete_candidates": 8 * 1024**4,
            "n_system": 5, "bytes_system": 1 * 1024**3,
            "n_unknown": 11, "bytes_unknown": 1 * 1024**4,
            "n_at_risk": 3, "total_bytes": 14 * 1024**4, "total_dirs": 37,
        },
    }))
    backups = tmp_path / "backups"
    backups.mkdir()
    a = backups / "scratch_backup_20260507_140030.tar.gz"
    a.write_text("dummy")
    (log_dir / "delete_log.jsonl").write_text(
        json.dumps({"ts_utc": "x", "path": "/scratch/qe-agent",
                    "freed_bytes": 4 * 1024**4, "proposal_ref": "p"}) + "\n"
    )
    config = {
        "scratch_root": str(tmp_path),
        "log_dir": str(log_dir),
        "backup_dir": str(backups),
        "backup": {"keep_last": 3},
    }
    out = status_run(config)
    cap = capsys.readouterr().out
    assert "37 dirs" in cap
    assert "Keepers" in cap
    assert "scratch_backup_20260507_140030" in cap
    assert out["last_audit"].endswith("audit_20260507_140000.json")
    assert out["n_archives"] == 1
