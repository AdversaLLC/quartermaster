#!/usr/bin/env python3
"""Prompt library loader (FR-22, EC-10, EC-11).

Reads <data_dir>/prompt_sources.json (a JSON list of https git URLs), keeps a
shallow clone of each in <data_dir>/prompt_repos/<owner>__<repo>, and turns
each repo into one pseudo-plugin record whose "prompts" list holds a
200-char excerpt per text file. Prompt text never leaves the data dir.

Usage: python3 qm_prompts.py   (fetches all sources and prints counts)
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("QM_DATA") or os.path.dirname(os.path.abspath(__file__))
TEXT_EXTS = frozenset({".md", ".mkd", ".txt", ".xml", ".json", ".yaml", ".yml", ""})
SKIP_STEMS = frozenset({"README", "LICENSE", "LICENCE", "COPYING"})
MAX_BYTES = 200 * 1024
EXCERPT = 200
GIT_TIMEOUT = 300
_PART = re.compile(r"^[A-Za-z0-9._-]+$")


def load_sources(data_dir):
    """Return the list of source URLs, or [] when prompt_sources.json is absent."""
    path = os.path.join(data_dir, "prompt_sources.json")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        urls = json.load(fh)
    if not isinstance(urls, list):
        raise ValueError(f"{path}: expected a JSON list of URLs")
    return [u for u in urls if isinstance(u, str)]


def slug(url):
    """https://host/owner/repo(.git) -> owner__repo; None if unsafe or not https."""
    if not url.startswith("https://"):
        return None
    parts = url.rstrip("/").split("/")
    if len(parts) < 5:
        return None
    owner, repo = parts[-2], re.sub(r"\.git$", "", parts[-1])
    if not all(_PART.match(p) and p not in (".", "..") for p in (owner, repo)):
        return None
    return f"{owner}__{repo}"


def repo_dir(url, data_dir):
    name = slug(url)
    return os.path.join(data_dir, "prompt_repos", name) if name else None


def _git(argv):
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return res.returncode == 0, res.stderr.strip()


def fetch(url, data_dir):
    """Clone or fast-forward one source. Returns its local dir, or None (EC-10)."""
    dest = repo_dir(url, data_dir)
    if dest is None:
        print(f"warning: prompt source skipped (need https://host/owner/repo): {url}",
              file=sys.stderr)
        return None
    if os.path.isdir(os.path.join(dest, ".git")):
        ok, err = _git(["git", "-C", dest, "pull", "--ff-only", "--quiet"])
    else:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        ok, err = _git(["git", "clone", "--depth", "1", "--quiet", "--", url, dest])
    if not ok:
        print(f"warning: prompt source unreachable, continuing: {url} ({err[:200]})",
              file=sys.stderr)
        return None
    return dest


def _skip_reason(full, rel):
    base = os.path.basename(rel)
    stem, ext = os.path.splitext(base)
    if base.startswith("."):
        return "hidden"
    if stem.upper() in SKIP_STEMS:
        return "readme/license"
    if ext.lower() not in TEXT_EXTS:
        return "not text"
    if os.path.getsize(full) > MAX_BYTES:
        return "over 200 KB"
    return None


def _read_text(full):
    """Return decoded text, or None for binary content."""
    with open(full, "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _walk(base):
    """Yield (full, rel) for regular files under base; never follows symlinks."""
    real_base = os.path.realpath(base)
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, base)
            inside = os.path.realpath(full).startswith(real_base + os.sep)
            yield full, rel, (os.path.islink(full) or not inside)


def scan(base):
    """Return (prompts, skipped) for one cloned repo directory."""
    prompts, skipped = [], []
    for full, rel, unsafe in _walk(base):
        reason = "symlink" if unsafe else _skip_reason(full, rel)
        text = None if reason else _read_text(full)
        if not reason and text is None:
            reason = "binary"
        if reason:
            skipped.append({"path": rel, "reason": reason})
            continue
        prompts.append({"name": os.path.splitext(rel)[0], "path": rel,
                        "desc": " ".join(text.split())[:EXCERPT]})
    return prompts, skipped


def records(data_dir):
    """One pseudo-plugin record per configured source (fetch() not called here)."""
    out = []
    for url in load_sources(data_dir):
        dest = repo_dir(url, data_dir)
        present = bool(dest) and os.path.isdir(dest)
        prompts, skipped = scan(dest) if present else ([], [])
        rec = {"name": slug(url) or url, "summary": "prompt library", "fetched": present,
               "repo": url, "subpath": "", "skills": [], "agents": [], "commands": [],
               "mcp": [], "hooks": [], "deps": {}, "prompts": prompts, "skipped": skipped}
        if not present:
            rec["missing"] = True
        out.append(rec)
    return out


def main():
    urls = load_sources(ROOT)
    if not urls:
        print(f"no prompt sources ({os.path.join(ROOT, 'prompt_sources.json')} absent or empty)")
        return 0
    for url in urls:
        fetch(url, ROOT)
    for rec in records(ROOT):
        state = "missing" if rec.get("missing") else "ok"
        print(f"{rec['name']}: {state}, {len(rec['prompts'])} prompts indexed, "
              f"{len(rec['skipped'])} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
