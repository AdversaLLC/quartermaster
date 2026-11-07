"""Tests for qm_prompts.py (FR-22, EC-10, EC-11). Synthetic fixtures only; no network."""
import builtins
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import qm_prompts as qp  # noqa: E402

URL = "https://example.invalid/acme/prompts"


@pytest.fixture(autouse=True)
def no_processes(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("tests must not launch processes")
    monkeypatch.setattr(subprocess, "run", refuse)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())


@pytest.fixture
def data_dir(tmp_path):
    (tmp_path / "prompt_sources.json").write_text(json.dumps([URL]))
    repo = tmp_path / "prompt_repos" / "acme__prompts"
    _write(str(repo / "vendor" / "assistant.md"), "Fake  prompt\n\n one. " + "x" * 400)
    _write(str(repo / "plain"), "extensionless fake prompt")
    _write(str(repo / "notes.txt"), "short")
    _write(str(repo / "big.txt"), "y" * (qp.MAX_BYTES + 1))
    _write(str(repo / "blob.md"), b"abc\x00def")
    _write(str(repo / "image.png"), b"\x89PNG")
    _write(str(repo / "README.md"), "readme")
    _write(str(repo / "LICENSE"), "license")
    _write(str(repo / ".git" / "config"), "git internals")
    return tmp_path


def test_fr22_absent_config_returns_empty(tmp_path):
    assert qp.load_sources(str(tmp_path)) == []
    assert qp.records(str(tmp_path)) == []


def test_fr22_record_shape(data_dir):
    [rec] = qp.records(str(data_dir))
    for key in ("skills", "agents", "commands", "mcp", "hooks"):
        assert rec[key] == []
    assert rec["name"] == "acme__prompts" and rec["repo"] == URL
    assert rec["summary"] == "prompt library" and rec["fetched"] is True
    assert rec["subpath"] == "" and rec["deps"] == {}
    names = sorted(p["name"] for p in rec["prompts"])
    assert names == ["notes", "plain", os.path.join("vendor", "assistant")]
    for p in rec["prompts"]:
        assert set(p) == {"name", "desc", "path"}


def test_fr22_excerpt_capped_and_collapsed(data_dir):
    [rec] = qp.records(str(data_dir))
    for p in rec["prompts"]:
        assert len(p["desc"]) <= 200
    first = next(p for p in rec["prompts"] if p["name"].endswith("assistant"))
    assert first["desc"].startswith("Fake prompt one. x") and len(first["desc"]) == 200


def test_ec11_oversize_binary_readme_skipped_and_listed(data_dir):
    [rec] = qp.records(str(data_dir))
    reasons = {s["path"]: s["reason"] for s in rec["skipped"]}
    assert reasons["big.txt"] == "over 200 KB"
    assert reasons["blob.md"] == "binary"
    assert reasons["image.png"] == "not text"
    assert reasons["README.md"] == reasons["LICENSE"] == "readme/license"
    assert not any(p.startswith(".git") for p in reasons)


def test_ec10_missing_repo_noted(tmp_path):
    (tmp_path / "prompt_sources.json").write_text(json.dumps([URL]))
    [rec] = qp.records(str(tmp_path))
    assert rec["missing"] is True and rec["fetched"] is False and rec["prompts"] == []


def test_ec10_fetch_failure_warns_and_returns_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qp, "_git", lambda argv: (False, "network down"))
    assert qp.fetch(URL, str(tmp_path)) is None
    assert "unreachable" in capsys.readouterr().err


def test_fetch_uses_list_argv_clone_then_pull(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(qp, "_git", lambda argv: (calls.append(argv), (True, ""))[1])
    dest = qp.fetch(URL, str(tmp_path))
    assert calls[-1][:4] == ["git", "clone", "--depth", "1"]
    os.makedirs(os.path.join(dest, ".git"))
    qp.fetch(URL, str(tmp_path))
    assert calls[-1][:4] == ["git", "-C", dest, "pull"]


@pytest.mark.parametrize("bad", ["http://h/a/b", "https://h/../..", "https://h/a/b;rm",
                                 "git@github.com:a/b"])
def test_fetch_rejects_unsafe_urls(tmp_path, bad):
    assert qp.slug(bad) is None
    assert qp.fetch(bad, str(tmp_path)) is None


def test_records_never_reads_outside_data_dir(data_dir, tmp_path_factory, monkeypatch):
    outside = tmp_path_factory.mktemp("outside")
    secret = outside / "secret.md"
    secret.write_text("outside text")
    repo = data_dir / "prompt_repos" / "acme__prompts"
    os.symlink(str(secret), str(repo / "link.md"))
    os.symlink(str(outside), str(repo / "linkdir"))
    real_open, base = builtins.open, os.path.realpath(str(data_dir))
    opened = []

    def spy(path, *a, **k):
        opened.append(os.path.realpath(path))
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", spy)
    [rec] = qp.records(str(data_dir))
    assert opened and all(p.startswith(base + os.sep) for p in opened)
    assert {"path": "link.md", "reason": "symlink"} in rec["skipped"]
    assert all("outside" not in p["desc"] for p in rec["prompts"])
