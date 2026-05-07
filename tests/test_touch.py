import json
import os
import time
from pathlib import Path
from scratch_keeper.touch import run as touch_run


def _config(tmp_path, max_age=20):
    return {
        "scratch_root": str(tmp_path / "scratch"),
        "log_dir": str(tmp_path / "logs"),
        "projects_dir": str(tmp_path / "projects"),
        "touch": {"max_age_days": max_age, "workers": 1},
    }


def _project(tmp_path, name, *, touch_globs, touch_exclude_globs=None):
    pdir = tmp_path / "projects"
    pdir.mkdir(exist_ok=True)
    (pdir / f"{name}.json").write_text(json.dumps({
        "name": name, "path": name, "category": "keeper",
        "backup_globs": [], "exclude_globs": [],
        "touch_globs": touch_globs,
        "touch_exclude_globs": touch_exclude_globs or [],
        "notes": "",
    }))


def test_touch_refreshes_old_files(tmp_path):
    scratch = tmp_path / "scratch"
    proj = scratch / "raman"
    proj.mkdir(parents=True)
    f = proj / "scf.in"
    f.write_text("x")
    old_ts = time.time() - 25 * 86400
    os.utime(f, (old_ts, old_ts))
    _project(tmp_path, "raman", touch_globs=["**/*"])
    out = touch_run(_config(tmp_path), max_age_days=20)
    new_mtime = f.stat().st_mtime
    assert new_mtime > old_ts + (3 * 86400)
    assert out["touched_total"] == 1


def test_touch_skips_recent_files(tmp_path):
    scratch = tmp_path / "scratch"
    proj = scratch / "raman"
    proj.mkdir(parents=True)
    f = proj / "scf.in"
    f.write_text("x")  # mtime ~ now
    _project(tmp_path, "raman", touch_globs=["**/*"])
    out = touch_run(_config(tmp_path, max_age=20), max_age_days=20)
    assert out["touched_total"] == 0


def test_touch_respects_exclude_globs(tmp_path):
    scratch = tmp_path / "scratch"
    proj = scratch / "raman"
    (proj / "out").mkdir(parents=True)
    keep = proj / "scf.in"
    skip = proj / "out" / "qeclaw.wfc1"
    keep.write_text("x")
    skip.write_bytes(b"\x00")
    old = time.time() - 25 * 86400
    os.utime(keep, (old, old))
    os.utime(skip, (old, old))
    _project(tmp_path, "raman",
             touch_globs=["**/*"],
             touch_exclude_globs=["**/out/**", "**/*.wfc*"])
    touch_run(_config(tmp_path), max_age_days=20)
    assert keep.stat().st_mtime > old + 86400
    assert skip.stat().st_mtime == old


def test_touch_dry_run_does_not_modify(tmp_path):
    scratch = tmp_path / "scratch"
    proj = scratch / "raman"
    proj.mkdir(parents=True)
    f = proj / "scf.in"
    f.write_text("x")
    old = time.time() - 25 * 86400
    os.utime(f, (old, old))
    _project(tmp_path, "raman", touch_globs=["**/*"])
    out = touch_run(_config(tmp_path), max_age_days=20, dry_run=True)
    assert out["touched_total"] == 0
    assert out["would_touch_total"] == 1
    assert f.stat().st_mtime == old


def test_touch_filters_by_project(tmp_path):
    scratch = tmp_path / "scratch"
    (scratch / "raman").mkdir(parents=True)
    (scratch / "kcw").mkdir()
    fa = scratch / "raman" / "a"
    fb = scratch / "kcw" / "b"
    fa.write_text("x"); fb.write_text("x")
    old = time.time() - 25 * 86400
    os.utime(fa, (old, old)); os.utime(fb, (old, old))
    _project(tmp_path, "raman", touch_globs=["**/*"])
    _project(tmp_path, "kcw", touch_globs=["**/*"])
    out = touch_run(_config(tmp_path), max_age_days=20, only_project="raman")
    assert fa.stat().st_mtime > old + 86400
    assert fb.stat().st_mtime == old
    assert out["projects"][0]["name"] == "raman"
    assert len(out["projects"]) == 1
