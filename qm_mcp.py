#!/usr/bin/env python3
"""Quartermaster: stdio MCP that routes a task to a carved-out kit (ROUTER-SPEC.md).

Stdlib only, no network, read-only. Two tools: route, explain.
"""
import json
import os
import sys

import qm_route

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.environ.get("QM_INDEX", os.path.join(ROOT, "qm_index.json"))
_IDX = None
ANNOTATIONS = {"readOnlyHint": True, "destructiveHint": False,
               "idempotentHint": True, "openWorldHint": False}


def idx():
    global _IDX
    if _IDX is None:
        if not os.path.exists(INDEX):
            raise OSError("qm_index.json missing: run ./rebuild.sh")
        _IDX = qm_route.load(INDEX)
    return _IDX


def t_route(a):
    task = str(a.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")
    return qm_route.route(idx(), task, bool(a.get("allow_risky")), a.get("depth", "normal"))


def t_explain(a):
    return qm_route.explain(idx(), str(a.get("id") or ""))


TOOLS = {
    "route": (t_route, "Describe a task; get the team, a per-step kit (skills/agents/MCP, "
                       "graded, installed y/n) and call-a-friend checkpoints.",
              {"task": {"type": "string"}, "allow_risky": {"type": "boolean"},
               "depth": {"type": "string", "enum": ["normal", "deep"]}}),
    "explain": (t_explain, "Why a component was routed: teams, rules, risk grade, reasons.",
                {"id": {"type": "string", "description": "name@plugin"}}),
}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        res = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
               "capabilities": {"tools": {}},
               "serverInfo": {"name": "quartermaster", "version": "0.1.0"}}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d,
                          "inputSchema": {"type": "object", "properties": p, "required": [next(iter(p))]},
                          "annotations": ANNOTATIONS}
                         for n, (_, d, p) in TOOLS.items()]}
    elif method == "tools/call":
        p = msg.get("params", {})
        fn = TOOLS.get(p.get("name"), (None,))[0]
        if fn is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool"}}
        try:
            res = {"content": [{"type": "text", "text": fn(p.get("arguments") or {})}]}
        except (ValueError, KeyError, OSError, RuntimeError) as e:
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
