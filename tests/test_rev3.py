"""Acceptance tests for ROUTER-SPEC.md rev 3 (AC-11 .. AC-17). Synthetic fixtures only."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import qm_stats as qs  # noqa: E402


# ---------- AC-11: statistics and split ----------

def test_ac11_wilson_known_value():
    lo, hi = qs.wilson(21, 36)
    assert round(lo, 2) == 0.42 and round(hi, 2) == 0.73


def test_ac11_wilson_edges():
    assert qs.wilson(0, 0) == (0.0, 1.0)
    lo, hi = qs.wilson(12, 12)
    assert hi == 1.0 and lo > 0.7


def test_ac11_mcnemar_exact():
    # 0 tasks only A got right, 6 only B got right -> two-sided exact p = 2 * 0.5**6
    a = [True] * 10 + [False] * 6
    b = [True] * 16
    assert qs.mcnemar(a, b) == pytest.approx(0.03125)
    assert qs.mcnemar(a, a) == 1.0


def test_ac11_split_is_seeded_and_stratified():
    items = [{"task": f"t{i}", "team": f"team{i % 3}"} for i in range(9)]
    s1 = qs.split(items, holdout_per_team=1, seed=7)
    s2 = qs.split(items, holdout_per_team=1, seed=7)
    assert [x["split"] for x in s1] == [x["split"] for x in s2]
    hold = [x for x in s1 if x["split"] == "holdout"]
    assert sorted(x["team"] for x in hold) == ["team0", "team1", "team2"]


# ---------- AC-12 .. AC-15: soft team prior ----------
import qm_build as qb  # noqa: E402
import qm_route as qr  # noqa: E402
import qm_teams as qt  # noqa: E402


def comp(team, secondary=()):
    return {"teams": [[team, "r"]] + [[t, "r"] for t in secondary]}


def test_ac12_off_team_strong_match_still_wins():
    prior = {"debug": 1.0}
    on, off = comp("debug"), comp("research")
    assert qr.team_norm(on, prior) == pytest.approx(1 / 1.5)
    # normalised BM25 1.0 off-team beats 0.6 on-team at the largest swept W with full confidence
    assert qr.combine(1.0, 0, 1.0, qr.team_norm(off, prior), 0.3) > qr.combine(0.6, 0, 1.0, qr.team_norm(on, prior), 0.3)


def test_ac12_secondary_counts_half():
    prior = {"debug": 0.6, "research": 0.4}
    assert qr.team_norm(comp("build", ["research"]), prior) == pytest.approx(0.5 * 0.4 / 1.5)


def test_ac14_general_gets_neutral_boost():
    prior = {"debug": 0.7, "research": 0.3}
    assert qr.team_norm(comp("general"), prior) == pytest.approx(0.5 * 0.7 / 1.5)


def test_fr17_confidence_ramp():
    assert qt.confidence({}) == 0.0
    assert qt.confidence({"debug": 1.0}) == 1.0                 # one team only: clearest case
    assert qt.confidence({"debug": 0.55, "build": 0.45}) == pytest.approx(0.5)
    assert qt.confidence({"debug": 0.7, "build": 0.3}) == 1.0


def test_fr17_combine_and_tiebreak():
    assert qr.combine(0.5, 1.0, 0.0, 1.0, 0.3) == pytest.approx(0.5 + 0.15)
    idx = {"components": [{"id": "b@p", "installed": False, "name": "b"},
                          {"id": "a@p", "installed": True, "name": "a"},
                          {"id": "c@p", "installed": False, "name": "c"}]}
    picked = qr._pick(idx, {0: 1.0, 1: 1.0, 2: 1.0}, 5)
    assert [c["id"] for c in picked] == ["a@p", "b@p", "c@p"]   # score, then installed, then id


def test_ac13_low_confidence_is_pure_bm25():
    assert qt.task_prior("asdf qwerty") == {}
    assert qt.task_prior("not a github actions job") == {}    # EC-7: negatives only


def test_ac13_phrases_beat_generic_verbs():
    p = qt.task_prior("this test passes locally but fails randomly in CI")   # dev task
    assert max(p, key=p.get) == "debug"
    p = qt.task_prior("set up github actions to run tests on every push")
    assert max(p, key=p.get) == "devops-infra"


def test_ac13_tie_is_derived():
    recs = [{"name": "p", "summary": "", "fetched": True, "repo": "", "subpath": "",
             "skills": [{"name": "alpha-tool", "desc": "alpha beta gamma"}]
             + [{"name": f"filler-{i}", "desc": f"unrelated word{i} text"} for i in range(30)],
             "agents": [], "commands": [], "mcp": [], "hooks": [], "deps": {}}]
    idx = qb.build(recs, {"p": ("A", [])}, set())       # filler keeps BM25 idf above the floor
    out = qr.route(idx, "docker react alpha beta gamma")     # one devops hit, one frontend hit
    assert "(derived)" in out.splitlines()[0]


def test_ac15_explain_shows_prior():
    recs = [{"name": "p", "summary": "", "fetched": True, "repo": "", "subpath": "",
             "skills": [{"name": "debug-tool", "desc": "debug a crash stack trace"}],
             "agents": [], "commands": [], "mcp": [], "hooks": [], "deps": {}}]
    idx = qb.build(recs, {"p": ("A", [])}, set())
    out = qr.explain(idx, "debug-tool@p", task="my app crashes with a stack trace")
    assert "prior:" in out and "debug" in out


# ---------- AC-18: tool links ----------
import json  # noqa: E402


def test_ac18_tool_link_routes_with_url(tmp_path):
    (tmp_path / "tool_links.json").write_text(json.dumps([{
        "name": "textshift", "url": "https://example.org/textshift",
        "desc": "Encode, decode and transform text: base64, hex, unicode tricks, ciphers"}]))
    recs = qb.link_records(str(tmp_path))
    filler = {"name": "f", "summary": "", "fetched": True, "repo": "", "subpath": "",
              "skills": [{"name": f"filler-{i}", "desc": f"unrelated word{i}"} for i in range(30)],
              "agents": [], "commands": [], "mcp": [], "hooks": [], "deps": {}}
    idx = qb.build(recs + [filler], {"links": ("B", ["external link; nothing fetched or run"]), "f": ("A", [])}, set())
    out = qr.route(idx, "encode this text as base64 and hex")
    line = next(l for l in out.splitlines() if "textshift@links" in l)
    assert "| link |" in line and "https://example.org/textshift" in line


def test_ac18_no_file_no_links(tmp_path):
    assert qb.link_records(str(tmp_path)) == []
