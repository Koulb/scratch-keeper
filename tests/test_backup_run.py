import json
from pathlib import Path
from scratch_keeper.backup import run as backup_run


def _write(p, body=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def _audit_payload(scratch):
    return {
        "rows": [
            {"name": "raman", "path": str(scratch / "raman"),
             "category": "keeper", "size_bytes": 100,
             "n_files": 1, "n_dirs": 0,
             "oldest_mtime": "2026-01-01", "newest_mtime": "2026-05-01",
             "days_until_reap": 5, "reproducible": False, "notes": ""},
            {"name": "qe-agent", "path": str(scratch / "qe-agent"),
             "category": "delete-candidate", "size_bytes": 100,
             "n_files": 1, "n_dirs": 0,
             "oldest_mtime": "2026-01-01", "newest_mtime": "2026-05-01",
             "days_until_reap": 5, "reproducible": True, "notes": ""},
        ],
        "summary": {},
    }


def test_backup_run_archives_only_keepers(tmp_path):
    scratch = tmp_path / "scratch"
    _write(scratch / "raman" / "scf.in", "x")
    _write(scratch / "qe-agent" / "bench.in", "y")
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "raman.json").write_text(json.dumps({
        "name": "raman", "path": "raman", "category": "keeper",
        "backup_globs": ["**/*.in"], "exclude_globs": [],
        "touch_globs": [], "touch_exclude_globs": [],
        "notes": "",
    }))
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit_payload(scratch)))
    config = {
        "scratch_root": str(scratch),
        "backup_dir": str(tmp_path / "backups"),
        "log_dir": str(tmp_path / "logs"),
        "projects_dir": str(pdir),
        "backup": {"compressor": "gzip", "zstd_level": 6,
                   "zstd_threads": 0, "keep_last": 3, "verify": True},
    }
    out = backup_run(config, audit_path=audit_path)
    assert out["n_files"] >= 1
    tar_path = Path(out["tar_path"])
    assert tar_path.exists()
    import tarfile
    with tarfile.open(tar_path, "r:gz") as t:
        names = [m.name for m in t.getmembers() if m.isfile()]
    assert any("raman/" in n for n in names)
    assert all("qe-agent" not in n for n in names)


def test_backup_run_rotates_old_archives(tmp_path):
    scratch = tmp_path / "scratch"
    _write(scratch / "raman" / "scf.in", "x")
    backups = tmp_path / "backups"
    backups.mkdir()
    for i in range(4):
        (backups / f"scratch_backup_2024010{i}_000000.tar.gz").write_text("old")
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "raman.json").write_text(json.dumps({
        "name": "raman", "path": "raman", "category": "keeper",
        "backup_globs": ["**/*.in"], "exclude_globs": [],
        "touch_globs": [], "touch_exclude_globs": [],
        "notes": "",
    }))
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit_payload(scratch)))
    config = {
        "scratch_root": str(scratch),
        "backup_dir": str(backups),
        "log_dir": str(tmp_path / "logs"),
        "projects_dir": str(pdir),
        "backup": {"compressor": "gzip", "zstd_level": 6,
                   "zstd_threads": 0, "keep_last": 2, "verify": True},
    }
    out = backup_run(config, audit_path=audit_path)
    assert "rotation_warnings" in out
    assert len(out["rotation_warnings"]) >= 1
