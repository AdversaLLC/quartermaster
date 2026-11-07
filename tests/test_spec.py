"""Acceptance tests for SPEC.md (AC-1 .. AC-13).

Unit tests use small fixture repos. Tests marked `snapshot` need the real
fetch to have finished and are skipped until then.
"""
import json
import os
import re
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build_index as bi  # noqa: E402
import snapshot_mcp as sm  # noqa: E402

LOG = os.path.join(ROOT, "fetch.log")
FETCH_DONE = os.path.exists(LOG) and "ALLDONE" in open(LOG).read()
snapshot = pytest.mark.skipif(not FETCH_DONE, reason="real fetch not finished")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "owner__repo"
    write(str(r / "skills/x/SKILL.md"), "---\nname: x\ndescription: >-\n  first line\n  second line\n---\nbody\n")
    write(str(r / "agents/y.md"), "---\nname: y\ndescription: agent y\n---\n")
    write(str(r / "commands/z.md"), "---\ndescription: cmd z\n---\n")
    write(str(r / ".mcp.json"), json.dumps({"mcpServers": {"srv": {
        "command": "npx", "args": ["-y", "pkg"], "env": {"API_KEY": "secret-value-123"}}}}))
    write(str(r / "hooks/hooks.json"), json.dumps([{"event": "PreToolUse"}]))
    return str(r)


def test_ac3_classifies_components(repo):
    c = bi.merge(bi.scan_repo(repo, "t"), "")
    assert [s["name"] for s in c["skills"]] == ["x"]
    assert [a["name"] for a in c["agents"]] == ["y"]
    assert [m["name"] for m in c["commands"]] == ["z"]
    assert c["hooks"] == ["PreToolUse"]  # EC-4: list-shaped hooks.json


def test_ac4_yaml_folded_description(repo):
    c = bi.merge(bi.scan_repo(repo, "t"), "")
    assert c["skills"][0]["desc"] == "first line second line"


def test_ac5_runtime_env_keys_no_secret(repo):
    c = bi.merge(bi.scan_repo(repo, "t"), "")
    assert c["runtime"] == ["node"]
    assert c["mcp"][0]["env"] == ["API_KEY"]
    assert "secret-value-123" not in json.dumps(c)


def test_ec3_malformed_json_skipped(repo):
    write(os.path.join(repo, "sub/.mcp.json"), "{not json")
    c = bi.merge(bi.scan_repo(repo, "t"), "")
    assert [m["name"] for m in c["mcp"]] == ["srv"]


def test_ec3_odd_mcp_shapes(repo):
    write(os.path.join(repo, "odd/.mcp.json"), json.dumps({"mcpServers": {
        "a": {"command": "uvx", "args": "single-string", "env": ["TOKEN", "OTHER=1"]},
        "b": "not-a-dict"}}))
    c = bi.merge(bi.scan_repo(repo, "t"), "")
    a = next(m for m in c["mcp"] if m["name"] == "a")
    assert a["env"] == ["OTHER", "TOKEN"] and a["args"] == ["single-string"]
    assert "python/uvx" in c["runtime"]


def test_ec5_subpath_split(tmp_path):
    r = str(tmp_path / "mono")
    for p in ("a", "b"):
        write(f"{r}/plugins/{p}/.claude-plugin/plugin.json", json.dumps({"name": p}))
        write(f"{r}/plugins/{p}/skills/s{p}/SKILL.md", f"---\nname: s{p}\n---\n")
    roots = bi.scan_repo(r, "t")
    assert [s["name"] for s in bi.merge(roots, "plugins/a")["skills"]] == ["sa"]


def test_ac7_fetch_failures_listed(tmp_path):
    log = tmp_path / "fetch.log"
    log.write_text("[1/2] a__ok ok 3\n[2/2] b__gone FAIL fetch: repository not found\nALLDONE\n")
    bi.write_failures(str(log), str(tmp_path))
    text = (tmp_path / "lists" / "fetch-failures.md").read_text()
    assert "b__gone" in text and "repository not found" in text and "a__ok" not in text


def test_ac8_exactly_four_tools():
    res = sm.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]
    assert sorted(t["name"] for t in res["tools"]) == ["get", "list", "search", "stats"]


def test_ac9_response_capped_with_paging_hint(monkeypatch):
    fake = [{"name": f"p{i}", "skills": [{"name": f"s{i}", "desc": "d" * 200}]} for i in range(300)]
    monkeypatch.setattr(sm, "_DATA", fake)
    text = sm.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "list", "arguments": {"type": "skills", "limit": 200}}}
                     )["result"]["content"][0]["text"]
    assert len(text) <= 8000
    assert "offset" in text.splitlines()[-1]


def test_ac10_tools_list_small():
    res = sm.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]
    assert len(json.dumps(res)) <= 1500


