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
