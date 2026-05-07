import sys
import pytest
from scratch_keeper import cli


def _invoke(*args):
    return cli.main(list(args))


def test_help_top_level_lists_subcommands(capsys):
    with pytest.raises(SystemExit) as exc:
        _invoke("--help")
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for sub in ("audit", "backup", "propose-delete", "execute-delete",
                "touch", "status", "run-all", "help"):
        assert sub in out


def test_help_subcommand_concepts(capsys):
    rc = _invoke("help", "concepts")
    assert rc == 0
    out = capsys.readouterr().out
    assert "keeper" in out.lower()


def test_help_subcommand_workflow(capsys):
    rc = _invoke("help", "workflow")
    assert rc == 0
    out = capsys.readouterr().out
    assert "audit" in out.lower()


def test_unknown_subcommand_returns_error():
    with pytest.raises(SystemExit) as exc:
        _invoke("totally-not-a-command")
    assert exc.value.code != 0


def test_subcommand_help_returns_zero(capsys):
    for sub in ("audit", "backup", "propose-delete",
                "execute-delete", "touch", "status", "run-all"):
        with pytest.raises(SystemExit) as exc:
            _invoke(sub, "--help")
        assert exc.value.code == 0
