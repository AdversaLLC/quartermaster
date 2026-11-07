# Quartermaster Router MCP — Specification

**Author:** Claude (for the user)
**Date:** 2026-11-07
**Status:** Draft — awaiting user approval
**Reviewers:** the user
**Builds on:** `SPEC.md` (plugin snapshot, approved)

## Context

The plugin snapshot holds 3,878 plugins: 21,097 skills, 2,755 agents, 3,632 commands and 2,391 MCP
servers. Today Claude has to know what to ask for. The user wants the reverse: describe the task
once, and a single MCP hands back a carved-out map. That map should say which team of agents fits
the task, which exact skills and tools each step needs ("quartermaster": only what that team needs,
nothing loaded up front), and where in the workflow to stop and get a second opinion from an outside
model through `/call-a-friend` (DeepSeek). The second opinion covers both review and research.

The user also wants every skill and MCP audited before it can be recommended. The result should be
shippable as an open-source, one-shot tool: "ship anything out of everything".

Token economy is a hard goal. The router returns names and one-line reasons; full detail is fetched
only on demand. No skill is loaded until a step needs it.

## Functional Requirements

- FR-1: The indexer MUST assign every agent and skill to exactly one primary team from a fixed taxonomy of 12 teams: build, debug, review-verify, research, security-reverse-eng, data-ml, frontend-ui, devops-infra, docs-writing, computer-use-browser, memory-context, business-ops.
- FR-2: Team assignment MUST be deterministic (keyword and field rules) and MUST record which rule matched, so any assignment can be explained.
- FR-3: The auditor MUST give every plugin a static risk grade (A to D) from its fetched manifests, with the reasons. Signals: shell pipes to `sh`, `sudo`, `curl`/`wget` in hooks, `base64`/`eval`, hooks that run on every tool call, MCP env keys that request credentials, remote MCP URLs, and unpinned `npx … @latest`.
- FR-4: The auditor MUST NOT execute any plugin code; the audit reads manifests only.
- FR-5: The router MUST expose a `route` tool. Given a task description, it returns the team, an ordered workflow (discuss → plan → execute → verify → ship), and, for each station, at most 5 recommended skills, agents or tools with one-line reasons.
- FR-6: Each `route` result MUST include a "kit" per station: the exact component names, whether each is installed locally, its install dependencies, and its risk grade.
- FR-7: The router MUST mark call-a-friend checkpoints in the workflow: after the plan is written, before any hard-to-undo step, after two failed attempts, and before declaring done. Each checkpoint MUST include a ready-to-send brief comparing what the user asked for with what Claude plans to do.
- FR-8: The router MUST NOT call any outside model or network service itself. Checkpoints are instructions for Claude to run `/call-a-friend` (which scrubs and logs).
- FR-9: By default the router MUST only recommend components graded A or B. C and D appear only when asked for explicitly, with a warning.
- FR-10: The router SHOULD prefer components that are already installed over ones that are not.
- FR-11: The project MUST be packaged as an open-source repository: license, README, tests, and a script that rebuilds the snapshot locally. Fetched third-party plugin content MUST NOT be redistributed, because its licenses vary.
- FR-12: The router MAY expose `explain(component)` to show why a component was routed (team rule plus audit reasons).

## Non-Functional Requirements

- NFR-1: The router's `tools/list` MUST stay ≤ 1,500 characters.
- NFR-2: A `route` response MUST be ≤ 4,000 characters.
- NFR-3: `route` MUST answer in < 1 s on this machine, using a precomputed index.
- NFR-4: The router MUST use only the standard library, with no network at serve time.
- NFR-5: The team taxonomy MUST classify ≥ 90% of agents into a team other than a catch-all, measured on the snapshot.

## Acceptance Criteria

### AC-1: (FR-1, FR-2, NFR-5)
Given the snapshot, When teams are built, Then every agent and skill has exactly one team and a matched rule, and at least 90% of agents are outside the catch-all.

### AC-2: (FR-3, FR-4)
Given a fixture plugin whose hook runs `curl x | sh`, When audited, Then it is graded D with the reason "pipe to shell", and no process is spawned.

### AC-3: (FR-5, NFR-2, NFR-3)
Given the task "decompile this APK and find the API keys", When `route` is called, Then the team is `security-reverse-eng`, the workflow has 5 stations, each station lists at most 5 items, the response is at most 4,000 characters, and it returns in under 1 s.

### AC-4: (FR-6, FR-10)
Given a route result, When inspected, Then every kit item shows installed yes/no, its dependencies and its grade, and installed items rank above uninstalled ones of equal score.

### AC-5: (FR-7, FR-8)
Given any route result, When inspected, Then call-a-friend checkpoints appear after plan, before hard-to-undo steps and before done, each with an asked-vs-planned brief, and the server made no network call.

### AC-6: (FR-9)
Given a C-graded component that matches best, When `route` is called normally, Then it is excluded; When called with `allow_risky: true`, Then it is included with a warning.

### AC-7: (FR-11)
Given the packaged repository, When its file list is checked, Then a license, README, tests and rebuild script are present, and no fetched `repos/` content is included.

### AC-8: (FR-12)
Given a component name, When `explain` is called, Then it returns the team rule and the audit reasons.

## Edge Cases

- EC-1: The task matches no team → return a `review-verify` + `research` default workflow, and say so.
- EC-2: A component appears in several plugins (1,583 duplicate names) → recommend the copy with the best grade that is installed.
- EC-3: A plugin wasn't fetched (25 repos) → its grade is "unaudited" and it is never recommended by default.
- EC-4: The snapshot is missing or stale → return an error naming the rebuild command.
- EC-5: DeepSeek or call-a-friend is unavailable → the checkpoint brief is still produced, and Claude reports that the second opinion was skipped.

## API Contracts

N/A for HTTP: this is a stdio MCP (JSON-RPC 2.0). The tools are:

```ts
interface RouteIn  { task: string; allow_risky?: boolean; }
interface KitItem  { name: string; kind: "skill"|"agent"|"command"|"mcp"; plugin: string;
                     why: string; installed: boolean; deps: string[]; grade: "A"|"B"|"C"|"D"|"unaudited"; }
interface Station  { name: "discuss"|"plan"|"execute"|"verify"|"ship"; kit: KitItem[] /* ≤5 */;
                     checkpoint?: { when: string; brief: string } /* call-a-friend */; }
interface RouteOut { team: string; matched_rule: string; stations: Station[]; notes: string[]; }
interface ExplainIn { component: string; }
interface ExplainOut { team: string; rule: string; grade: string; reasons: string[]; }
```

## Data Models

| Entity | Field | Type | Constraints |
|---|---|---|---|
| TeamIndex | component | string | unique name@plugin |
| TeamIndex | team | enum (12) | required |
| TeamIndex | rule | string | the keyword/field rule that matched |
| Audit | plugin | string | unique |
| Audit | grade | A, B, C, D, unaudited | required |
| Audit | reasons | string[] | empty only for grade A |
| Installed | name | string | from `~/.claude/plugins/installed_plugins.json` and the skills dirs |

## Out of Scope

- OS-1: Installing any plugin automatically. The router recommends; the user or Claude installs on request.
- OS-2: Calling DeepSeek from inside the MCP. That stays in `/call-a-friend`, which already scrubs and logs.
- OS-3: LLM-based auditing of 30,000 components. The audit is static and deterministic; an LLM review is a per-plugin follow-up.
- OS-4: Proxying calls to the underlying MCP servers, as in SPEC.md OS-2.
- OS-5: Computer-use and browser execution itself. The router only routes to those skills.
