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
