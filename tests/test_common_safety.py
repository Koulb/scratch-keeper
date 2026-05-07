import pytest
from pathlib import Path
from scratch_keeper.common import ensure_under_root, PathOutsideRootError


def test_path_inside_root_passes(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    inside = root / "raman"
    inside.mkdir()
    assert ensure_under_root(inside, root) == inside.resolve()


def test_path_equal_to_root_refused(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    with pytest.raises(PathOutsideRootError):
        ensure_under_root(root, root)


def test_path_outside_root_refused(tmp_path):
    root = tmp_path / "scratch"
    other = tmp_path / "other"
    root.mkdir()
    other.mkdir()
    with pytest.raises(PathOutsideRootError):
        ensure_under_root(other, root)


def test_symlink_escaping_root_refused(tmp_path):
    root = tmp_path / "scratch"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    link.symlink_to(outside)
    with pytest.raises(PathOutsideRootError):
        ensure_under_root(link, root)


def test_relative_path_resolved_against_root(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    (root / "raman").mkdir()
    assert ensure_under_root("raman", root) == (root / "raman").resolve()


def test_traversal_attempt_refused(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    with pytest.raises(PathOutsideRootError):
        ensure_under_root(root / ".." / "etc", root)
