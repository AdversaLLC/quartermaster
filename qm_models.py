"""FR-24 (ROUTER-SPEC rev 3.2): task-dependent model hint per workflow step. Text only; calls nothing."""
import json
import os
import re

import qm_teams

STATIONS = ("discuss", "plan", "execute", "verify", "ship")
DEFAULTS = {"standard": "claude-sonnet-5-5", "deep": "claude-opus-5-5"}
REASON_ORDER = ("security", "irreversible", "unclear", "matches-execute")
EXECUTE_WORDS = frozenset("delete drop overwrite migrate destroy revoke rotate rm force-push".split())
SHIP_WORDS = frozenset("deploy publish release push production prod send charge refund transfer".split())
_ID = re.compile(r"[A-Za-z0-9._:/-]{1,64}")
_WORD = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def model_ids(data_dir):
    """Tier -> model id; bad ids or unknown keys fall back to DEFAULTS (EC-12)."""
    ids = dict(DEFAULTS)
    path = os.path.join(data_dir, "qm_models.json")
    if os.path.exists(path):
        with open(path) as fh:
            user = json.load(fh)
        for tier in DEFAULTS:
            value = user.get(tier) if isinstance(user, dict) else None
            if isinstance(value, str) and _ID.fullmatch(value):
                ids[tier] = value
    return ids


def _irreversible(task):
    """Stations raised by whole-word risky verbs, skipping negated words and dry runs (EC-15)."""
    low = (task or "").lower()
    if "dry run" in low or "dry-run" in low:
        return set()
    words = _WORD.findall(low)
    negated = {i for i, w in enumerate(words) if w in qm_teams.NEGATORS or w.endswith("n't")
               for i in range(i + 1, i + 4)}
    hit = set()
    for i, w in enumerate(words):
        if i in negated:
            continue
        if w in EXECUTE_WORDS:
            hit.add("execute")
        if w in SHIP_WORDS:
            hit.add("ship")
    return hit


def station_tiers(task, prior, clarify):
    """{station: (tier, reasons)}; everything starts standard and rules only raise (FR-24)."""
    reasons = {s: [] for s in STATIONS}
    top = max(prior, key=prior.get) if prior else None
    if top == "security-reverse-eng" and qm_teams.confidence(prior) >= 0.5:
        reasons["execute"].append("security")
        reasons["verify"].append("security")
    for s in _irreversible(task):
        reasons[s].append("irreversible")
    if clarify:
        reasons["plan"].append("unclear")
    if reasons["execute"] and not reasons["verify"]:      # rule 4: verify never below execute
        reasons["verify"].append("matches-execute")
    out = {}
    for s in STATIONS:
        rs = sorted(dict.fromkeys(reasons[s]), key=REASON_ORDER.index)
        out[s] = ("deep" if rs else "standard", rs)
    return out


def annotate(lines, tiers, ids):
    """Insert `model: <id> — <reasons>` after each station header, plus the closing note."""
    out = []
    for line in lines:
        out.append(line)
        name = line[3:] if line.startswith("## ") else None
        if name in tiers:
            tier, rs = tiers[name]
            out.append(f"model: {ids[tier]} — {', '.join(rs) or 'default'}")
    out.append("models are suggestions; override freely")
    return out
