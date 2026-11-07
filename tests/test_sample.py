"""AC-16 (FR-21): sampler writes only into the data dir, filters, and is seeded."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import qm_sample  # noqa: E402

GOOD = [f"please add a retry option number {i} to the http client module" for i in range(40)]
BAD = {
    "length": "fix it",
    "language": "por favor corrige el error en el módulo de pagos ahora mismo",
    "secret": "use this key sk-abcdefghijklmnopqrstuvwx to call the api and test it",
    "token_url": "fetch https://example.com/data?token=abc123 and parse the json for me",
    "email": "send the report to someone@example.com when the build is finished ok",
    "home_path": "open /home/alice/project/main.py and refactor the parser into modules",
}


def fake_rows():
    rows = [{"content": t, "language": "en"} for t in GOOD]
    rows += [{"content": GOOD[0], "language": "en"}]  # duplicate
    for key, text in BAD.items():
        rows.append({"content": text, "language": "es" if key == "language" else "en"})
    return rows


def fake_fetch(offset, length=qm_sample.PAGE):
    return fake_rows()[offset:offset + length]


def snapshot(root):
    out = set()
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".pytest_cache", ".git")]
        out.update(os.path.join(d, f) for f in files)
    return out


def read(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line)["task"] for line in fh]


def test_writes_only_into_out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(qm_sample, "fetch_page", fake_fetch)
    before = snapshot(ROOT)
    res = qm_sample.sample(str(tmp_path), n=10, fetch=fake_fetch)
    assert sorted(os.listdir(tmp_path)) == ["real_tasks_raw.jsonl"]
    assert res["path"] == str(tmp_path / "real_tasks_raw.jsonl")
    assert snapshot(ROOT) == before


def test_filters_and_dedupe(tmp_path):
    res = qm_sample.sample(str(tmp_path), n=1000, fetch=fake_fetch)
    tasks = read(res["path"])
    assert sorted(tasks) == sorted(GOOD)
    d = res["drops"]
    assert (d["length"], d["language"], d["secret"], d["email"], d["home_path"], d["duplicate"]) \
        == (1, 1, 2, 1, 1, 1)


def test_deterministic_for_seed(tmp_path):
    a, b, c = (tmp_path / x for x in "abc")
    for p in (a, b, c):
        p.mkdir()
    qm_sample.sample(str(a), n=10, seed=7, fetch=fake_fetch)
    qm_sample.sample(str(b), n=10, seed=7, fetch=fake_fetch)
    qm_sample.sample(str(c), n=10, seed=8, fetch=fake_fetch)
    ra, rb, rc = (read(str(p / "real_tasks_raw.jsonl")) for p in (a, b, c))
    assert ra == rb and len(ra) == 10
    assert ra != rc
