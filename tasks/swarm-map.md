# Swarm map — Quartermaster ship (2026-11-07)

Substrate: Claude Code, real subagents. Prime = main session.

| Hub | Owner | Owns | Status |
|---|---|---|---|
| A packaging | subagent | LICENSE, README.md, NOTICE, rebuild.sh, .gitignore | done (AC-7 pass) |
| B routing eval | subagent | qm_eval.py, tests/routing_set.json | done: Recall@5 bm25 0.86 vs rules 0.58, team acc 0.58, n=36 (index 14:47:07) |
| C real index + MCP | Prime | qm_*.py, qm_index.json, MCP registration | done: 22/22 tests, registered user scope |

Interfaces: qm_eval.evaluate(idx) -> (bm25_recall, rules_recall), consumed by tests/test_router.py::test_ac10.
Rework budget: 2 per Hub (Prime decrements).
Checkpoint: this file after every merge.

Prime merges so far:
- Hub A found the cold-route timing failure (postings built inside the timed call); fixed in qm_route.load.
- Hub C fixes: checkpoints never trimmed (_fit), stem e/-s, stopwords, team-gated non-execute stations, atomic index write.
- Hub B fixes applied: no team boost for `general`; name boost counts only rare (<1% df) terms. Recall unchanged at 0.86; full suite 41/41.
- Open: team keyword rules misfire (team accuracy 0.58: "find"->research, "tests"->review-verify, no rule for pull request / screen reader / classifier). Next loop.
- Open: no git repo yet; 286 plugins unaudited (marketplace plugins not in repos/).
