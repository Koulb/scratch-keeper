from pathlib import Path
from scratch_keeper.common import Manifest
from scratch_keeper.backup import build_file_list, DEFAULT_BACKUP_GLOBS


def test_build_file_list_uses_manifest_globs(tmp_path):
    proj = tmp_path / "raman"
    (proj / "a").mkdir(parents=True)
    (proj / "a" / "scf.in").write_text("&CONTROL")
    (proj / "a" / "scf.out").write_text("ok")
    (proj / "a" / "out").mkdir()
    (proj / "a" / "out" / "qeclaw.wfc1").write_bytes(b"\x00" * 1000)
    m = Manifest(
        name="raman", path="raman", category="keeper",
        backup_globs=["**/*.in", "**/*.out"],
        exclude_globs=["**/out/**", "**/*.wfc*"],
    )
    files = build_file_list(proj, m)
    rels = sorted(f.relative_to(proj).as_posix() for f in files)
    assert rels == ["a/scf.in", "a/scf.out"]


def test_build_file_list_falls_back_to_default_globs(tmp_path):
    proj = tmp_path / "kcw"
    (proj / "x").mkdir(parents=True)
    (proj / "x" / "input.in").write_text("")
    (proj / "x" / "junk.bin").write_bytes(b"\x00")
    m = Manifest(name="kcw", path="kcw", category="keeper",
                 backup_globs=[], exclude_globs=[])
    files = build_file_list(proj, m)
    assert any(f.name == "input.in" for f in files)
    assert all(f.name != "junk.bin" for f in files)
    assert "**/*.in" in DEFAULT_BACKUP_GLOBS


def test_build_file_list_excludes_win_over_includes(tmp_path):
    proj = tmp_path / "p"
    (proj / "deep").mkdir(parents=True)
    (proj / "deep" / "scf.in").write_text("")
    (proj / "deep" / "scf.in.bak").write_text("")
    m = Manifest(
        name="p", path="p", category="keeper",
        backup_globs=["**/*.in", "**/*.in.bak"],
        exclude_globs=["**/*.bak"],
    )
    files = build_file_list(proj, m)
    rels = sorted(f.name for f in files)
    assert rels == ["scf.in"]
