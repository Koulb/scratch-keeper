import json
from pathlib import Path
from scratch_keeper.audit import run as audit_run


def _make(p, n=1):
    p.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (p / f"f{i}").write_bytes(b"x" * 100)


def _fake_config(tmp_path):
    return {
        "scratch_root": str(tmp_path / "scratch"),
        "log_dir": str(tmp_path / "logs"),
        "projects_dir": str(tmp_path / "projects"),
        "reaper": {"max_days_idle": 30, "warn_threshold_days": 7},
        "audit": {"parallel_workers": 2, "cache_ttl_minutes": 60},
        "delete": {"protected_dotfiles": [".julia"]},
    }


def test_audit_run_writes_json_and_returns_path(tmp_path):
    scratch = tmp_path / "scratch"
    _make(scratch / "raman", n=2)
    _make(scratch / "qe-agent", n=5)
    _make(scratch / ".julia", n=1)
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "raman.json").write_text(json.dumps({
        "name": "raman", "path": "raman", "category": "keeper",
        "backup_globs": [], "exclude_globs": [],
        "touch_globs": [], "touch_exclude_globs": [],
        "notes": "active",
    }))
    out = audit_run(_fake_config(tmp_path))
    out_path = Path(out["audit_path"])
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    by_name = {r["name"]: r for r in payload["rows"]}
    assert by_name["raman"]["category"] == "keeper"
    assert by_name["qe-agent"]["category"] == "delete-candidate"
    assert by_name[".julia"]["category"] == "system"
    assert payload["summary"]["n_keepers"] == 1
    assert payload["summary"]["n_delete_candidates"] == 1


def test_audit_run_summary_counts_at_risk(tmp_path):
    import os
    import time
    scratch = tmp_path / "scratch"
    _make(scratch / "old", n=1)
    f = scratch / "old" / "f0"
    old_ts = time.time() - 26 * 86400
    os.utime(f, (old_ts, old_ts))
    out = audit_run(_fake_config(tmp_path))
    payload = json.loads(Path(out["audit_path"]).read_text())
    assert payload["summary"]["n_at_risk"] >= 1


def test_audit_run_summary_aggregates_inode_counts(tmp_path):
    scratch = tmp_path / "scratch"
    _make(scratch / "raman", n=3)
    _make(scratch / "qe-agent", n=5)
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "raman.json").write_text(json.dumps({
        "name": "raman", "path": "raman", "category": "keeper",
    }))
    out = audit_run(_fake_config(tmp_path))
    payload = json.loads(Path(out["audit_path"]).read_text())
    s = payload["summary"]
    assert s["total_files"] == 8
    assert s["files_keepers"] == 3
    assert s["files_delete_candidates"] == 5
    assert s["files_system"] == 0
    assert s["files_unknown"] == 0


def test_audit_run_attaches_quota_when_detect_succeeds(tmp_path, monkeypatch):
    from scratch_keeper import audit as audit_mod
    monkeypatch.setattr(
        audit_mod, "lfs_quota",
        lambda path, **_: {
            "files_used": 50_000, "files_limit": 1_000_000,
            "kbytes_used": 1024, "kbytes_limit": 4096,
        },
    )
    scratch = tmp_path / "scratch"
    _make(scratch / "raman", n=1)
    cfg = _fake_config(tmp_path)
    cfg["quota"] = {"auto_detect": True, "warn_threshold_pct": 80}
    out = audit_run(cfg)
    payload = json.loads(Path(out["audit_path"]).read_text())
    assert payload["quota"]["files_used"] == 50_000
    assert payload["quota"]["files_limit"] == 1_000_000
    assert payload["quota"]["files_pct"] == 5.0


def test_audit_run_skips_quota_when_detect_returns_none(tmp_path, monkeypatch):
    from scratch_keeper import audit as audit_mod
    monkeypatch.setattr(audit_mod, "lfs_quota", lambda path, **_: None)
    scratch = tmp_path / "scratch"
    _make(scratch / "raman", n=1)
    cfg = _fake_config(tmp_path)
    cfg["quota"] = {"auto_detect": True}
    out = audit_run(cfg)
    payload = json.loads(Path(out["audit_path"]).read_text())
    assert payload["quota"] is None


def test_audit_run_print_includes_inode_line(tmp_path, monkeypatch, capsys):
    from scratch_keeper import audit as audit_mod
    monkeypatch.setattr(
        audit_mod, "lfs_quota",
        lambda path, **_: {
            "files_used": 900_000, "files_limit": 1_000_000,
            "kbytes_used": 1, "kbytes_limit": 2,
        },
    )
    scratch = tmp_path / "scratch"
    _make(scratch / "raman", n=2)
    cfg = _fake_config(tmp_path)
    cfg["quota"] = {"auto_detect": True, "warn_threshold_pct": 80}
    audit_run(cfg)
    captured = capsys.readouterr().out
    assert "files" in captured
    assert "Inode quota" in captured
    assert "90.0%" in captured
    assert "WARNING" in captured
