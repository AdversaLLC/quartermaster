"""FR-3/FR-4: declared-risk grade A-D from a plugin's files. Reads only; never
executes anything. Grade A means "nothing risky declared", not "safe"."""
import json
import os
import re

SEVERITY = {"A": 0, "B": 1, "C": 2, "D": 3}
TEXT_EXT = (".md", ".json", ".sh", ".js", ".mjs", ".cjs", ".py", ".ts")
MAX_FILES, MAX_BYTES = 400, 200_000
HIDDEN = re.compile("[​-‏‪-‮⁦-⁩]")
CRED_KEY = re.compile(r"(key|token|secret|password|passwd|credential|auth)", re.I)

# (pattern, reason, grade) checked against hook command strings
HOOK_RULES = [
    (re.compile(r"(curl|wget)[^|;&]*\|\s*(ba|z)?sh\b"), "pipe to shell", "D"),
    (re.compile(r"base64\s+(-d|--decode)[^|]*\|\s*(ba|z)?sh|eval\s*\(?\s*[\"'$`]"), "decode-and-run", "D"),
    (re.compile(r"\bsudo\b"), "sudo in hook", "C"),
    (re.compile(r"\b(curl|wget)\b"), "network call in hook", "C"),
    (re.compile(r"npx\s+(-y\s+)?\S+@latest"), "unpinned npx @latest", "B"),
]


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(MAX_BYTES)
    except OSError:
        return ""


def _json(path):
    try:
        return json.loads(_read(path))
    except ValueError:
        return None


def _files(root):
    n = 0
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in ("node_modules", ".git", "vendor", "dist")]
        for f in files:
            if f.endswith(TEXT_EXT):
                n += 1
                if n > MAX_FILES:
                    return
                yield os.path.join(d, f)


def _hook_findings(doc):
    out = []
    hooks = (doc or {}).get("hooks", doc) if isinstance(doc, dict) else {}
    if not isinstance(hooks, dict):
        return out
    for event, groups in hooks.items():
        for g in groups if isinstance(groups, list) else []:
            if not isinstance(g, dict):
                continue
            if event in ("PreToolUse", "PostToolUse") and g.get("matcher") in (None, "", "*"):
                out.append(("hook on every tool call", "B"))
            for h in g.get("hooks") or []:
                cmd = h.get("command", "") if isinstance(h, dict) else ""
                for rx, reason, grade in HOOK_RULES:
                    if rx.search(cmd):
                        out.append((reason, grade))
    return out


def _file_findings(path):
    name = os.path.basename(path)
    if name == "package.json":
        scripts = (_json(path) or {}).get("scripts") or {}
        if isinstance(scripts, dict) and ({"postinstall", "preinstall", "install"} & set(scripts)):
            return [("postinstall install script", "C")]
        return []
    if name in ("hooks.json", "plugin.json", "settings.json"):
        doc = _json(path)
        out = _hook_findings(doc)
        if isinstance(doc, dict) and doc.get("monitors"):
            out.append(("declares monitors", "B"))
        return out
    if name.endswith(".md"):
        text = _read(path)
        out = [("hidden unicode", "C")] if HIDDEN.search(text) else []
        head = text[:2000]
        if re.search(r"^allowed-tools:.*\bBash\b(?!\()", head, re.M):
            out.append(("unrestricted Bash in allowed-tools", "B"))
        return out
    return []


def _mcp_findings(servers):
    out = []
    for s in servers or []:
        url = (s or {}).get("url") or ""
        if url.startswith("http://") and "127.0.0.1" not in url and "localhost" not in url:
            out.append(("plain-http remote MCP", "C"))
        elif url.startswith("https://"):
            out.append(("remote MCP", "B"))
        if any(CRED_KEY.search(str(k)) for k in (s or {}).get("env") or []):
            out.append(("MCP asks for credentials", "B"))
        args = " ".join(map(str, (s or {}).get("args") or []))
        if "@latest" in args:
            out.append(("unpinned npx @latest", "B"))
    return out


def audit_plugin(root, mcp_servers):
    """Return (grade, sorted unique reasons). root=None means not fetched."""
    if root is None:
        return "unaudited", ["plugin files not fetched"]
    findings = _mcp_findings(mcp_servers)
    if os.path.isdir(root):
        for path in _files(root):
            findings.extend(_file_findings(path))
    if not findings:
        return "A", []
    grade = max((g for _, g in findings), key=SEVERITY.get)
    return grade, sorted({r for r, _ in findings})
