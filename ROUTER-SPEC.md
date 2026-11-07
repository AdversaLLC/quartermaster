# Quartermaster Router MCP — Specification

**Author:** Claude (for the user)
**Date:** 2026-11-07
**Status:** Rev 2 — built and released as v0.1.0. Rev 3 (section at the end) — draft, awaiting approval
**Reviewers:** the user; DeepSeek second opinion (log: `~/.claude/call-a-friend/2026-11-07T14-39-18-deepseek-browser-router-spec.md`)
**Builds on:** `SPEC.md` (plugin snapshot, approved). Rev 1 kept as `ROUTER-SPEC.rev1.md`.

## Context

The plugin snapshot holds 3,878 plugins: 21,097 skills, 2,755 agents, 3,632 commands and 2,391 MCP
servers. The user wants to describe a task once and get back a carved-out map from a single MCP: the
team that fits, the exact components each workflow step needs ("quartermaster": only what that team
needs, nothing loaded up front), and where to stop for a second opinion via `/call-a-friend`.
Every component is risk-screened before it can be recommended. The result ships as an open-source,
one-shot tool. Token economy is a hard goal.

### What rev 2 changed, and why

DeepSeek's review (prior art: ToolRet shows even strong retrievers score low on tool retrieval;
fixed top-5 shortlists miss hard queries) led to these changes. Each one was checked or reasoned
against this machine; the cited outside projects are unverified leads, not dependencies.

- Retrieval is BM25 over component text, not keyword rules alone (FR-2). Rules stay as team labels and boosts.
- Teams are soft labels with a primary team for display, not one hard bucket (FR-1).
- The audit grade is renamed **declared risk**: it says what the files declare, never "safe" (FR-3).
  Signals added after measuring the snapshot: 17 SKILL.md files contain hidden bidi or zero-width
  characters, 37 plugins have `postinstall` scripts, 8 declare monitors, 2,837 skills set `allowed-tools`.
- Shortlist depth adapts to the score gap, and stations without good matches are skipped (FR-5).
- A labeled routing set and a keyword-rules baseline are required before AC-3 counts (NFR-6).
- IDs are `name@plugin` everywhere (FR-14). Vague tasks return a clarifying question (FR-13).

## Functional Requirements

- FR-1: The indexer MUST give every agent, skill, command and MCP server a primary team from a fixed taxonomy of 12 (build, debug, review-verify, research, security-reverse-eng, data-ml, frontend-ui, devops-infra, docs-writing, computer-use-browser, memory-context, business-ops), plus up to 2 secondary teams, each with the keyword rule that matched. Components matching no rule get team `general`.
- FR-2: The router MUST rank components with BM25 over name, description and plugin summary, boosted by: exact name-token match, team agreement with the task, and installed status. Ranking MUST be deterministic.
- FR-3: The auditor MUST give every fetched plugin a declared-risk grade A–D with reasons, reading files only: hook commands, `.mcp.json`/plugin MCP entries, SKILL.md/agent/command text, and `package.json` scripts. Signals: pipe to shell; `sudo`; `curl`/`wget` in hooks; `base64`/`eval` decode-and-run; hooks on every tool call (`PreToolUse`/`PostToolUse` with no or `*` matcher); MCP env keys that request credentials; remote MCP URLs (plain `http://` graded worse than `https://`); unpinned `npx … @latest`; `postinstall`/`preinstall` scripts; monitors; hidden bidi/zero-width characters in instruction text; `allowed-tools` granting unrestricted `Bash`. Grade A means "nothing risky declared", never "safe".
- FR-4: The auditor MUST NOT execute any plugin code.
- FR-5: `route(task)` MUST return the primary team, then the workflow stations discuss → plan → execute → verify → ship, keeping only stations with at least one match. Each station lists 1–5 items by default; the cut is where the score drops below 50% of the station's best. `depth: "deep"` raises the cap to 10.
- FR-6: Each kit item MUST show its `name@plugin` ID, kind, installed yes/no, dependencies, grade, and a one-line reason.
- FR-7: Every route MUST include call-a-friend checkpoints: after plan, before hard-to-undo steps, after two failed attempts, and before done, each with an asked-vs-planned brief template. "Hard to undo" means deleting or overwriting data, deploying or publishing, pushing to a shared remote, spending money, or using credentials.
- FR-8: The router MUST NOT call any outside model or network service. Brief templates MUST NOT include file paths, environment values or secrets.
- FR-9: By default only grades A and B are recommended. `allow_risky: true` admits C and D with a warning per item. Unaudited components are never recommended.
- FR-10: Installed components SHOULD rank above uninstalled ones of near-equal score.
- FR-11: The repository MUST ship a LICENSE, README, NOTICE, tests with synthetic fixtures only, and a rebuild script. It MUST NOT ship `repos/`, `snapshot.json` or the built index, and MUST NOT imply endorsement by Anthropic.
- FR-12: `explain(id)` MUST return the component's teams with matched rules, grade and audit reasons.
- FR-13: If the best BM25 score is below a confidence floor, `route` MUST return a clarifying question plus the `review-verify` + `research` default workflow, and say so.
- FR-14: Component IDs MUST be `name@plugin` in every input and output. A bare name resolves to the best-graded installed copy, and the response says which copy was picked.

