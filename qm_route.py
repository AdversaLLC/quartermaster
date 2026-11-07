"""FR-2, FR-5..FR-10, FR-12..FR-14: route a task over the prebuilt index."""
import json
import math
import os
import re

import qm_build
import qm_teams

K1, B = 1.2, 0.75
FLOOR = 2.0            # FR-13 confidence floor on the best task score
CUT = 0.5              # FR-5 keep items scoring >= 50% of the station's best
STATIONS = {           # station -> words that mark a component as serving it
    "discuss": "brainstorm clarify requirement intent discuss interview idea question",
    "plan": "plan planning spec specification architecture design roadmap breakdown",
    "verify": "verify verification test testing review qa validate check audit",
    "ship": "ship release deploy publish commit changelog merge pr package",
}
CHECKPOINTS = [
    ("after-plan", "plan written, before executing"),
    ("before-irreversible", "before deleting/overwriting data, deploying, publishing, pushing, spending or using credentials"),
    ("after-two-failures", "the same step failed twice"),
    ("before-done", "before saying the work is finished"),
]
_PATHISH = re.compile(r"(~|/)[\w./-]*/[\w./-]*|\b[A-Z_]{3,}=\S+")


def load(path):
    with open(path) as fh:
        idx = json.load(fh)
    snap = os.path.join(os.path.dirname(path), "snapshot.json")
    if os.path.exists(snap) and qm_build.file_sha256(snap) != idx.get("built_from"):
        raise RuntimeError("index older than snapshot.json: run ./rebuild.sh")
    _postings(idx)          # NFR-3: pay the table build at load, not on the first route
    return idx


def _postings(idx):
    if "_post" not in idx:
        post = {}
        for i, c in enumerate(idx["components"]):
            tf = {}
            for t in c["terms"]:
                tf[t] = tf.get(t, 0) + 1
            for t, n in tf.items():
                post.setdefault(t, []).append((i, n))
        idx["_post"] = post
        idx["_by_id"] = {c["id"]: i for i, c in enumerate(idx["components"])}
    return idx["_post"]


def bm25(idx, qterms):
    post, comps, N = _postings(idx), idx["components"], idx["N"]
    scores = {}
    for t in set(qterms):
        plist = post.get(t, [])
        if not plist:
            continue
        idf = math.log(1 + (N - len(plist) + 0.5) / (len(plist) + 0.5))
        for i, tf in plist:
            dl = len(comps[i]["terms"])
            scores[i] = scores.get(i, 0.0) + idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / idx["avgdl"]))
    return scores


def _allowed(c, allow_risky):
    return c["grade"] in ("A", "B") or (allow_risky and c["grade"] in ("C", "D"))


STATION_TEAM = {"discuss": "build", "plan": "build", "verify": "review-verify", "ship": "devops-infra"}


def _boost(c, qset, team, team_weight=1.5, rare=None):
    """Name hits count only rare query terms (rare=None: all); `general` earns no team boost."""
    hits = qset & set(qm_build.terms(c["name"].replace("-", " ")))
    name_hits = len(hits if rare is None else hits & rare)
    team_hit = team_weight if team != "general" and any(t == team for t, _ in c["teams"]) else 0.0
    return min(name_hits, 3) * 1.0 + team_hit + (0.3 if c["installed"] else 0.0)


def _pick(idx, scored, cap):
    comps, seen, out = idx["components"], set(), []
    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], not comps[kv[0]]["installed"], comps[kv[0]]["id"]))
    best = ranked[0][1] if ranked else 0
    for i, s in ranked:
        c = comps[i]
        if c["name"] in seen:          # EC-2: one copy per name, best first
            continue
        if out and s < best * CUT:
            break
        seen.add(c["name"])
        out.append(c)
        if len(out) >= cap:
            break
    return out


def _clean(text, n):
    return _PATHISH.sub("…", (text or "").replace("|", "/").replace("\n", " "))[:n]


def _line(c):
    warn = " WARNING risky" if c["grade"] in ("C", "D") else ""
    deps = (c["deps"][0][:24] + (f"+{len(c['deps']) - 1}" if len(c["deps"]) > 1 else "")) if c["deps"] else "-"
    return (f"- {c['id']} | {c['kind']} | inst {'y' if c['installed'] else 'n'} | "
            f"{c['grade']}{warn} | {_clean(deps, 30)} | {_clean(c['desc'], 70)}")


