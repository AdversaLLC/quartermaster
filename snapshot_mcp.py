#!/usr/bin/env python3
"""Single stdio MCP server over the local plugin snapshot (snapshot.json).

Stdlib only, read-only: lists, searches and describes every agent, skill,
command, hook and MCP server in the snapshot. Installs nothing. Output is
compact tab-separated text to keep tokens low.
"""
import json
import os
import sys

ROOT = os.environ.get("QM_DATA") or os.path.dirname(os.path.abspath(__file__))   # data dir; code may live in /usr/lib
KINDS = ("agents", "skills", "commands", "mcp", "hooks")
MAX_CHARS = 8000
HINT = "[truncated: page with offset/limit, or narrow with search query/type]"
_DATA = None


def cap(text):
    """FR-9: keep every response <= MAX_CHARS, cut on a line boundary."""
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS - len(HINT) - 1]
    cut = cut[:cut.rfind("\n")] if "\n" in cut else cut
    shown = cut.count("\n")
    return f"{cut}\n{HINT.replace(']', f'; {shown} rows shown — next offset +{shown}]')}"


def data():
    global _DATA
    if _DATA is None:
        _DATA = json.load(open(os.path.join(ROOT, "snapshot.json")))
    return _DATA


def rows(kind):
    for r in data():
        for c in r.get(kind) or []:
            if kind == "hooks":
                yield {"name": str(c), "desc": ""}, r
            else:
                yield c, r


def fmt(c, r, kind):
    desc = (c.get("desc") or "").replace("\t", " ").replace("\n", " ")[:120]
    return f"{kind[:-1] if kind != 'mcp' else 'mcp'}\t{c.get('name')}\t{r['name']}\t{desc}"


def t_stats(_):
    d = data()
    out = {k: sum(len(r.get(k) or []) for r in d) for k in KINDS}
    out["plugins"] = len(d)
    out["fetched"] = sum(bool(r.get("fetched")) for r in d)
    return json.dumps(out)


def t_list(a):
    kind = a.get("type", "skills")
    if kind not in KINDS:
        return f"type must be one of {', '.join(KINDS)}"
    off, lim = int(a.get("offset", 0)), min(int(a.get("limit", 50)), 200)
    items = list(rows(kind))
    body = "\n".join(fmt(c, r, kind) for c, r in items[off:off + lim])
    return f"{len(items)} total, showing {off}-{off + lim}\n{body}"


def t_search(a):
    q = a.get("query", "").lower().split()
    kinds = [a["type"]] if a.get("type") in KINDS else KINDS
    lim = min(int(a.get("limit", 30)), 200)
    hits = []
    for kind in kinds:
        for c, r in rows(kind):
            text = f"{c.get('name')} {c.get('desc', '')} {r['name']} {r.get('summary', '')}".lower()
            if all(w in text for w in q):
                hits.append(fmt(c, r, kind))
                if len(hits) >= lim:
                    return "\n".join(hits)
    return "\n".join(hits) or "no matches; try fewer or shorter words, or drop the type filter"


def t_get(a):
    name = a.get("plugin", "").lower()
    for r in data():
        if r["name"].lower() == name or r.get("id", "").lower() == name:
            slim = {k: v for k, v in r.items() if v not in (None, [], {}, "")}
            for k in ("skills", "agents", "commands"):
                if k in slim:
                    slim[k] = [i["name"] for i in slim[k]]
            return json.dumps(slim, separators=(",", ":"))
    return "not found; use the search tool to find the exact plugin name"


ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False,
               "idempotentHint": True, "openWorldHint": False}

TOOLS = {
    "stats": (t_stats, "Counts of plugins, agents, skills, commands, MCP servers, hooks.", {}),
    "list": (t_list, "Page through one component type.",
             {"type": {"type": "string", "enum": list(KINDS)}, "offset": {"type": "integer"},
              "limit": {"type": "integer"}}),
    "search": (t_search, "Keyword search (all words must match) across components.",
               {"query": {"type": "string", "description": "words, e.g. 'pdf extract'"},
                "type": {"type": "string", "enum": list(KINDS)},
                "limit": {"type": "integer"}}),
    "get": (t_get, "Full record for one plugin: components, MCP config, dependencies, repo.",
            {"plugin": {"type": "string", "description": "plugin name or id from search/list"}}),
}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        res = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
               "capabilities": {"tools": {}},
               "serverInfo": {"name": "plugin-snapshot", "version": "0.1.0"}}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d,
                          "inputSchema": {"type": "object", "properties": p},
                          "annotations": ANNOTATIONS}
                         for n, (_, d, p) in TOOLS.items()]}
    elif method == "tools/call":
        p = msg.get("params", {})
        fn = TOOLS.get(p.get("name"), (None,))[0]
        if fn is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool"}}
        try:
            text = cap(fn(p.get("arguments") or {}))
            res = {"content": [{"type": "text", "text": text}]}
        except (ValueError, KeyError, OSError) as e:
            res = {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
    elif mid is None:
        return None
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