## Non-Functional Requirements

- NFR-1: The router's `tools/list` MUST stay ≤ 1,500 characters.
- NFR-2: A `route` response MUST be ≤ 4,000 characters, using one compact line per kit item.
- NFR-3: `route` MUST answer in < 1 s, using a precomputed index loaded once.
- NFR-4: Standard library only, no network at serve time.
- NFR-5: At least 80% of agents MUST get a primary team other than `general`.
- NFR-6: A labeled routing set of at least 30 tasks MUST exist. BM25 routing MUST beat the keyword-rules-only baseline on Recall@5, and both numbers MUST be reported. The labels were written by Claude, so they are a sanity check, not a benchmark.

## Acceptance Criteria

### AC-1: (FR-1, NFR-5)
Given the snapshot, When teams are built, Then every component has a primary team and matched rule (or `general`), and at least 80% of agents are not `general`.

### AC-2: (FR-3, FR-4)
Given synthetic fixture plugins, When audited, Then: a hook running `curl x | sh` grades D with "pipe to shell"; a `postinstall` script grades at least C; a SKILL.md with a U+202E character grades at least C with "hidden unicode"; a plain plugin grades A; and no subprocess is spawned.

### AC-3: (FR-5, FR-6, NFR-2, NFR-3)
Given the task "decompile this APK and find the API keys", When `route` is called, Then the team is `security-reverse-eng`, each station lists 1–5 items with all FR-6 fields, the response is ≤ 4,000 characters, and it returns in under 1 s.

### AC-4: (FR-10, FR-14)
Given two components of equal score where one is installed, Then the installed one ranks first, and every ID in the output has the form `name@plugin`.

### AC-5: (FR-7, FR-8)
Given any route, Then checkpoints after-plan, before-irreversible, after-two-failures and before-done are present, and no brief contains `/home/` or `=`-style env values.

### AC-6: (FR-9)
Given a C-graded best match, When routed normally it is excluded; with `allow_risky: true` it is included with a warning.

### AC-7: (FR-11)
Given the package file list, Then LICENSE, README, NOTICE, tests and the rebuild script are present, and `repos/`, `snapshot.json` and the index are excluded by `.gitignore`.

### AC-8: (FR-12)
Given an ID, When `explain` is called, Then it returns teams, rules, grade and reasons.

### AC-9: (FR-13)
Given the task "asdf qwerty", When routed, Then it returns a clarifying question and the default workflow.

### AC-10: (NFR-6)
Given the labeled set, When evaluated, Then BM25 Recall@5 > rules-only Recall@5, and both are printed.

## Edge Cases

