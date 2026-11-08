"""Acceptance tests for ROUTER-SPEC.md rev 3.2 (AC-19 .. AC-24): model hints per step."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import qm_build as qb  # noqa: E402
import qm_mcp as qm  # noqa: E402
import qm_models as mm  # noqa: E402
import qm_route as qr  # noqa: E402

STD, DEEP = "claude-sonnet-5-5", "claude-opus-5-5"


def tiers(task, prior=None, clarify=False):
    return mm.station_tiers(task, prior or {}, clarify)


def test_ac20_trivial_task_all_standard():
    t = tiers("rename a variable in utils.py")
    assert all(tier == "standard" for tier, _ in t.values())


def test_ac21_security_prior_raises_execute_and_verify():
    t = tiers("look at this", prior={"security-reverse-eng": 1.0})
    assert t["execute"] == ("deep", ["security"])
    assert t["verify"] == ("deep", ["security"])           # already deep: no matches-execute
    assert t["plan"][0] == "standard"


def test_ac21_weak_security_prior_does_not_raise():
    t = tiers("look at this", prior={"security-reverse-eng": 0.55, "debug": 0.45})   # confidence 0.5
    assert t["execute"][0] == "deep"
    t = tiers("look at this", prior={"security-reverse-eng": 0.52, "debug": 0.48})   # confidence 0.2
    assert t["execute"][0] == "standard"


def test_ac22_irreversible_words_per_station():
    t = tiers("delete the old releases and deploy v2")
    assert t["execute"] == ("deep", ["irreversible"])
    assert t["ship"] == ("deep", ["irreversible"])
    assert t["verify"] == ("deep", ["matches-execute"])


def test_ac22_negation_dry_run_and_whole_words():
    assert tiers("don't deploy yet")["ship"][0] == "standard"
    assert tiers("do a dry run of the deploy")["ship"][0] == "standard"
    assert tiers("add a push notification")["ship"][0] == "deep"
    assert tiers("add a pushpin icon")["ship"][0] == "standard"


def test_unclear_raises_plan_only():
    t = tiers("asdf", clarify=True)
    assert t["plan"] == ("deep", ["unclear"]) and t["execute"][0] == "standard"


def test_ac23_bad_model_id_falls_back(tmp_path):
    (tmp_path / "qm_models.json").write_text(json.dumps({"standard": "x\n)", "deep": "my-opus:1"}))
    ids = mm.model_ids(str(tmp_path))
    assert ids == {"standard": STD, "deep": "my-opus:1"}
    assert mm.model_ids(str(tmp_path / "missing")) == {"standard": STD, "deep": DEEP}


def _idx():
    recs = [{"name": "p", "summary": "", "fetched": True, "repo": "", "subpath": "",
             "skills": [{"name": "release-tool", "desc": "deploy and release the app to production"},
                        {"name": "plan-tool", "desc": "write a plan and spec before coding"},
                        {"name": "verify-tool", "desc": "run tests and verify the change"}]
             + [{"name": f"filler-{i}", "desc": f"unrelated word{i}"} for i in range(30)],
             "agents": [], "commands": [], "mcp": [], "hooks": [], "deps": {}}]
    return qb.build(recs, {"p": ("A", [])}, set())


def test_ac19_off_is_byte_identical():
    idx = _idx()
    base = qr.route(idx, "deploy the app to production")
    assert qr.route(idx, "deploy the app to production", models=False) == base
    assert qr.route(idx, "deploy the app to production", models="true") == base     # non-boolean = off


def test_ac24_hint_lines_and_limits():
    out = qr.route(_idx(), "deploy the app to production", models=True)
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## ") and not line.startswith("## checkpoints"):
            assert lines[i + 1].startswith("model: ")
    assert "models are suggestions; override freely" in out
    assert "$" not in out and len(out) <= 4000
    res = qm.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert len(json.dumps(res["result"])) <= 1500
