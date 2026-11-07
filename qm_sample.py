"""FR-21: sample real first-turn user prompts from SALT-NLP/SWE-chat (ODC-BY).

Stdlib only. Reads rows through the Hugging Face datasets-server /filter API.
The dataset is gated: accept its terms on huggingface.co, then export HF_TOKEN.
Writes ONLY <out_dir>/real_tasks_raw.jsonl. Stats go to stdout.
"""
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://datasets-server.huggingface.co/filter"
DATASET = "SALT-NLP/SWE-chat"
WHERE = "\"turn_type\"='user_prompt' AND \"is_first_turn\"=true"
PAGE = 100
OUT_NAME = "real_tasks_raw.jsonl"

SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[abprs]-"
    r"|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY"
    r"|\b(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S+"
    r"|\b[A-Za-z0-9+/_-]{40,}\b)", re.I)
TOKEN_URL = re.compile(
    r"https?://[^\s]*([?&](token|key|sig|signature|access_token|auth|code)=|//[^/\s]+:[^/\s]+@)", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
HOME_PATH = re.compile(r"(/home/[^/\s]+|/Users/[^/\s]+|[A-Za-z]:\\Users\\|/root/)")


def fetch_page(offset, length=PAGE):
    """Return one page of first-turn user-prompt rows (list of dicts)."""
    query = urllib.parse.urlencode({"dataset": DATASET, "config": "conversations",
                                    "split": "train", "where": WHERE,
                                    "offset": offset, "length": length})
    req = urllib.request.Request(f"{API}?{query}")
    token = os.environ.get("HF_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return [r["row"] for r in data.get("rows", [])]


def fetch_rows(max_rows, fetch=fetch_page):
    """Page through the API until max_rows rows or an empty page."""
    rows = []
    while len(rows) < max_rows:
        page = fetch(len(rows))
        if not page:
            break
        rows.extend(page)
    return rows[:max_rows]


def is_english(row, text):
    """Trust the dataset's language tag when present; else mostly-ASCII letters."""
    lang = row.get("language")
    if lang:
        return lang == "en"
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) > 0.95


def reject_reason(row):
    """Return the name of the first failing filter, or None if the row is kept."""
    text = (row.get("content") or "").strip()
    words = len(text.split())
    if row.get("is_continuation") or not (6 <= words <= 60):
        return "length"
    if not is_english(row, text):
        return "language"
    if TOKEN_URL.search(text) or SECRET.search(text):
        return "secret"
    if EMAIL.search(text):
        return "email"
    if HOME_PATH.search(text):
        return "home_path"
    return None


def clean(rows):
    """Apply filters and dedupe; return (sorted unique texts, drop counts)."""
    drops = {"length": 0, "language": 0, "secret": 0, "email": 0, "home_path": 0, "duplicate": 0}
    seen = {}
    for row in rows:
        reason = reject_reason(row)
        if reason:
            drops[reason] += 1
            continue
        text = " ".join(row["content"].split())
        key = text.lower()
        if key in seen:
            drops["duplicate"] += 1
            continue
        seen[key] = text
    return sorted(seen.values()), drops


def sample(out_dir, n=150, seed=20261107, max_rows=3000, fetch=fetch_page):
    """Download, filter, dedupe, sample n with seed; write out_dir/real_tasks_raw.jsonl."""
    rows = fetch_rows(max_rows, fetch)
    texts, drops = clean(rows)
    picked = random.Random(seed).sample(texts, min(n, len(texts)))
    path = os.path.join(out_dir, OUT_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        for text in picked:
            fh.write(json.dumps({"task": text}, ensure_ascii=False) + "\n")
    return {"fetched": len(rows), "kept": len(texts), "written": len(picked),
            "drops": drops, "path": path}


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 150
    out_dir = os.environ.get("QM_DATA") or os.path.dirname(os.path.abspath(__file__))
    try:
        print(json.dumps(sample(out_dir, n), indent=1))
    except urllib.error.HTTPError as err:
        sys.exit(f"qm_sample: {DATASET} fetch failed ({err}). The dataset is gated: accept its "
                 "terms on huggingface.co, then export HF_TOKEN from that account.")


if __name__ == "__main__":
    main(sys.argv)
