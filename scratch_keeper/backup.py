"""Backup verb: build a per-project file list from globs and stream a
tar archive into the long-term store."""
from __future__ import annotations

import datetime as _dt
import fnmatch
import hashlib
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from scratch_keeper.common import (
    Manifest, write_json, get_logger,
    load_manifests, read_json, timestamp_now,
)


DEFAULT_BACKUP_GLOBS: tuple[str, ...] = (
    "**/*.in", "**/*.cif", "**/*.UPF", "**/*.upf",
    "**/*.xml", "**/*.out",
    "**/summary.json", "**/parsed/**", "**/plots/**",
    "**/*.png", "**/*.pdf", "**/*.ipynb",
    "**/run.sh", "**/*.slurm",
)
DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    "**/out/**", "**/*.wfc*", "**/*.save/**",
    "**/tmp/**", "**/__pycache__/**", "**/.git/**",
)


def _match_any(rel: str, patterns: list[str]) -> bool:
    rel_posix = rel.replace(os.sep, "/")
    for pat in patterns:
        if fnmatch.fnmatchcase(rel_posix, pat):
            return True
        # `**/` prefix should also match top-level files; emulate.
        if pat.startswith("**/") and fnmatch.fnmatchcase(rel_posix, pat[3:]):
            return True
    return False


def build_file_list(root: str | os.PathLike, manifest: Manifest) -> list[Path]:
    """Walk `root` (a project directory) and return all files matching
    `manifest.backup_globs` minus `manifest.exclude_globs`. Empty
    `backup_globs` falls back to DEFAULT_BACKUP_GLOBS, empty
    `exclude_globs` falls back to DEFAULT_EXCLUDE_GLOBS.
    """
    root_path = Path(root)
    includes = list(manifest.backup_globs) or list(DEFAULT_BACKUP_GLOBS)
    excludes = list(manifest.exclude_globs) or list(DEFAULT_EXCLUDE_GLOBS)

    out: list[Path] = []
    for dirpath, _dirs, files in os.walk(root_path, followlinks=False):
        for name in files:
            full = Path(dirpath) / name
            rel = full.relative_to(root_path).as_posix()
            if not _match_any(rel, includes):
                continue
            if _match_any(rel, excludes):
                continue
            out.append(full)
    return out


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_compressor(compressor: str) -> str:
    """Return effective compressor: 'zstd' if requested and available,
    else 'gzip'. Raise on completely unknown choices."""
    if compressor not in ("zstd", "gzip"):
        raise ValueError(f"unsupported compressor {compressor!r}")
    if compressor == "zstd" and shutil.which("zstd") is None:
        return "gzip"
    return compressor


def _suffix_for(compressor: str) -> str:
    return ".tar.zst" if compressor == "zstd" else ".tar.gz"


def archive_files(
    *,
    files: list[Path],
    root: Path,
    out_path: Path,
    compressor: str = "zstd",
    zstd_level: int = 6,
    zstd_threads: int = 0,
    verify: bool = True,
) -> dict:
    """Create a tar archive of `files`, with paths stored relative to `root`.

    Writes to `<out_path>.partial`, renames on success. Returns a dict with
    the tar path, sidecar manifest path, file count, sha256, and bytes.
    """
    log = get_logger("scratch_keeper.backup")
    eff = _resolve_compressor(compressor)
    out_path = out_path.with_suffix("").with_suffix(_suffix_for(eff))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    partial = out_path.with_name(out_path.name + ".partial")

    if eff == "gzip":
        with tarfile.open(partial, "w:gz") as t:
            for f in files:
                t.add(f, arcname=str(f.relative_to(root)),
                      recursive=False)
    else:
        list_file = partial.with_suffix(".files")
        list_file.write_text(
            "\n".join(str(f.relative_to(root)) for f in files) + "\n"
        )
        cmd = [
            "tar",
            "--use-compress-program",
            f"zstd -T{zstd_threads} -{zstd_level}",
            "-cf", str(partial),
            "-C", str(root),
            "-T", str(list_file),
        ]
        log.info("running %s", " ".join(cmd))
        subprocess.run(cmd, check=True)
        list_file.unlink(missing_ok=True)

    if verify:
        if eff == "gzip":
            with tarfile.open(partial, "r:gz") as t:
                count = sum(1 for m in t.getmembers() if m.isfile())
        else:
            res = subprocess.run(
                ["tar", "--use-compress-program", "zstd -d", "-tf", str(partial)],
                check=True, capture_output=True, text=True,
            )
            count = sum(1 for line in res.stdout.splitlines()
                        if not line.endswith("/"))
        if count != len(files):
            raise RuntimeError(
                f"verify mismatch: tar has {count} files, expected {len(files)}"
            )

    digest = _sha256_of(partial)
    size = partial.stat().st_size
    partial.rename(out_path)

    sidecar_path = out_path.with_suffix("").with_suffix(".manifest.json")
    if sidecar_path == out_path:
        sidecar_path = out_path.with_name(out_path.name + ".manifest.json")
    write_json(sidecar_path, {
        "created_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "tar_path": str(out_path),
        "tar_size_bytes": size,
        "sha256": digest,
        "n_files": len(files),
        "compressor": eff,
    })
    return {
        "tar_path": str(out_path),
        "manifest_path": str(sidecar_path),
        "n_files": len(files),
        "sha256": digest,
        "tar_size_bytes": size,
    }


