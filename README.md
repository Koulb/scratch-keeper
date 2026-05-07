# scratch-keeper

CSCS scratch keeper for `/capstor/scratch/cscs/apoliukh/`.
A `cluster-manage` CLI that audits, backs up, deletes, and refreshes mtime
on cluster scratch directories so essential work survives the 30-day reaper.

## Install (Eiger / Daint login node)

```bash
git clone https://github.com/Koulb/scratch-keeper.git ~/scratch-keeper
ln -s ~/scratch-keeper/bin/cluster-manage ~/.local/bin/cluster-manage
cluster-manage help concepts
```

## Workflow

```bash
cluster-manage audit
cluster-manage backup --audit logs/audit_<ts>.json
cluster-manage propose-delete --audit logs/audit_<ts>.json
$EDITOR logs/delete_proposal_<ts>.json
cluster-manage execute-delete logs/delete_proposal_<ts>.json --confirm
cluster-manage touch
```

See `docs/superpowers/specs/2026-05-07-scratch-keeper-design.md` for the design.
