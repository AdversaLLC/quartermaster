# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Quartermaster (README.md has install, tools and output shape). Runtime is Python 3.11+ standard
library only; pytest is the only dev dependency. The checkout folder may still be named
`plugin-snapshot/`; don't assume it matches the repo name.

## Commands

```
python3 -m pytest -q tests/                  # full suite
python3 -m pytest -q tests/ -k ac6          # tests are named after spec IDs (AC-n / FR-n / EC-n)
python3 qm_build.py                          # rebuild qm_index.json from the existing snapshot.json
python3 qm_eval.py                           # Recall@5 BM25 vs rules, team accuracy, per-task table
```

Run `fetch.py` / `rebuild.sh` only when `snapshot.json` itself must change: it fetches thousands of
plugin repos over the network. Routing and audit changes need only `qm_build.py`.

## Architecture

Two stages, joined by files in the data dir (`QM_DATA`):

1. Snapshot: `fetch.py` fills `repos/`; `build_index.py` reads `repos/` plus Claude Code's plugin
   caches and writes `snapshot.json`. `build_index.py` without a prior fetch indexes whatever is in `repos/`.
2. Router: `qm_build.py` joins `snapshot.json`, the static audit (`qm_audit.py`), team labels
   (`qm_teams.py`) and local install state into `qm_index.json`; `qm_route.py` serves `route`/`explain`
   from it via `qm_mcp.py`.

There are two live MCP servers: `qm_mcp.py` (route/explain) and `snapshot_mcp.py` (search/list/get
over the snapshot). Router tools belong in `qm_mcp.py`; tool descriptions count against the
`tools/list` size cap.

The Arch package installs code to read-only `/usr/lib/quartermaster`; its launchers default
`QM_DATA` to `~/.local/share/quartermaster`, so data paths must always come from `ROOT`.

## Changing behaviour (spec-first)

Routing or audit changes start in the spec: add or amend an FR/AC in `ROUTER-SPEC.md` (or `SPEC.md`
for the snapshot), name the test after it, then change the code. No rule or signal without an AC.

- Team rule (`qm_teams.py`): the matched rule is shown by `explain`. Check it on a held-out slice
  of `tests/routing_set.json` that you did not look at while writing the rule.
- Audit signal (`qm_audit.py`): static file reads only — never import, exec or run plugin
  content. Each signal needs a grade mapping and a synthetic fixture in tests (the suite
  monkeypatches subprocess to fail on any process launch).
- `terms()`/`stem()` in `qm_build.py` are the one tokenizer for index and query; any change
  needs an index rebuild before evaluating.

## Invariants and gotchas

- Index staleness is the SHA-256 of `snapshot.json`, not mtime: `tests/test_spec.py` reruns
  `build_index.py`, which rewrites the file with identical content.
- Response sizes are capped by tests; `_fit` drops kit lines first and never trims checkpoints.
- IDs are `name@plugin` everywhere. A bare name resolves to the installed copy first, then the
  lowest-risk grade; `unaudited` never resolves and is never recommended.
- Grade A means "nothing risky declared", never "safe". Keep that wording in output and docs.
- `@real` tests skip without `qm_index.json`; snapshot tests skip unless `fetch.log` has `ALLDONE`.
  Tests use synthetic fixtures only; never copy real plugin content (licensing, see NOTICE).
- `repos/`, `snapshot.json`, `qm_index.json`, `lists/` are gitignored build outputs; don't `git add -f` them.
- `tests/routing_set.json` labels are LLM-written: Recall is a sanity check. Don't tune on the
  full set; keep a fixed held-out split.
- Release: tag `vX.Y.Z`, push, bump `pkgver` in `packaging/arch/PKGBUILD`, then `updpkgsums`
  (never `SKIP`). Packaging is Arch only.
