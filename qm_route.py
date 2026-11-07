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


W = 4.0   # FR-17 prior weight: best dev Recall@5 of {1.5, 2, 3, 4} (23/24), 2026-11-07


def team_boost(c, prior, w=W):
    """FR-17: soft team prior. `general` components get the neutral half-weight boost."""
    if not prior:
        return 0.0
    teams = [t for t, _ in c["teams"]]
    if teams[0] == "general":
        return w * 0.5 * max(prior.values())
    secondary = max((prior.get(t, 0.0) for t in teams[1:]), default=0.0)
    return w * (prior.get(teams[0], 0.0) + 0.5 * secondary)


def _boost(c, qset, prior, w, rare):
    """Name hits count only rare query terms; plus the soft team prior and an installed nudge."""
    name_hits = len(qset & set(qm_build.terms(c["name"].replace("-", " "))) & rare)
    return min(name_hits, 3) * 1.0 + team_boost(c, prior, w) + (0.3 if c["installed"] else 0.0)


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
    if c["kind"] == "link":                              # FR-23: the URL is the reason
        return f"- {c['id']} | link | inst n | {c['grade']} | - | {c.get('url', '')} {_clean(c['desc'], 40)}"
    deps = (c["deps"][0][:24] + (f"+{len(c['deps']) - 1}" if len(c["deps"]) > 1 else "")) if c["deps"] else "-"
    return (f"- {c['id']} | {c['kind']} | inst {'y' if c['installed'] else 'n'} | "
            f"{c['grade']}{warn} | {_clean(deps, 30)} | {_clean(c['desc'], 70)}")


def _checkpoints(task):
    brief = _clean(task, 120)
    return (["## checkpoints (run /call-a-friend; it scrubs and logs)",
             f"brief: Asked: \"{brief}\". Planned: <3 lines>. What is wrong or missing?"]
            + [f"checkpoint {name}: {when}" for name, when in CHECKPOINTS])


def _header(prior, execute_items, top, allow_risky):
    grades = "A-D" if allow_risky else "A,B"
    if top < FLOOR:
        return ["team: general (no confident match) | confidence: low",
                "clarify: what is the goal, the input and the expected output? Showing the default workflow."]
    if prior:
        team = max(prior, key=prior.get)
        return [f"team: {team} | team prior: {prior[team]:.2f} | confidence: high | grades: {grades}"]
    votes = {}
    for c in execute_items:                      # EC-6/EC-7: derive from what was found
        t = c["teams"][0][0]
        if t != "general":
            votes[t] = votes.get(t, 0) + 1
    ranked = sorted(votes.items(), key=lambda kv: -kv[1])
    team = ranked[0][0] if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]) else "unknown"
    return [f"team: {team} (derived) | confidence: low | grades: {grades}"]


def _station(idx, station, base, ctx, allow_risky):
    comps, (qset, prior, rare, sets, terms) = idx["components"], ctx
    if station == "execute":
        return {i: s + _boost(comps[i], qset, prior, W, rare) for i, s in base.items()
                if not any(set(comps[i]["terms"][:6]) & st for st in sets.values())}
    ok_teams = {STATION_TEAM[station]} | set(prior)          # station role, not task team
    return {i: 0.6 * s + base.get(i, 0.0) + _boost(comps[i], qset, prior, W / 2, rare)
            for i, s in bm25(idx, terms[station]).items() if _allowed(comps[i], allow_risky)
            and set(comps[i]["terms"][:6]) & sets[station]
            and any(t in ok_teams for t, _ in comps[i]["teams"])}


def route(idx, task, allow_risky=False, depth="normal"):
    cap = 10 if depth == "deep" else 5
    q = qm_build.terms(task)
    qset = set(q)
    rare = {t for t in qset if idx["df"].get(t, 0) < 0.01 * idx["N"]}   # 1% of components
    prior = qm_teams.task_prior(task)
    comps = idx["components"]
    base = {i: s for i, s in bm25(idx, q).items() if _allowed(comps[i], allow_risky)}
    top = max(base.values(), default=0.0)
    terms = {s: qm_build.terms(w) for s, w in STATIONS.items()}
    if top < FLOOR:
        prior = {"review-verify": 1.0}
    ctx = (qset, prior, rare, {s: set(t) for s, t in terms.items()}, terms)
    body, execute_items = [], []
    for station in ("discuss", "plan", "execute", "verify", "ship"):
        items = _pick(idx, _station(idx, station, base, ctx, allow_risky), cap)
        if station == "execute":
            execute_items = items
        if items:
            body.append(f"## {station}")
            body.extend(_line(c) for c in items)
    head = _header(qm_teams.task_prior(task), execute_items, top, allow_risky)
    return _fit(head + body, _checkpoints(task))


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


def explain(idx, ident, task=None):
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
            f"deps: {', '.join(c['deps']) or '-'}\ndesc: {_clean(c['desc'], 200)}"
            + (_prior_line(c, task) if task else ""))


def _prior_line(c, task):
    """FR-20: what the soft team prior adds for this component on this task."""
    prior = qm_teams.task_prior(task)
    shown = ", ".join(f"{t} {p:.2f}" for t, p in sorted(prior.items(), key=lambda kv: -kv[1])) or "none (pure BM25)"
    return f"\nprior: +{team_boost(c, prior):.2f} (task teams: {shown})"
