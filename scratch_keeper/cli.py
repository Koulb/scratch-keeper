"""cluster-manage entrypoint: argparse dispatcher for the scratch_keeper verbs."""
from __future__ import annotations

import argparse
import logging
import sys
from importlib import resources
from pathlib import Path

from scratch_keeper import (
    audit as audit_mod,
    backup as backup_mod,
    propose_delete as propose_mod,
    execute_delete as execute_mod,
    status as status_mod,
    touch as touch_mod,
)
from scratch_keeper.common import get_logger, load_config


DEFAULT_CONFIG_PATHS = (
    Path("~/scratch-keeper/config.json").expanduser(),
    Path(__file__).resolve().parent.parent / "config.json",
)


def _read_help_file(name: str) -> str:
    return (Path(__file__).resolve().parent / "help" / f"{name}.txt").read_text()


def _resolve_config(path: str | None) -> dict:
    candidates = [Path(path).expanduser()] if path else list(DEFAULT_CONFIG_PATHS)
    for c in candidates:
        if c.exists():
            return load_config(c)
    raise FileNotFoundError(
        f"config.json not found; tried: {[str(p) for p in candidates]}"
    )


def _set_log_level(level: str) -> None:
    lg = get_logger("scratch_keeper")
    lg.setLevel(getattr(logging, level.upper(), logging.INFO))


def _add_global(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default=None, help="path to config.json")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARN", "ERROR"])


def _cmd_audit(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    audit_mod.run(cfg, quick=args.quick)
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    backup_mod.run(
        cfg,
        audit_path=Path(args.audit),
        include=args.include or None,
        exclude=args.exclude or None,
        out_dir=args.out,
        verify=(False if args.no_verify else None),
        dry_run=args.dry_run,
    )
    return 0


def _cmd_propose_delete(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    propose_mod.run(
        cfg,
        audit_path=Path(args.audit),
        include_unknown=args.include_unknown,
        auto_mark_reproducible=args.auto_mark_reproducible,
        min_size_gb=args.min_size_gb,
        out_path=Path(args.out) if args.out else None,
    )
    return 0


def _cmd_execute_delete(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    out = execute_mod.run(
        cfg,
        proposal_path=Path(args.proposal),
        confirm=args.confirm,
        max_rows=args.max_rows,
        max_bytes_gb=args.max_bytes_gb,
        allow_dotfiles=args.allow_dotfiles,
    )
    return 0 if out.get("status") == "ok" else 2


def _cmd_touch(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    touch_mod.run(
        cfg,
        only_project=args.project,
        max_age_days=args.max_age_days,
        dry_run=args.dry_run,
    )
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    status_mod.run(cfg)
    return 0


def _cmd_run_all(args: argparse.Namespace) -> int:
    cfg = _resolve_config(args.config)
    a = audit_mod.run(cfg)
    backup_mod.run(cfg, audit_path=Path(a["audit_path"]),
                   dry_run=args.dry_run)
    propose_mod.run(cfg, audit_path=Path(a["audit_path"]))
    touch_mod.run(cfg, dry_run=args.dry_run)
    return 0


def _cmd_help(args: argparse.Namespace) -> int:
    if args.topic in ("concepts", "workflow"):
        print(_read_help_file(args.topic))
        return 0
    if args.topic in ("audit", "backup", "propose-delete",
                      "execute-delete", "touch", "status", "run-all"):
        return main([args.topic, "--help"])
    print(_read_help_file("workflow"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cluster-manage",
        description="cluster-manage — CSCS scratch keeper CLI. "
                    "Audit, backup, propose-delete, execute-delete, touch, status, run-all.",
    )
    _add_global(p)
    sp = p.add_subparsers(dest="cmd")

    a = sp.add_parser("audit", help="Scan scratch, classify dirs, write audit_<ts>.json")
    _add_global(a); a.add_argument("--quick", action="store_true")
    a.set_defaults(func=_cmd_audit)

    b = sp.add_parser("backup", help="Build a tar of keepers in store")
    _add_global(b); b.add_argument("--audit", required=True)
    b.add_argument("--include", action="append")
    b.add_argument("--exclude", action="append")
    b.add_argument("--out", default=None)
    b.add_argument("--no-verify", action="store_true")
    b.add_argument("--dry-run", action="store_true")
    b.set_defaults(func=_cmd_backup)

    pd = sp.add_parser("propose-delete", help="Write delete_proposal_<ts>.json (no rm)")
    _add_global(pd); pd.add_argument("--audit", required=True)
    pd.add_argument("--include-unknown", action="store_true")
    pd.add_argument("--auto-mark-reproducible", action="store_true")
    pd.add_argument("--min-size-gb", type=float, default=0.0)
    pd.add_argument("--out", default=None)
    pd.set_defaults(func=_cmd_propose_delete)

    ed = sp.add_parser("execute-delete", help="Apply a proposal (--confirm required)")
    _add_global(ed); ed.add_argument("proposal")
    ed.add_argument("--confirm", action="store_true")
    ed.add_argument("--max-rows", type=int, default=None)
    ed.add_argument("--max-bytes-gb", type=int, default=None)
    ed.add_argument("--allow-dotfiles", action="store_true")
    ed.set_defaults(func=_cmd_execute_delete)

    t = sp.add_parser("touch", help="Refresh mtime per project")
    _add_global(t); t.add_argument("--project", default=None)
    t.add_argument("--max-age-days", type=int, default=None)
    t.add_argument("--dry-run", action="store_true")
    t.set_defaults(func=_cmd_touch)

    s = sp.add_parser("status", help="Print last audit + archives + last delete")
    _add_global(s); s.set_defaults(func=_cmd_status)

    ra = sp.add_parser("run-all", help="audit → backup → propose → touch (no delete)")
    _add_global(ra); ra.add_argument("--dry-run", action="store_true")
    ra.set_defaults(func=_cmd_run_all)

    h = sp.add_parser("help", help="Show help. Try: help concepts, help workflow")
    h.add_argument("topic", nargs="?", default=None)
    h.set_defaults(func=_cmd_help)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    _set_log_level(getattr(args, "log_level", "INFO"))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
