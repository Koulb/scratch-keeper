import json
import pytest
from pathlib import Path
from scratch_keeper.execute_delete import run as execute_run


def _proposal(tmp_path, candidates):
    p = tmp_path / "proposal.json"
    p.write_text(json.dumps({
        "audit_ref": "x", "created_utc": "x",
        "candidates": candidates,
        "summary": {"total_candidates": len(candidates),
                    "default_delete": 0, "default_keep_for_review": 0,
                    "bytes_if_all_delete": 0},
    }))
    return p


def _candidate(path, *, action="delete", size=None):
    p = Path(path)
    if size is None:
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return {
        "path": str(p), "size_bytes": size, "size_human": "",
        "n_files": 1, "oldest_mtime": None, "newest_mtime": None,
        "reason": "", "reproducible": True, "score": 99.0,
        "action": action,
    }


def _config(scratch, projects=None):
    return {
        "scratch_root": str(scratch),
        "log_dir": str(scratch.parent / "logs"),
        "projects_dir": str(scratch.parent / "projects") if projects else "",
        "delete": {
            "default_max_rows": 50,
            "default_max_bytes_gb": 5000,
            "protected_dotfiles": [".julia"],
        },
    }


def test_requires_confirm_flag(tmp_path):
    scratch = tmp_path / "scratch"
    target = scratch / "qe-agent"
    target.mkdir(parents=True)
    (target / "f").write_text("x")
    proposal = _proposal(tmp_path, [_candidate(target)])
    out = execute_run(_config(scratch), proposal_path=proposal, confirm=False)
    assert out["deleted"] == 0
    assert target.exists()
    assert "missing --confirm" in out["status"].lower()


def test_refuses_path_outside_scratch_root(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "f").write_text("x")
    proposal = _proposal(tmp_path, [_candidate(outside)])
    out = execute_run(_config(scratch), proposal_path=proposal, confirm=True)
    assert out["deleted"] == 0
    assert outside.exists()
    assert any("outside" in e.lower() for e in out["errors"])


def test_refuses_keeper_listed_in_manifest(tmp_path):
    scratch = tmp_path / "scratch"
    target = scratch / "raman"
    target.mkdir(parents=True)
    (target / "f").write_text("x")
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "raman.json").write_text(json.dumps({
        "name": "raman", "path": "raman", "category": "keeper",
        "backup_globs": [], "exclude_globs": [],
        "touch_globs": [], "touch_exclude_globs": [], "notes": "",
    }))
    proposal = _proposal(tmp_path, [_candidate(target)])
    cfg = _config(scratch, projects=True)
    out = execute_run(cfg, proposal_path=proposal, confirm=True)
    assert out["deleted"] == 0
    assert target.exists()
    assert any("keeper" in e.lower() for e in out["errors"])


def test_refuses_dotfile_unless_allowed(tmp_path):
    scratch = tmp_path / "scratch"
    target = scratch / ".julia"
    target.mkdir(parents=True)
    (target / "f").write_text("x")
    proposal = _proposal(tmp_path, [_candidate(target)])
    out = execute_run(_config(scratch), proposal_path=proposal, confirm=True)
    assert out["deleted"] == 0
    assert target.exists()


def test_actually_deletes_when_clean(tmp_path):
    scratch = tmp_path / "scratch"
    target = scratch / "qe-agent"
    target.mkdir(parents=True)
    (target / "f").write_text("x" * 10)
    proposal = _proposal(tmp_path, [_candidate(target)])
    out = execute_run(_config(scratch), proposal_path=proposal, confirm=True)
    assert out["deleted"] == 1
    assert not target.exists()


def test_drift_check_aborts_row_when_size_changed(tmp_path):
    scratch = tmp_path / "scratch"
    target = scratch / "qe-agent"
    target.mkdir(parents=True)
    (target / "f").write_text("x" * 10)
    cand = _candidate(target, size=10_000_000_000)  # claim much bigger
    proposal = _proposal(tmp_path, [cand])
    out = execute_run(_config(scratch), proposal_path=proposal, confirm=True)
    assert out["deleted"] == 0
    assert target.exists()
    assert any("drift" in e.lower() for e in out["errors"])


def test_max_rows_cap_blocks_excess(tmp_path):
    scratch = tmp_path / "scratch"
    cands = []
    for i in range(3):
        t = scratch / f"qe-agent-{i}"
        t.mkdir(parents=True)
        (t / "f").write_text("x")
        cands.append(_candidate(t))
    proposal = _proposal(tmp_path, cands)
    cfg = _config(scratch)
    out = execute_run(cfg, proposal_path=proposal, confirm=True, max_rows=2)
    assert out["deleted"] == 2