- EC-1: No team matches → `general` team, default workflow (FR-13).
- EC-2: Duplicate names (1,583) → FR-14 resolution.
- EC-3: Plugin not fetched (25 repos) or no files found → grade `unaudited`, never recommended.
- EC-4: Index missing or older than `snapshot.json` → error naming the rebuild command.
- EC-5: call-a-friend unavailable → checkpoint brief still produced; Claude reports the second opinion was skipped.

## API Contracts

stdio MCP (JSON-RPC 2.0), server name `quartermaster`:

```ts
interface RouteIn   { task: string; allow_risky?: boolean; depth?: "normal" | "deep"; }
interface ExplainIn { id: string; }   // name@plugin, or a bare name (FR-14)
```

`route` returns compact text: a header line (team, confidence), then per station
`## <station>` with one line per item: `id | kind | inst y/n | grade | deps | why`, then checkpoints.

## Data Models

`qm_index.json` (built, not shipped): components `[{id, kind, name, plugin, desc, teams:[[team, rule]], grade, tokens}]`, plugin audits `{plugin: {grade, reasons}}`, BM25 stats `{df, avgdl, N}`, and `built_from` = `snapshot.json` mtime.

## Out of Scope

- OS-1: Installing plugins. OS-2: Calling DeepSeek from the MCP. OS-3: LLM-based auditing.
- OS-4: Proxying calls to underlying MCP servers. OS-5: Embeddings (they would break NFR-4).
- OS-6: Adaptive depth beyond the score-gap rule (search-based depth is a later step).

---

# Rev 3 — Team routing, real eval tasks, prompt library (draft, awaiting approval)

Basis: two DeepSeek reviews on 2026-11-07 (`~/.claude/call-a-friend/*team-routing.md`,
`*rev3-evalsources.md`). Checked on this machine: 12 holdout tasks give ±28 pp, so pass/fail
gates on them are meaningless; `SALT-NLP/SWE-chat` (ODC-BY) and `hao-li/AIDev` (CC-BY-4.0) exist
on Hugging Face; SWE-bench Verified shows no license tag (unverified).

## Purpose
Raise team-pick accuracy (0.58, n=36) without lowering retrieval, measure it on real user
phrasing instead of self-written tasks, and let the router recommend tested system prompts from a
user-chosen prompt library where they fit.

## Inputs
| Input | Type | Required | Constraints | Default |
|---|---|---|---|---|
| task | string | yes | non-empty after strip | — |
| team rule | (phrase, weight) | — | weight in {0.5, 1, 3, -2}; 0.5 = generic verbs (find, write, test, fix) | — |
| synonym map | term -> [terms] | — | ≤ 15 entries; each fixes ≥ 2 dev misses | empty |
| `prompt_sources.json` (data dir) | list of git URLs | no | user-local, never committed | absent = feature off |
| real eval tasks | `tests/real_tasks.jsonl` in the data dir | no | from SWE-chat user prompts, never committed | — |

