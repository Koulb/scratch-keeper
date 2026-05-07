import datetime as dt
import json
from pathlib import Path
from scratch_keeper.propose_delete import (
    score_row, build_candidates, run as propose_run,
)


def _row(name, *, cat="delete-candidate", repro=True, size=1_000_000_000,
         days_old=10, n_files=100):
    newest = (dt.datetime.now() - dt.timedelta(days=days_old)).isoformat()
    return {
        "name": name, "path": f"/scratch/{name}",
        "category": cat, "reproducible": repro,
        "size_bytes": size, "n_files": n_files, "n_dirs": 0,
        "oldest_mtime": newest, "newest_mtime": newest,
        "days_until_reap": 30 - days_old, "notes": "",
    }


def test_score_row_increases_with_age_and_size_and_reproducibility():
    weights = {"age_days": 0.4, "reproducible": 0.3,
               "size_gb": 0.2, "name_match": 0.1}
    young = _row("a", days_old=1, repro=False, size=10)
    old_big_repro = _row("qe-agent", days_old=120, repro=True,
                         size=4 * 1024**4)
    s_young = score_row(young, weights, name_match_set=set())
    s_oldbig = score_row(old_big_repro, weights,
                         name_match_set={"qe-agent"})
    assert s_oldbig > s_young


def test_build_candidates_includes_default_delete_and_unknown_bulk():
    rows = [
        _row("qe-agent", cat="delete-candidate"),
        _row("diamond_new_data", cat="unknown", days_old=80,
             n_files=50_000, size=800 * 1024**3),
        _row("raman", cat="keeper", repro=False),
    ]
    cands = build_candidates(rows, include_unknown=False,
                             min_size_gb=0,
                             score_weights={"age_days": 1, "reproducible": 1,
                                            "size_gb": 1, "name_match": 1})
    names = [c["path"].split("/")[-1] for c in cands]
    assert "qe-agent" in names
    assert "diamond_new_data" in names  # bulk-unknown auto-included
    assert "raman" not in names


def test_build_candidates_skips_recent_unknown_when_flag_off():
    rows = [_row("recent", cat="unknown", days_old=2, n_files=10)]
    cands = build_candidates(rows, include_unknown=False,
                             min_size_gb=0,
                             score_weights={"age_days": 1, "reproducible": 1,
                                            "size_gb": 1, "name_match": 1})
    assert cands == []


def test_propose_run_writes_proposal(tmp_path):
    audit = {
        "rows": [
            _row("qe-agent", cat="delete-candidate"),
            _row("recent", cat="unknown", days_old=2, n_files=10),
        ],
    }
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit))
    config = {
        "log_dir": str(tmp_path / "logs"),
        "delete": {
            "score_weights": {"age_days": 0.4, "reproducible": 0.3,
                              "size_gb": 0.2, "name_match": 0.1}
        },
    }
    out = propose_run(config, audit_path=audit_path)
    proposal = json.loads(Path(out["proposal_path"]).read_text())
    assert proposal["audit_ref"] == str(audit_path)
    assert proposal["summary"]["total_candidates"] == len(proposal["candidates"])
    deletes = [c for c in proposal["candidates"] if c["action"] == "delete"]
    assert any(c["path"].endswith("qe-agent") for c in deletes)
