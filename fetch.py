#!/usr/bin/env python3
"""Fetch only manifest files of every plugin repo in the Claude plugin directory.

Nothing is installed or executed: each repo is fetched blobless at its reviewed
commit and only the manifest/dependency files are checked out.
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("QM_DATA") or os.path.dirname(os.path.abspath(__file__))   # data dir; code may live in /usr/lib
OUT = os.path.join(ROOT, "repos")
DIRECTORY = os.path.expanduser("~/.claude/plugins/plugin-directory-cache-v2.json")
WANT = re.compile(
    r"(^|/)(plugin\.json|marketplace\.json|\.mcp\.json|SKILL\.md|hooks\.json|"
    r"package\.json|requirements[^/]*\.txt|pyproject\.toml|Cargo\.toml|go\.mod|"
    r"Dockerfile)$|(^|/)(agents|commands)/[^/]+\.md$"
)
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")


def git(args, cwd, timeout=120):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True,
                          text=True, timeout=timeout)


def fetch(url, sha):
    name = "__".join(url.rstrip("/").split("/")[-2:])
    dest = os.path.join(OUT, name)
    if os.path.exists(os.path.join(dest, ".done")):
        return name, "skip"
    os.makedirs(dest, exist_ok=True)
    try:
        git(["init", "-q"], dest)
        git(["remote", "add", "origin", url], dest)
        r = git(["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha], dest)
        if r.returncode:
            return name, "FAIL fetch: " + r.stderr.strip().splitlines()[-1][:120]
        files = git(["ls-tree", "-r", "--name-only", "FETCH_HEAD"], dest).stdout.split("\n")
        keep = [f for f in files if f and WANT.search(f) and "node_modules/" not in f]
        if keep:
            for i in range(0, len(keep), 200):
                git(["checkout", "-q", "FETCH_HEAD", "--", *keep[i:i + 200]], dest, 300)
        with open(os.path.join(dest, ".done"), "w") as fh:
            json.dump({"url": url, "sha": sha, "files": len(files), "kept": len(keep)}, fh)
        return name, f"ok {len(keep)}"
    except subprocess.TimeoutExpired:
        return name, "FAIL timeout"


def norm_url(url):
    url = url.rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def marketplace_sources(base):
    """FR-13: marketplace entries that live in external repos (url / git-subdir).

    Relative sources are already on disk; npm/command sources get url=None.
    """
    out = []
    for mk in sorted(os.listdir(base)):
        mf = os.path.join(base, mk, ".claude-plugin", "marketplace.json")
        try:
            plugins = json.load(open(mf)).get("plugins", [])
        except (OSError, ValueError):
            continue
        for p in plugins:
            s = p.get("source")
            if not isinstance(s, dict):
                continue
            kind = s.get("source")
            url = norm_url(s["url"]) if kind in ("url", "git-subdir") and s.get("url") else None
            out.append({"name": p.get("name"), "marketplace": mk, "kind": kind, "url": url,
                        "sha": s.get("sha") or s.get("ref") or "HEAD",
                        "subpath": (s.get("path") or "").strip("/"),
                        "summary": p.get("description", "")})
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    listings = json.load(open(DIRECTORY))["listings"]
    repos = {}
    for x in listings:
        r = x["source"]["repository"]
        repos[norm_url(r["url"])] = r["reviewed_commit"]
    for s in marketplace_sources(os.path.expanduser("~/.claude/plugins/marketplaces")):
        if s["url"] and s["url"].startswith("https://") and s["url"] not in repos:
            repos[s["url"]] = s["sha"]
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for name, status in ex.map(lambda kv: fetch(*kv), repos.items()):
            done += 1
            print(f"[{done}/{len(repos)}] {name} {status}", flush=True)
    print("ALLDONE", flush=True)


if __name__ == "__main__":
    main()