## Functional Requirements
- FR-15: Eval sets carry `split` (dev/holdout), chosen by a seeded stratified random split (seed recorded). `qm_eval.py` reports each metric with a 95% Wilson interval and, between two runs, a paired comparison (McNemar exact). Tuning uses dev only.
- FR-16: The rule classifier returns normalised team scores. Negative phrases subtract before normalising. Confidence = top1 − top2 margin; below 0.2 (calibrated on dev) the task is low-confidence.
- FR-17: Score per query (rev 3.1, after DeepSeek review 2026-11-07): `bm25n = bm25 / max bm25` (0 if max is 0); `name_n = rare name hits (max 3) / 3`; `conf = clamp((top1 - top2) / 0.2, 0, 1)` from the task prior (0 if no prior; a single matching team gives margin 1); `team_n = (P(primary) + 0.5 * max P(secondary)) / 1.5`, and `general` components get `0.5 * max P / 1.5`; `score = bm25n + 0.15 * name_n + W * conf * team_n`. Installed is a tie-break only: sort key `(-score, not installed, id)`. Each step keeps rank 1, then items with score ≥ 50% of the best, at most 5 (10 with `deep`). `W` is swept over {0.05, 0.1, 0.15, 0.2, 0.3} on dev only; the baseline is the old formula (rev 3.0, W = 3), saved as `eval_runs/dev-oldformula-W3.json`; the new formula replaces it at the midpoint of its flat region, and it is reported with an exact McNemar p against the baseline (p < 0.05 needs ≥ 6 one-way discordant tasks of 24).
- FR-18: Weighted phrase rules as in the Inputs table.
- FR-19: Synonym map expands task text for team scoring only, adding to (not replacing) original matches.
- FR-20: `explain` shows the component's team prior value for a given task when called with `task`.
- FR-21: Real eval tasks: a script samples about 150 user prompts from SWE-chat into the data dir. They are labelled with a team and expected component substrings before the router is run on them. Neither the prompts nor the labels are committed (attribution noted in NOTICE).
- FR-22: Prompt library: when `prompt_sources.json` exists, the rebuild clones those repos into `prompt_repos/` (data dir, gitignored) and indexes each prompt file as kind `prompt` with id `file@repo`, team labels and a 200-char excerpt. Prompts compete in the `plan` and `execute` stations like other components, grade `A` (text only, nothing runs). Route lines show the id and local path, never the full text. No prompt text is shipped in the repo, tests or release.

- FR-23: Tool links: when `<data_dir>/tool_links.json` exists (list of `{name, url, desc}`, desc ≤ 200 chars in our own words), each entry is indexed as kind `link` with id `name@links`, grade `B` (reason: "external link; nothing fetched or run"). Links compete in `execute`; the route line shows the URL as the reason. The file is user-local and never committed.

## Edge Cases
| Case | Expected |
|---|---|
| EC-6: two teams tie | Low confidence: `team: unknown (derived)`, pure BM25 |
| EC-7: only negative phrases match | All P = 0 (pure BM25); reason shown in header |
| EC-8: synonym maps to two teams | Its weight splits equally; original matches still count |
| EC-10: prompt source unreachable | Rebuild warns and continues; index notes the source as missing |
| EC-11: prompt file not text or > 200 KB | Skipped and listed |

## Acceptance Criteria
- AC-11 (FR-15): `qm_eval.py` prints Wilson intervals and a McNemar p-value between baseline and candidate; the baseline run is saved before any rev 3 change.
- AC-12 (FR-17): synthetic fixture with fixed BM25 scores: an off-team component scoring 10.0 beats an on-team one scoring 6.0 with W = 3 and P = 1.0.
- AC-13 (FR-16, EC-6, EC-7): synthetic tie returns `unknown (derived)`; a negatives-only task yields pure BM25 ranking.
- AC-14 (FR-17): a `general` component gets the neutral boost (fixture with exact expected value).
- AC-15 (FR-20): `explain(id, task)` prints the expected prior value for a fixture.
- AC-16 (FR-21): the sampler writes only into the data dir; a test asserts no file under the repo tree is created.
- AC-17 (FR-22): with a fixture prompt repo, a matching task routes `file@repo` into `execute`; the route text never contains more than the 70-char excerpt; `git ls-files` contains no prompt text.
- AC-18 (FR-23): with a fixture `tool_links.json`, an encoding task routes `name@links` into `execute` and the line contains its URL; without the file, no `link` components exist.
- Release gate: on real tasks, candidate vs baseline team accuracy is reported with intervals; a change ships only if McNemar p < 0.05 or retrieval Recall@5 does not drop. All rev 2 tests still pass.

## Explicitly Excluded
- Using leaked vendor prompts as eval tasks (vendor wording, not user phrasing; AGPL text cannot enter the MIT repo).
- A trained classifier; BM25 query expansion (RM3); BM25F / `b` tuning (later, dev only).
- Shipping or summarising prompt-library content in the public repo.
