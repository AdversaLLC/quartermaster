"""FR-1: deterministic team labels. Each rule is a keyword; the team with the
most keyword hits wins. Every label records the keyword that matched it."""
import re

TEAMS = {
    "security-reverse-eng": "security vulnerab pentest penetration exploit malware reverse decompil disassembl "
                            "ghidra jadx apk frida firmware forensic cve owasp threat secret credential "
                            "crypto audit-security sast fuzz hardening yara",
    "debug": "debug bug fix error stack trace crash failing troubleshoot diagnos root-cause regression",
    "review-verify": "review verify verification test tests testing qa lint quality coverage assert "
                     "acceptance validate check critique",
    "research": "research search find investigate paper literature source citation web-search "
                "analyze compare explore summarize",
    "data-ml": "data dataset sql database pandas ml machine-learning model training llm embedding "
               "rag vector analytics notebook etl pipeline spark statistics",
    "frontend-ui": "frontend ui ux react vue svelte css tailwind html component design figma "
                   "layout accessibility animation web-design",
    "devops-infra": "deploy deployment devops docker kubernetes k8s terraform ci cd infra infrastructure "
                    "cloud aws gcp azure server monitoring release ship publish",
    "docs-writing": "docs documentation readme write writing blog article copy content changelog "
                    "tutorial explain markdown prose",
    "computer-use-browser": "browser chrome playwright puppeteer selenium scrape scraping click "
                            "screenshot automation desktop computer-use",
    "memory-context": "memory context remember recall session handoff knowledge notes token compact",
    "business-ops": "business marketing sales seo finance legal hr product roadmap customer "
                    "email slack jira linear notion crm",
    "build": "build implement feature code coding scaffold refactor api backend app library "
             "plan planning spec architecture",
}
_RULES = {t: kws.split() for t, kws in TEAMS.items()}
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.-]*")


def tokens(text):
    return _TOKEN.findall((text or "").lower())


def _hit(kw, toks, text):
    if "-" in kw:
        return kw in text or kw.replace("-", " ") in text
    return any(t.startswith(kw) for t in toks) if len(kw) >= 5 else kw in toks


def teams_for(text, limit=3):
    """Return up to `limit` (team, rule) pairs, best first; ('general', ...) if none."""
    low = (text or "").lower()
    toks = tokens(low)
    scored = []
    for order, (team, kws) in enumerate(_RULES.items()):
        hits = [kw for kw in kws if _hit(kw, toks, low)]
        if hits:
            scored.append((-len(hits), order, team, hits[0]))
    if not scored:
        return [("general", "no rule matched")]
    scored.sort()
    return [(team, f"keyword '{kw}'") for _, _, team, kw in scored[:limit]]


# ---------- rev 3: task-side team prior (FR-16, FR-18) ----------
# Phrases (weight 3) come only from misses on the dev split of tests/routing_set.json.
PHRASES = {
    "build": "project skeleton|scaffold|clean up|refactor|split it into|smaller functions",
    "debug": "fails randomly|flaky|passes locally|broke after|which commit|bisect",
    "research": "look up|on the web|latest info|web search",
    "security-reverse-eng": "leaked|api keys|passwords|secrets",
    "data-ml": "sql query|classifier|train a|machine learning",
    "devops-infra": "github actions|on every push|ci pipeline",
    "computer-use-browser": "scrape|crawl",
    "business-ops": "ranks on google|seo|invoice|unpaid",
}
_PHRASES = {t: p.split("|") for t, p in PHRASES.items()}
GENERIC = frozenset("find write test tests testing fix check build make set run".split())
NEGATORS = frozenset("not no without don't dont never".split())
MARGIN = 0.2   # FR-17: margin at which confidence reaches 1 (old hard cut-off)


def _negated(toks):
    """Indexes of tokens within 3 words after a negator."""
    out = set()
    for i, t in enumerate(toks):
        if t in NEGATORS:
            out.update(range(i + 1, i + 4))
    return out


def _raw_scores(text):
    low = (text or "").lower()
    toks = tokens(low)
    neg = _negated(toks)
    scores = {}
    for team, kws in _RULES.items():
        s = 0.0
        for i, tok in enumerate(toks):
            hit = any(_hit(kw, [tok], tok) for kw in kws)
            if hit:
                w = 0.5 if tok in GENERIC else 1.0
                s += -2.0 if i in neg else w
        for ph in _PHRASES.get(team, []):
            pos = low.find(ph)
            if pos >= 0:
                start = len(tokens(low[:pos]))
                s += -2.0 if start in neg else 3.0
        scores[team] = s
    return scores


def task_prior(text):
    """FR-16: normalised P(team|task) over positive scores; {} if nothing positive matched."""
    pos = {t: s for t, s in _raw_scores(text).items() if s > 0}
    total = sum(pos.values())
    return {t: s / total for t, s in pos.items()} if total else {}


def confidence(prior):
    """FR-17: clamp((top1 - top2) / MARGIN, 0, 1); 0 with no prior, 1 when one team matches alone."""
    if not prior:
        return 0.0
    ranked = sorted(prior.values(), reverse=True) + [0.0]
    return max(0.0, min(1.0, (ranked[0] - ranked[1]) / MARGIN))
