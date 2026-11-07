"""Markdown list writers for the plugin snapshot (split from build_index)."""
import os
import re
from collections import defaultdict


def write_lists(recs, out_root):
    os.makedirs(os.path.join(out_root, "lists"), exist_ok=True)
    for kind in ("agents", "skills", "commands"):
        with open(os.path.join(out_root, "lists", f"{kind}.md"), "w") as fh:
            fh.write(f"# {kind}\n\n| {kind[:-1]} | plugin | marketplace | description |\n|---|---|---|---|\n")
            for r in recs:
                for c in r.get(kind) or []:
                    desc = (c.get("desc") or "").replace("|", "/").replace("\n", " ")[:140]
                    fh.write(f"| {c['name']} | {r['name']} | {r['marketplace']} | {desc} |\n")
    with open(os.path.join(out_root, "lists", "tools-mcp.md"), "w") as fh:
        fh.write("# tools (MCP servers)\n\n| server | plugin | type | command / url | env keys |\n|---|---|---|---|---|\n")
        for r in recs:
            for m in r.get("mcp") or []:
                how = m.get("url") or " ".join([m.get("command") or "", *map(str, m.get("args") or [])])
                fh.write(f"| {m['name']} | {r['name']} | {m.get('type', '')} | {how[:100]} | {', '.join(m.get('env') or [])} |\n")
    with open(os.path.join(out_root, "lists", "hooks.md"), "w") as fh:
        fh.write("# hooks\n\n| plugin | events |\n|---|---|\n")
        for r in recs:
            if r.get("hooks"):
                fh.write(f"| {r['name']} | {', '.join(map(str, r['hooks']))} |\n")
    with open(os.path.join(out_root, "lists", "dependencies.md"), "w") as fh:
        fh.write("# install dependencies\n\n| plugin | runtime | packages |\n|---|---|---|\n")
        for r in recs:
            deps = r.get("deps") or {}
            if deps or r.get("runtime"):
                pk = "; ".join(f"{k}: {', '.join(v[:12])}{' …' if len(v) > 12 else ''}" for k, v in deps.items())
                fh.write(f"| {r['name']} | {', '.join(r.get('runtime') or [])} | {pk} |\n")


def write_failures(log_path, out_root):
    """FR-7: every repo that failed to fetch, with its reason."""
    os.makedirs(os.path.join(out_root, "lists"), exist_ok=True)
    rows = []
    if os.path.exists(log_path):
        for ln in open(log_path, errors="replace"):
            m = re.match(r"\[\d+/\d+\] (\S+) FAIL (.*)$", ln.strip())
            if m:
                rows.append((m.group(1), m.group(2).replace("|", "/")))
    with open(os.path.join(out_root, "lists", "fetch-failures.md"), "w") as fh:
        fh.write(f"# fetch failures ({len(rows)})\n\n| repo | reason |\n|---|---|\n")
        fh.writelines(f"| {r} | {why} |\n" for r, why in rows)


def write_duplicates(recs, out_root):
    """FR-11: component names shipped by more than one plugin."""
    seen = defaultdict(set)
    for r in recs:
        for kind in ("skills", "agents", "commands"):
            for c in r.get(kind) or []:
                seen[(kind[:-1], c["name"])].add(r["name"])
    dups = sorted(((k, n, sorted(p)) for (k, n), p in seen.items() if len(p) > 1),
                  key=lambda x: -len(x[2]))
    os.makedirs(os.path.join(out_root, "lists"), exist_ok=True)
    with open(os.path.join(out_root, "lists", "duplicates.md"), "w") as fh:
        fh.write(f"# duplicate names ({len(dups)})\n\n| kind | name | count | plugins |\n|---|---|---|---|\n")
        for k, n, p in dups:
            fh.write(f"| {k} | {n} | {len(p)} | {', '.join(p[:8])}{' …' if len(p) > 8 else ''} |\n")