def test_ec6_missing_snapshot_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "_DATA", None)
    monkeypatch.setattr(sm, "ROOT", str(tmp_path))
    r = sm.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "stats", "arguments": {}}})["result"]
    assert r.get("isError") is True


def test_ec7_unknown_tool_and_bad_json():
    r = sm.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})
    assert r["error"]["code"] == -32602
    out = subprocess.run([sys.executable, os.path.join(ROOT, "snapshot_mcp.py")],
                         input="{bad\n", capture_output=True, text=True, timeout=10).stdout
    assert json.loads(out)["error"]["code"] == -32700


def test_ac13_duplicates_listed(tmp_path):
    recs = [{"name": "p1", "marketplace": "m", "skills": [{"name": "code-review"}]},
            {"name": "p2", "marketplace": "m", "skills": [{"name": "code-review"}]},
            {"name": "p3", "marketplace": "m", "skills": [{"name": "unique"}]}]
    bi.write_duplicates(recs, str(tmp_path))
    text = (tmp_path / "lists" / "duplicates.md").read_text()
    assert "code-review" in text and "p1" in text and "p2" in text and "unique" not in text


def test_ac14_annotations_and_actionable_errors(monkeypatch):
    res = sm.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]
    want = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    assert all(t.get("annotations") == want for t in res["tools"])
    monkeypatch.setattr(sm, "_DATA", [{"name": "p1", "skills": [{"name": "s1"}]}])
    call = lambda n, a: sm.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                  "params": {"name": n, "arguments": a}})["result"]["content"][0]["text"]
    assert "search" in call("get", {"plugin": "nope"})
    assert "fewer" in call("search", {"query": "zzz qqq"})


def test_ac15_external_marketplace_sources(tmp_path, monkeypatch):
    import fetch
    mk = tmp_path / "marketplaces" / "mk" / ".claude-plugin"
    write(str(mk / "marketplace.json"), json.dumps({"plugins": [
        {"name": "ext", "source": {"source": "git-subdir", "url": "https://github.com/o/mono.git",
                                   "path": "plugins/p", "sha": "abc"}},
        {"name": "pkg", "source": {"source": "npm", "package": "x"}},
        {"name": "local", "source": "./plugins/local"}]}))
    srcs = fetch.marketplace_sources(str(tmp_path / "marketplaces"))
    ext = next(s for s in srcs if s["name"] == "ext")
    assert (ext["url"], ext["sha"], ext["subpath"]) == ("https://github.com/o/mono", "abc", "plugins/p")
    assert next(s for s in srcs if s["name"] == "pkg")["url"] is None
    assert not any(s["name"] == "local" for s in srcs)
    repo = tmp_path / "repos" / "o__mono"
    write(str(repo / ".done"), "{}")
    for p in ("p", "q"):
        write(str(repo / f"plugins/{p}/.claude-plugin/plugin.json"), json.dumps({"name": p}))
        write(str(repo / f"plugins/{p}/skills/s{p}/SKILL.md"), f"---\nname: s{p}\n---\n")
    monkeypatch.setattr(bi, "ROOT", str(tmp_path))
    recs = {r["name"]: r for r in bi.external_records(srcs)}
    assert [s["name"] for s in recs["ext"]["skills"]] == ["sp"] and recs["ext"]["marketplace"] == "mk"
    assert recs["pkg"]["fetched"] is False and "npm" in recs["pkg"]["not_fetchable"]


@snapshot
def test_ac1_fetch_log_complete():
    lines = [ln for ln in open(LOG) if ln.startswith("[")]
    assert all(re.search(r"\] \S+ (ok \d+|skip|FAIL .+)$", ln.strip()) for ln in lines)


@snapshot
def test_ac2_only_manifest_files():
    bad = []
    for dirpath, dirs, files in os.walk(os.path.join(ROOT, "repos")):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, "repos"))
            rel = rel.split(os.sep, 1)[1] if os.sep in rel else rel
            if f != ".done" and not bi_want(rel):
                bad.append(rel)
    assert not bad[:5]


def bi_want(rel):
    import fetch
    return bool(fetch.WANT.search(rel)) and "node_modules/" not in rel


@snapshot
def test_ac6_and_ac11_build_outputs_in_time():
    t = time.time()
    subprocess.run([sys.executable, os.path.join(ROOT, "build_index.py")], check=True,
                   capture_output=True, timeout=300)
    assert time.time() - t < 300
    for f in ("agents", "skills", "commands", "tools-mcp", "hooks", "dependencies",
              "fetch-failures", "duplicates"):
        p = os.path.join(ROOT, "lists", f + ".md")
        assert os.path.getsize(p) > 0, p
    assert os.path.getsize(os.path.join(ROOT, "snapshot.json")) > 0


@snapshot
def test_ac12_registered_after_approval():
    out = subprocess.run(["claude", "mcp", "list"], capture_output=True, text=True, timeout=120).stdout
    assert re.search(r"plugin-snapshot.*Connected", out)