def _checkpoints(task):
    brief = _clean(task, 120)
    return (["## checkpoints (run /call-a-friend; it scrubs and logs)",
             f"brief: Asked: \"{brief}\". Planned: <3 lines>. What is wrong or missing?"]
            + [f"checkpoint {name}: {when}" for name, when in CHECKPOINTS])


def route(idx, task, allow_risky=False, depth="normal"):
    cap = 10 if depth == "deep" else 5
    q = qm_build.terms(task)
    qset = set(q)
    rare = {t for t in qset if idx["df"].get(t, 0) < 0.01 * idx["N"]}   # 1% of components
    team, rule = qm_teams.teams_for(task)[0]
    comps = idx["components"]
    base = {i: s for i, s in bm25(idx, q).items() if _allowed(comps[i], allow_risky)}
    top = max(base.values(), default=0.0)
    lines = []
    if top < FLOOR:
        lines.append(f"team: general (no confident match) | confidence: low")
        lines.append("clarify: what is the goal, the input and the expected output? Showing the default workflow.")
        team = "review-verify"
    else:
        lines.append(f"team: {team} ({rule}) | confidence: high | grades: {'A-D' if allow_risky else 'A,B'}")
    station_terms = {s: qm_build.terms(w) for s, w in STATIONS.items()}
    station_sets = {s: set(t) for s, t in station_terms.items()}
    for station in ("discuss", "plan", "execute", "verify", "ship"):
        if station == "execute":
            scored = {i: s + _boost(comps[i], qset, team, 3.0, rare) for i, s in base.items()
                      if not any(set(comps[i]["terms"][:6]) & st for st in station_sets.values())}
        else:
            sb = bm25(idx, station_terms[station])
            ok_teams = {team, STATION_TEAM[station]}
            scored = {i: 0.6 * s + base.get(i, 0.0) + _boost(comps[i], qset, team, rare=rare)
                      for i, s in sb.items() if _allowed(comps[i], allow_risky)
                      and set(comps[i]["terms"][:6]) & station_sets[station]
                      and any(t in ok_teams for t, _ in comps[i]["teams"])}
        items = _pick(idx, scored, cap)
        if items:
            lines.append(f"## {station}")
            lines.extend(_line(c) for c in items)
    return _fit(lines, _checkpoints(task))


def _fit(lines, checkpoints, limit=4000):
    """NFR-2: checkpoints are never trimmed; kit lines are dropped from the end first."""
    tail = "\n".join(checkpoints)
    budget = limit - len(tail) - 40
    kept, used, dropped = [], 0, 0
    for line in lines:
        if used + len(line) + 1 > budget:
            dropped += line.startswith("- ")
            continue
        kept.append(line)
        used += len(line) + 1
    if dropped:
        kept.append(f"[{dropped} items trimmed to fit 4000 chars; use depth or explain]")
    return "\n".join(kept + [tail])


def explain(idx, ident):
    _postings(idx)
    comps = idx["components"]
    note = ""
    if ident not in idx["_by_id"]:
        cands = [c for c in comps if c["name"] == ident and c["grade"] != "unaudited"]
        if not cands:
            return f"not found: {ident} (use name@plugin)"
        order = {"A": 0, "B": 1, "C": 2, "D": 3}
        pick = sorted(cands, key=lambda c: (not c["installed"], order[c["grade"]], c["id"]))[0]
        note = f"picked {pick['id']} of {len(cands)} copies (installed, then best grade)\n"
        ident = pick["id"]
    c = comps[idx["_by_id"][ident]]
    reasons = idx["audits"].get(c["plugin"], ["unaudited", []])[1]
    teams = "; ".join(f"{t} ({r})" for t, r in c["teams"])
    return (f"{note}id: {c['id']}\nkind: {c['kind']}\nteams: {teams}\ngrade: {c['grade']}\n"
            f"reasons: {', '.join(reasons) or 'none declared'}\ninstalled: {c['installed']}\n"
            f"deps: {', '.join(c['deps']) or '-'}\ndesc: {_clean(c['desc'], 200)}")
