"""NFR-6 / AC-10: Recall@k of BM25 routing vs a keyword-rules-only baseline
over the labeled set in tests/routing_set.json. Labels were written by Claude:
a sanity check, not a benchmark."""
import json
import os

import qm_build
import qm_route
import qm_teams

HERE = os.path.dirname(os.path.abspath(__file__))
SET_PATH = os.path.join(HERE, "tests", "routing_set.json")
INDEX_PATH = os.path.join(HERE, "qm_index.json")


def load_set(path=SET_PATH):
    with open(path) as fh:
        return json.load(fh)


def _hit(names, expect):
    subs = [e.lower() for e in expect]
    return any(s in n.lower() for n in names for s in subs)


def parse_route(text):
    """Return (team, {station: [ids]}) from a route() kit."""
    team, station, stations = None, None, {}
    for line in text.splitlines():
        if line.startswith("team: "):
            team = line[len("team: "):].split()[0]
        elif line.startswith("## "):
            station = line[3:].split()[0]
        elif line.startswith("- ") and station:
            stations.setdefault(station, []).append(line[2:].split("|")[0].strip())
    return team, stations


def bm25_top(idx, task, k=5):
    """First k unique ids: the execute station first, then the others in kit order."""
    team, stations = parse_route(qm_route.route(idx, task))
    order = ["execute"] + [s for s in stations if s != "execute"]
    out = []
    for s in order:
        for ident in stations.get(s, []):
            if ident not in out:
                out.append(ident)
    return team, out[:k]


def rules_top(idx, task, k=5):
    """A/B components whose primary team equals the task's rule team,
    ranked by how many task tokens appear in their terms, tie-break by id."""
    team = qm_teams.teams_for(task)[0][0]
    q = set(qm_build.terms(task))
    cands = [c for c in idx["components"]
             if c["grade"] in ("A", "B") and c["teams"] and c["teams"][0][0] == team]
    cands.sort(key=lambda c: (-len(q & set(c["terms"])), c["id"]))
    return [c["id"] for c in cands[:k]]


def _name(ident):
    return ident.rsplit("@", 1)[0]


def score(idx, items, k=5):
    """Per-task rows: task, label, routed team, bm25 ids/hit, rules ids/hit."""
    rows = []
    for it in items:
        team, b = bm25_top(idx, it["task"], k)
        r = rules_top(idx, it["task"], k)
        rows.append({"task": it["task"], "label": it["team"], "team": team,
                     "bm25": b, "bm25_hit": _hit(map(_name, b), it["expect"]),
                     "rules": r, "rules_hit": _hit(map(_name, r), it["expect"])})
    return rows


def evaluate(idx, k=5, items=None):
    """Return (bm25_recall, rules_recall) at k over the labeled set."""
    rows = score(idx, items if items is not None else load_set(), k)
    n = len(rows) or 1
    return sum(r["bm25_hit"] for r in rows) / n, sum(r["rules_hit"] for r in rows) / n


def report(rows):
    n = len(rows) or 1
    print(f"{'bm25':4} {'rule':4} {'team ok':7} {'label':22} {'routed':22} task")
    for r in rows:
        ok = "y" if r["team"] == r["label"] else "n"
        print(f"{'HIT' if r['bm25_hit'] else '-':4} {'HIT' if r['rules_hit'] else '-':4} "
              f"{ok:7} {r['label']:22} {str(r['team']):22} {r['task'][:60]}")
    bm = sum(r["bm25_hit"] for r in rows) / n
    ru = sum(r["rules_hit"] for r in rows) / n
    acc = sum(r["team"] == r["label"] for r in rows) / n
    print(f"\nRecall@5 bm25={bm:.2f} rules={ru:.2f} | team accuracy={acc:.2f} | n={len(rows)}")
    print("\nBM25 misses (returned instead):")
    for r in rows:
        if not r["bm25_hit"]:
            print(f"- {r['task']}\n    {', '.join(r['bm25']) or '(nothing)'}")


if __name__ == "__main__":
    report(score(qm_route.load(INDEX_PATH), load_set()))
