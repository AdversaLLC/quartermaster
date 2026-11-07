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