def _rotation_warnings(backup_dir: Path, keep_last: int) -> list[str]:
    archives = sorted(
        list(backup_dir.glob("scratch_backup_*.tar.zst"))
        + list(backup_dir.glob("scratch_backup_*.tar.gz")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if len(archives) <= keep_last:
        return []
    return [f"old archive (kept_last={keep_last}): {p}" for p in archives[keep_last:]]


def run(config: dict, *, audit_path: Path,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        out_dir: str | None = None,
        verify: bool | None = None,
        dry_run: bool = False) -> dict:
    log = get_logger("scratch_keeper.backup")
    payload = read_json(audit_path)
    rows = payload["rows"]
    keepers = [r for r in rows if r["category"] == "keeper"]
    if include:
        keepers = [r for r in keepers if r["name"] in include]
    if exclude:
        keepers = [r for r in keepers if r["name"] not in exclude]

    projects_dir = Path(config["projects_dir"]).expanduser()
    manifests = load_manifests(projects_dir) if projects_dir.exists() else {}

    files_total: list[Path] = []
    per_project: list[dict] = []
    scratch_root = Path(config["scratch_root"])
    for r in keepers:
        proj_path = Path(r["path"])
        m = manifests.get(proj_path.name) or Manifest(
            name=proj_path.name, path=proj_path.name, category="keeper",
        )
        proj_files = build_file_list(proj_path, m)
        per_project.append({
            "name": proj_path.name,
            "n_files": len(proj_files),
            "src_total_bytes": r["size_bytes"],
        })
        files_total.extend(proj_files)

    log.info("backup will archive %d files from %d keeper projects",
             len(files_total), len(keepers))

    if dry_run:
        return {
            "dry_run": True,
            "n_files": len(files_total),
            "n_projects": len(keepers),
            "per_project": per_project,
        }

    backup_dir = Path(out_dir or config["backup_dir"]).expanduser()
    bcfg = config.get("backup", {})
    ts = timestamp_now()
    target = backup_dir / f"scratch_backup_{ts}.tar.zst"

    arch = archive_files(
        files=files_total,
        root=scratch_root,
        out_path=target,
        compressor=bcfg.get("compressor", "zstd"),
        zstd_level=int(bcfg.get("zstd_level", 6)),
        zstd_threads=int(bcfg.get("zstd_threads", 0)),
        verify=bool(verify if verify is not None else bcfg.get("verify", True)),
    )

    side = read_json(arch["manifest_path"])
    side["audit_ref"] = str(audit_path)
    side["projects"] = per_project
    write_json(arch["manifest_path"], side)

    keep_last = int(bcfg.get("keep_last", 3))
    warnings = _rotation_warnings(backup_dir, keep_last)
    for w in warnings:
        log.warning(w)

    return {
        "tar_path": arch["tar_path"],
        "manifest_path": arch["manifest_path"],
        "n_files": arch["n_files"],
        "sha256": arch["sha256"],
        "tar_size_bytes": arch["tar_size_bytes"],
        "rotation_warnings": warnings,
    }
