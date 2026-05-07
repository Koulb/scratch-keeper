import json
import os
import time
from pathlib import Path
from scratch_keeper.common import (
    du_bytes, count_files_dirs, mtime_extremes,
    write_json, read_json, get_logger, timestamp_now, human_bytes,
)


def test_du_bytes_sums_apparent_size(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 1000)
    (tmp_path / "b").write_bytes(b"y" * 2000)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c").write_bytes(b"z" * 500)
    assert du_bytes(tmp_path) >= 3500


def test_count_files_dirs(tmp_path):
    (tmp_path / "f1").touch()
    (tmp_path / "f2").touch()
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "f3").touch()
    n_files, n_dirs = count_files_dirs(tmp_path)
    assert n_files == 3
    assert n_dirs == 1


def test_mtime_extremes(tmp_path):
    f1 = tmp_path / "old"
    f1.touch()
    os.utime(f1, (1_700_000_000, 1_700_000_000))
    f2 = tmp_path / "new"
    f2.touch()
    os.utime(f2, (1_750_000_000, 1_750_000_000))
    oldest, newest = mtime_extremes(tmp_path)
    assert oldest == 1_700_000_000
    assert newest == 1_750_000_000


def test_mtime_extremes_empty_dir_returns_dir_mtime(tmp_path):
    oldest, newest = mtime_extremes(tmp_path)
    assert oldest > 0 and newest > 0
    assert oldest == newest


def test_write_then_read_json_roundtrip(tmp_path):
    payload = {"hello": "world", "n": 42}
    p = tmp_path / "out.json"
    write_json(p, payload)
    assert read_json(p) == payload


def test_human_bytes_formats():
    assert human_bytes(0) == "0 B"
    assert human_bytes(1023) == "1023 B"
    assert human_bytes(1024) == "1.0 KB"
    assert human_bytes(1024 * 1024) == "1.0 MB"
    assert human_bytes(2 * 1024**3) == "2.0 GB"
    assert human_bytes(3 * 1024**4) == "3.0 TB"


def test_timestamp_now_format():
    ts = timestamp_now()
    assert len(ts) == 15  # YYYYMMDD_HHMMSS
    assert ts[8] == "_"


def test_get_logger_returns_singleton():
    a = get_logger("scratch_keeper.test")
    b = get_logger("scratch_keeper.test")
    assert a is b


from scratch_keeper.common import _parse_lfs_quota


def test_parse_lfs_quota_basic():
    raw = (
        "Disk quotas for usr apoliukh (uid 25431):\n"
        "     Filesystem  kbytes  quota  limit  grace  files  quota  limit  grace\n"
        "/capstor/scratch/cscs\n"
        "              12345678  0  1099511627776  -  12345  0  1000000  -\n"
    )
    q = _parse_lfs_quota(raw)
    assert q == {
        "kbytes_used": 12345678,
        "kbytes_limit": 1099511627776,
        "files_used": 12345,
        "files_limit": 1000000,
    }


def test_parse_lfs_quota_strips_exceeded_asterisk():
    raw = (
        "Disk quotas for usr foo (uid 1):\n"
        "     Filesystem  kbytes  quota  limit  grace  files  quota  limit  grace\n"
        "/scratch\n"
        "              500000  0  400000*  -  9  0  10*  -\n"
    )
    q = _parse_lfs_quota(raw)
    assert q["files_used"] == 9
    assert q["files_limit"] == 10
    assert q["kbytes_limit"] == 400000


def test_parse_lfs_quota_uses_soft_when_hard_is_zero():
    raw = (
        "Disk quotas for usr foo (uid 1):\n"
        "     Filesystem  kbytes  quota  limit  grace  files  quota  limit  grace\n"
        "/scratch\n"
        "              100  500  0  -  1  9  0  -\n"
    )
    q = _parse_lfs_quota(raw)
    assert q["files_limit"] == 9
    assert q["kbytes_limit"] == 500


def test_parse_lfs_quota_returns_none_for_garbage():
    assert _parse_lfs_quota("") is None
    assert _parse_lfs_quota("nonsense\n") is None


def test_parse_lfs_quota_returns_none_when_all_limits_zero():
    raw = (
        "Disk quotas for usr foo (uid 1):\n"
        "     Filesystem  kbytes  quota  limit  grace  files  quota  limit  grace\n"
        "/scratch\n"
        "              100  0  0  -  1  0  0  -\n"
    )
    assert _parse_lfs_quota(raw) is None
