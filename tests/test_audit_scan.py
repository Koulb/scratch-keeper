import os
import time
from scratch_keeper.audit import scan_dir
from scratch_keeper.common import Manifest


def _make_dir(p, *, n_files=1, mtime=None):
    p.mkdir(parents=True, exist_ok=True)
    for i in range(n_files):
        f = p / f"f{i}"
        f.write_bytes(b"a" * 100)
        if mtime is not None:
            os.utime(f, (mtime, mtime))
    if mtime is not None:
        os.utime(p, (mtime, mtime))


def test_scan_dir_keeper(tmp_path):
    target = tmp_path / "raman"
    _make_dir(target, n_files=3)
    m = Manifest(name="raman", path="raman", category="keeper",
                 notes="active project")
    row = scan_dir(target, manifests={"raman": m},
                   reaper_max_days=30, protected_dotfiles=[])
    assert row["name"] == "raman"
    assert row["category"] == "keeper"
    assert row["reproducible"] is False
    assert row["n_files"] == 3
    assert row["size_bytes"] >= 300
    assert row["notes"] == "active project"
    assert isinstance(row["days_until_reap"], int)


def test_scan_dir_at_risk_when_recent_mtime_is_old(tmp_path):
    target = tmp_path / "old_proj"
    _make_dir(target, n_files=1, mtime=time.time() - 25 * 86400)
    row = scan_dir(target, manifests={}, reaper_max_days=30,
                   protected_dotfiles=[])
    assert row["category"] == "unknown"
    assert row["days_until_reap"] <= 5


def test_scan_dir_unknown_category_when_no_match(tmp_path):
    target = tmp_path / "weird"
    _make_dir(target, n_files=1)
    row = scan_dir(target, manifests={}, reaper_max_days=30,
                   protected_dotfiles=[])
    assert row["category"] == "unknown"
    assert row["reproducible"] is None
