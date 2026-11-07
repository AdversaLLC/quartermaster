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
