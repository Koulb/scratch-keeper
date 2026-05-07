import json
import tarfile
from pathlib import Path
from scratch_keeper.backup import archive_files


def test_archive_creates_tar_gz_and_manifest(tmp_path):
    proj = tmp_path / "src" / "raman"
    (proj / "a").mkdir(parents=True)
    (proj / "a" / "scf.in").write_text("hello")
    (proj / "b.in").write_text("world")
    files = sorted([(proj / "a" / "scf.in"), (proj / "b.in")])

    out = archive_files(
        files=files,
        root=tmp_path / "src",
        out_path=tmp_path / "out" / "scratch_backup_001.tar.gz",
        compressor="gzip",
        verify=True,
    )
    archive = Path(out["tar_path"])
    sidecar = Path(out["manifest_path"])
    assert archive.exists()
    assert sidecar.exists()

    with tarfile.open(archive, "r:gz") as t:
        members = sorted(m.name for m in t.getmembers() if m.isfile())
    assert members == ["raman/a/scf.in", "raman/b.in"]

    sc = json.loads(sidecar.read_text())
    assert sc["tar_path"] == str(archive)
    assert sc["n_files"] == 2
    assert len(sc["sha256"]) == 64


def test_archive_missing_compressor_raises(tmp_path):
    import pytest
    from scratch_keeper.backup import archive_files
    with pytest.raises(ValueError):
        archive_files(
            files=[],
            root=tmp_path,
            out_path=tmp_path / "out.tar.zst",
            compressor="exotic-codec-9000",
            verify=False,
        )
