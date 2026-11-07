#!/usr/bin/env python3
"""Build qm_index.json from snapshot.json + fetched repos (FR-1..FR-3, FR-14).

Usage: python3 qm_build.py   (after fetch.py and build_index.py)
"""
import hashlib
import json
import os
import sys
import time

import qm_audit
import qm_prompts
import qm_teams

ROOT = os.environ.get("QM_DATA") or os.path.dirname(os.path.abspath(__file__))   # data dir; code may live in /usr/lib
KINDS = {"skills": "skill", "agents": "agent", "commands": "command", "mcp": "mcp", "prompts": "prompt", "links": "link"}
HOME = os.path.expanduser("~")


STOP = frozenset("a an the and or of to in on for with by from at as is are be it its this that "
                 "these those my me i we you your our use using when what how do does can will "
                 "should into about via any all".split())


def stem(tok):
    if len(tok) == 4 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]                       # keys -> key, apis -> api
    for suf in ("ing", "ed", "es", "s", "e"):
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def terms(text):
    out = []
    for t in qm_teams.tokens(text):
        if t in STOP:
            continue
        out.append(stem(t))
        if "-" in t:
            out.extend(stem(p) for p in t.split("-") if p and p not in STOP)
    return out


def _deps(r):
    d = r.get("deps") or {}
    flat = [f"{k}:{v}" for k, vs in d.items() for v in (vs or [])] if isinstance(d, dict) else []
    return flat[:4] + (r.get("runtime") or [])[:2]


def build(recs, audits, installed, installed_skills=frozenset()):
    comps = []
    for r in recs:
        grade, _ = audits.get(r["name"], ("unaudited", []))
        for key, kind in KINDS.items():
            for c in r.get(key) or []:
                name = c.get("name") or ""
                desc = (c.get("desc") or c.get("url") or c.get("command") or "")[:200]
                text = f"{name.replace('-', ' ').replace('_', ' ')} {desc}"
                comps.append({
                    "id": f"{name}@{r['name']}", "kind": kind, "name": name, "plugin": r["name"],
                    "desc": desc, "teams": qm_teams.teams_for(text), "grade": grade,
                    "installed": r["name"] in installed or (kind == "skill" and name in installed_skills),
                    "deps": _deps(r),
                    "terms": terms(f"{text} {text} {r.get('summary') or ''}"),
                })
                if kind == "link":
                    comps[-1]["url"] = c.get("url", "")
    df = {}
    for c in comps:
        for t in set(c["terms"]):
            df[t] = df.get(t, 0) + 1
    avgdl = sum(len(c["terms"]) for c in comps) / max(len(comps), 1)
    return {"components": comps, "audits": {k: list(v) for k, v in audits.items()},
            "df": df, "avgdl": avgdl, "N": len(comps)}


def link_records(data_dir):
    """FR-23: user-local external tool links; [] when tool_links.json is absent."""
    path = os.path.join(data_dir, "tool_links.json")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        links = [x for x in json.load(fh) if isinstance(x, dict) and x.get("name") and x.get("url")]
    return [{"name": "links", "summary": "external tool links", "fetched": True, "repo": "",
             "subpath": "", "skills": [], "agents": [], "commands": [], "mcp": [], "hooks": [],
             "deps": {}, "links": [{"name": x["name"], "url": x["url"],
                                    "desc": str(x.get("desc", ""))[:200]} for x in links]}]


def file_sha256(path):
    """EC-4: staleness is judged on content, so a same-content rewrite is not stale."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def plugin_root(r):
    repo = (r.get("repo") or "").rstrip("/")
    if not r.get("fetched") or not repo:
        return None
    path = os.path.join(ROOT, "repos", "__".join(repo.split("/")[-2:]), r.get("subpath") or "")
    return path if os.path.isdir(path) else None


def installed_sets():
    plugins, skills = set(), set()
    ip = os.path.join(HOME, ".claude/plugins/installed_plugins.json")
    if os.path.exists(ip):
        with open(ip) as fh:
            doc = json.load(fh)
        plugins = {k.split("@")[0] for k in (doc.get("plugins") or doc)}
    sd = os.path.join(HOME, ".claude/skills")
    if os.path.isdir(sd):
        skills = set(os.listdir(sd))
    return plugins, skills


def main():
    t = time.time()
    snap = os.path.join(ROOT, "snapshot.json")
    with open(snap) as fh:
        recs = json.load(fh)
    recs += qm_prompts.records(ROOT)        # FR-22: local prompt library, if configured
    recs += link_records(ROOT)               # FR-23: local tool links, if configured
    audits = {r["name"]: ("A", []) if "prompts" in r      # FR-22: text only, nothing runs
              else ("B", ["external link; nothing fetched or run"]) if "links" in r
              else tuple(qm_audit.audit_plugin(plugin_root(r), r.get("mcp"))) for r in recs}
    plugins, skills = installed_sets()
    idx = build(recs, audits, plugins, skills)
    idx["built_from"] = file_sha256(snap)
    tmp = os.path.join(ROOT, "qm_index.json.tmp")
    with open(tmp, "w") as fh:
        json.dump(idx, fh, separators=(",", ":"))
    os.replace(tmp, os.path.join(ROOT, "qm_index.json"))   # atomic: readers never see half a file
    grades = {}
    for g, _ in audits.values():
        grades[g] = grades.get(g, 0) + 1
    print(f"{idx['N']} components, grades {grades}, {time.time() - t:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
