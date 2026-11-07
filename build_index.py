#!/usr/bin/env python3
"""Sort every plugin component in the local snapshot into agents, skills, tools
(MCP servers), commands and hooks, with install dependencies. Read-only.

Sources: fetched directory repos (repos/), cloned marketplaces, catalog cache.
Output: snapshot.json + one markdown list per component type.
"""
import json
import os
import re
import tomllib
from collections import defaultdict

import fetch
from writers import write_duplicates, write_failures, write_lists  # noqa: F401

ROOT = os.environ.get("QM_DATA") or os.path.dirname(os.path.abspath(__file__))   # data dir; code may live in /usr/lib
PLUG = os.path.expanduser("~/.claude/plugins")
FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def frontmatter(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read(8000)
    except OSError:
        return {}
    m = FM.match(text)
    out = {}
    if m:
        key = None
        for line in m.group(1).splitlines():
            if line.startswith((" ", "\t")):
                if key and out.get(key) in ("", ">", ">-", "|", "|-", ">+", "|+"):
                    out[key] = line.strip()
                elif key and out.get(key) is not None and line.strip():
                    out[key] += " " + line.strip()
                continue
            k, sep, v = line.partition(":")
            if sep:
                key = k.strip()
                out[key] = v.strip().strip("'\"")
    return out


def load_json(path):
    try:
        return json.load(open(path, encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def plugin_root(path, repo):
    """Nearest ancestor holding .claude-plugin/plugin.json, else the repo root."""
    d = os.path.dirname(path)
    while d.startswith(repo):
        if os.path.exists(os.path.join(d, ".claude-plugin", "plugin.json")):
            return d
        if d == repo:
            break
        d = os.path.dirname(d)
    return repo


def mcp_entries(servers):
    out = []
    for name, cfg in (servers or {}).items():
        if not isinstance(cfg, dict):
            continue
        env = cfg.get("env") or {}
        keys = env.keys() if isinstance(env, dict) else [str(e).split("=")[0] for e in env] \
            if isinstance(env, list) else []
        args = cfg.get("args") or []
        args = [args] if isinstance(args, str) else list(args) if isinstance(args, list) else []
        out.append({"name": name, "type": cfg.get("type", "url" if cfg.get("url") else "stdio"),
                    "command": cfg.get("command"), "args": args[:6],
                    "url": cfg.get("url"), "env": sorted(set(keys))})
    return out


def deps_of(path):
    base = os.path.basename(path)
    if base == "package.json":
        j = load_json(path) or {}
        return {"npm": sorted({**j.get("dependencies", {}), **j.get("peerDependencies", {})})}
    if base.startswith("requirements") and base.endswith(".txt"):
        names = [re.split(r"[<>=!~\[; ]", ln.strip())[0] for ln in open(path, errors="replace")]
        return {"pip": sorted({n for n in names if n and not n.startswith(("#", "-"))})}
    if base == "pyproject.toml":
        try:
            t = tomllib.load(open(path, "rb"))
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        names = [re.split(r"[<>=!~\[; ]", d)[0] for d in t.get("project", {}).get("dependencies", [])]
        return {"pip": sorted(set(filter(None, names)))}
    if base == "Cargo.toml":
        try:
            return {"cargo": sorted(tomllib.load(open(path, "rb")).get("dependencies", {}))}
        except (OSError, tomllib.TOMLDecodeError):
            return {}
    if base == "go.mod":
        return {"go": sorted(re.findall(r"^\s+(\S+)\s+v", open(path, errors="replace").read(), re.M))}
    if base == "Dockerfile":
        return {"docker": ["Dockerfile"]}
    return {}


def scan_repo(repo, source):
    plugins = defaultdict(lambda: {"skills": [], "agents": [], "commands": [], "hooks": [],
                                   "mcp": [], "deps": defaultdict(set), "source": source})
    for dirpath, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        for f in files:
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, repo)
            P = plugins[os.path.relpath(plugin_root(p, repo), repo)]
            if f == "SKILL.md":
                fm = frontmatter(p)
                P["skills"].append({"name": fm.get("name") or os.path.basename(dirpath),
                                    "desc": fm.get("description", "")[:200], "path": rel})
            elif f.endswith(".md") and os.path.basename(dirpath) in ("agents", "commands"):
                fm = frontmatter(p)
                kind = os.path.basename(dirpath)
                P[kind].append({"name": fm.get("name") or f[:-3],
                                "desc": fm.get("description", "")[:200], "path": rel})
            elif f == "hooks.json":
                j = load_json(p) or {}
                h = j.get("hooks", j) if isinstance(j, dict) else j
                if isinstance(h, dict):
                    P["hooks"].extend(sorted(h.keys()))
                elif isinstance(h, list):
                    P["hooks"].extend(str(e.get("event") or e.get("type") or "hook")
                                      for e in h if isinstance(e, dict))
            elif f == ".mcp.json":
                j = load_json(p) or {}
                P["mcp"].extend(mcp_entries(j.get("mcpServers", j)))
            elif f == "plugin.json":
                j = load_json(p) or {}
                if isinstance(j.get("mcpServers"), dict):
                    P["mcp"].extend(mcp_entries(j["mcpServers"]))
                P["meta"] = {k: j.get(k) for k in ("name", "version", "description") if j.get(k)}
            else:
                for k, v in deps_of(p).items():
                    P["deps"][k].update(v)
    return plugins


def runtime_deps(mcp):
    run = set()
    for m in mcp:
        cmd = os.path.basename(m.get("command") or "")
        if cmd in ("npx", "node", "bun", "bunx", "deno"):
            run.add("node" if cmd in ("npx", "node") else cmd)
        elif cmd in ("uvx", "uv", "python", "python3", "pipx"):
            run.add("python/" + cmd)
        elif cmd == "docker":
            run.add("docker")
        elif cmd:
            run.add(cmd)
        if m.get("url"):
            run.add("remote-http")
    return sorted(run)


def merge(roots, prefix):
    out = {"skills": [], "agents": [], "commands": [], "hooks": [], "mcp": [], "deps": defaultdict(set)}
    for rel, P in roots.items():
        if prefix and not (rel == prefix or rel.startswith(prefix + "/")):
            continue
        for k in ("skills", "agents", "commands", "hooks", "mcp"):
            out[k].extend(P[k])
        for k, v in P["deps"].items():
            out["deps"][k] |= v
    out["hooks"] = sorted(set(out["hooks"]))
    out["deps"] = {k: sorted(v) for k, v in out["deps"].items() if v}
    out["runtime"] = runtime_deps(out["mcp"])
    return out


def directory_records():
    d = load_json(os.path.join(PLUG, "plugin-directory-cache-v2.json"))
    claims, scans, recs = d["entryNameClaims"], {}, []
    for x in d["listings"]:
        url = x["source"]["repository"]["url"]
        name = "__".join(url.rstrip("/").split("/")[-2:])
        repo = os.path.join(ROOT, "repos", name)
        fetched = os.path.exists(os.path.join(repo, ".done"))
        if fetched and name not in scans:
            scans[name] = scan_repo(repo, "directory")
        sub = claims.get(x["id"], {}).get("repositoryKey", "").partition("#")[2].strip("/")
        comp = merge(scans[name], sub) if fetched else None
        recs.append({"id": x["id"], "name": d["entryNames"].get(x["id"], x["name"]),
                     "title": x["name"], "summary": x.get("summary", ""),
                     "marketplace": "directory", "repo": url, "subpath": sub,
                     "sha": x["source"]["repository"]["reviewed_commit"],
                     "fetched": fetched, **(comp or {})})
    return recs


def marketplace_records():
    recs = []
    base = os.path.join(PLUG, "marketplaces")
    for mk in sorted(os.listdir(base)):
        roots = scan_repo(os.path.join(base, mk), mk)
        for rel, P in roots.items():
            if not any(P[k] for k in ("skills", "agents", "commands", "hooks", "mcp")):
                continue
            meta = P.get("meta", {})
            recs.append({"id": f"{mk}:{rel}", "name": meta.get("name") or os.path.basename(rel) or mk,
                         "summary": meta.get("description", ""), "marketplace": mk,
                         "subpath": rel, "fetched": True, **merge({rel: P}, "")})
    return recs


def external_records(srcs):
    """FR-13: records for marketplace entries hosted in external repos."""
    recs, scans = [], {}
    for s in srcs:
        rec = {"id": f"{s['marketplace']}:{s['name']}", "name": s["name"], "summary": s.get("summary", ""),
               "marketplace": s["marketplace"], "repo": s["url"], "sha": s["sha"],
               "subpath": s["subpath"], "fetched": False}
        if not s["url"]:
            rec["not_fetchable"] = f"{s['kind']} source"
            recs.append(rec)
            continue
        name = "__".join(s["url"].split("/")[-2:])
        repo = os.path.join(ROOT, "repos", name)
        if os.path.exists(os.path.join(repo, ".done")):
            if name not in scans:
                scans[name] = scan_repo(repo, s["marketplace"])
            rec.update(fetched=True, **merge(scans[name], s["subpath"]))
        recs.append(rec)
    return recs


def catalog_fill(recs):
    """Use the official catalog's component names for anything not fetched."""
    cat = (load_json(os.path.join(PLUG, "plugin-catalog-cache.json")) or {}).get("catalog", {})
    by_name = {v["plugin"]: v for v in cat.get("plugins", {}).values()}
    for r in recs:
        c = by_name.get(r["name"])
        if c and not r.get("fetched"):
            comp = c["components"]
            for k, ck in (("skills", "skills"), ("agents", "agents"), ("commands", "commands")):
                r[k] = [{"name": i["name"], "desc": "", "path": ""} for i in comp.get(ck, [])]
            r["mcp"] = [{"name": i["name"] if isinstance(i, dict) else i} for i in comp.get("mcpServers", [])]
            r["hooks"] = [i["name"] if isinstance(i, dict) else i for i in comp.get("hooks", [])]
            r["source_of_components"] = "catalog-cache"
        if c:
            r["tokens"] = c.get("tokens")
            r["installs"] = c.get("unique_installs")


def main():
    recs = directory_records() + marketplace_records()
    known = {r["name"].lower() for r in recs}
    srcs = fetch.marketplace_sources(os.path.join(PLUG, "marketplaces"))
    recs += [r for r in external_records(srcs) if r["name"].lower() not in known]
    catalog_fill(recs)
    json.dump(recs, open(os.path.join(ROOT, "snapshot.json"), "w"), indent=1)
    write_lists(recs, ROOT)
    write_failures(os.path.join(ROOT, "fetch.log"), ROOT)
    write_duplicates(recs, ROOT)
    count = lambda k: sum(len(r.get(k) or []) for r in recs)
    print(json.dumps({"plugins": len(recs), "fetched": sum(bool(r.get("fetched")) for r in recs),
                      "skills": count("skills"), "agents": count("agents"),
                      "commands": count("commands"), "mcp_servers": count("mcp"),
                      "with_hooks": sum(bool(r.get("hooks")) for r in recs),
                      "with_deps": sum(bool(r.get("deps")) for r in recs)}, indent=1))


if __name__ == "__main__":
    main()
