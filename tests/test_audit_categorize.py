from scratch_keeper.common import Manifest
from scratch_keeper.audit import categorize, DEFAULT_DELETE_CANDIDATES


def test_manifest_keeper_wins(tmp_path):
    m = Manifest(name="raman", path="raman", category="keeper")
    cat, repro, notes = categorize("raman", manifests={"raman": m})
    assert cat == "keeper"
    assert repro is False
    assert notes == ""


def test_manifest_delete_candidate_marks_reproducible():
    m = Manifest(name="qe-agent", path="qe-agent", category="delete-candidate",
                 notes="QEClaw benchmark output")
    cat, repro, notes = categorize("qe-agent", manifests={"qe-agent": m})
    assert cat == "delete-candidate"
    assert repro is True
    assert "benchmark" in notes


def test_protected_dotfile_is_system():
    cat, repro, _ = categorize(
        ".julia",
        manifests={},
        protected_dotfiles=[".julia", ".enroot"],
    )
    assert cat == "system"
    assert repro is False


def test_default_delete_candidate_by_name():
    for name in DEFAULT_DELETE_CANDIDATES:
        cat, repro, _ = categorize(name, manifests={})
        assert cat == "delete-candidate", name
        assert repro is True


def test_unknown_when_no_match():
    cat, repro, _ = categorize("brand_new_dir", manifests={})
    assert cat == "unknown"
    assert repro is None
