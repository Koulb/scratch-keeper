import json
import pytest
from scratch_keeper.common import load_config, load_manifests, Manifest


def test_load_config_resolves_user_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "scratch_root": "/capstor/scratch/cscs/apoliukh",
        "store_root": "/capstor/store/cscs/marvel/mr33/apoliukh",
        "backup_dir": "/capstor/store/cscs/marvel/mr33/apoliukh/scratch_backup",
        "log_dir": "~/scratch-keeper/logs",
        "projects_dir": "~/scratch-keeper/projects",
        "reaper": {"max_days_idle": 30, "warn_threshold_days": 7},
        "audit": {"parallel_workers": 4, "cache_ttl_minutes": 60},
        "backup": {"compressor": "zstd", "zstd_level": 6,
                   "zstd_threads": 0, "keep_last": 3, "verify": True},
        "delete": {"default_max_rows": 50, "default_max_bytes_gb": 5000,
                   "protected_dotfiles": [".julia"],
                   "score_weights": {"age_days": 0.4, "reproducible": 0.3,
                                     "size_gb": 0.2, "name_match": 0.1}},
        "touch": {"max_age_days": 20, "workers": 4}
    }))
    cfg = load_config(cfg_path)
    assert cfg["log_dir"] == str(tmp_path / "scratch-keeper" / "logs")
    assert cfg["projects_dir"] == str(tmp_path / "scratch-keeper" / "projects")
    assert cfg["scratch_root"] == "/capstor/scratch/cscs/apoliukh"


def test_load_manifests_reads_all_json_files(tmp_path):
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "raman.json").write_text(json.dumps({
        "name": "raman", "path": "raman", "category": "keeper",
        "backup_globs": ["**/*.in"], "exclude_globs": [],
        "touch_globs": ["**/*"], "touch_exclude_globs": [],
        "notes": ""
    }))
    (pdir / "kcw.json").write_text(json.dumps({
        "name": "kcw", "path": "kcw-hpro", "category": "keeper",
        "backup_globs": [], "exclude_globs": [],
        "touch_globs": [], "touch_exclude_globs": [],
        "notes": ""
    }))
    (pdir / "not_a_manifest.txt").write_text("ignore me")
    manifests = load_manifests(pdir)
    assert set(manifests.keys()) == {"raman", "kcw-hpro"}
    assert isinstance(manifests["raman"], Manifest)
    assert manifests["raman"].name == "raman"
    assert manifests["kcw-hpro"].path == "kcw-hpro"


def test_load_manifests_rejects_missing_required_field(tmp_path):
    pdir = tmp_path / "projects"
    pdir.mkdir()
    (pdir / "broken.json").write_text(json.dumps({"name": "broken"}))
    with pytest.raises(ValueError, match="missing"):
        load_manifests(pdir)
