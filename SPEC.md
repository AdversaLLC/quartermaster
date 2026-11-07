# Plugin Snapshot MCP — Specification

**Author:** Claude (for the user)  
**Date:** 2026-11-07  
**Status:** Approved (2026-11-07, by the user)  
**Reviewers:** the user  
**Location:** `~/Projects/plugin-snapshot/`

> **Honesty note:** FR-1 to FR-6 were implemented *before* this spec (`fetch.py`,
> `build_index.py`, `snapshot_mcp.py`). For those, this document is post-hoc
> documentation plus acceptance tests still to be written. FR-7 to FR-9 are
> unbuilt and gated on approval.

## Context

The plugin browser lists ~3,773 plugins across the Anthropic Directory (3,602
listings, 3,217 GitHub repos) and the locally cloned marketplaces. Each plugin bundles
some mix of skills, agents, slash commands, hooks and MCP servers. Nobody can see across
all of them: what kinds of component exist, which plugins duplicate each other, and what
each one needs installed.

The user asked to "put them all in an MCP format first, get them all, organise them —
every single one — sort between agents, skills, tools and list install dependencies",
and explicitly: **do not install them; compile a local snapshot and work from there.**

A secondary goal is token economy (the user's tokencut toolkit): one small MCP surface
that can answer questions about thousands of components without loading thousands of
descriptions into context.

## Functional Requirements

- FR-1: The fetcher MUST retrieve every repo referenced by `plugin-directory-cache-v2.json` at its `reviewed_commit`. *(built before spec)*
- FR-2: The fetcher MUST check out only manifest and dependency files (`plugin.json`, `marketplace.json`, `.mcp.json`, `SKILL.md`, `agents/*.md`, `commands/*.md`, `hooks.json`, `package.json`, `requirements*.txt`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Dockerfile`). *(built before spec)*
- FR-3: The system MUST NOT install, build, or execute any fetched code. *(built before spec)*
- FR-4: The indexer MUST classify every component into exactly one of: `agents`, `skills`, `commands`, `hooks`, `mcp` (tools). *(built before spec)*
- FR-5: The indexer MUST record per plugin: npm/pip/cargo/go/docker packages, MCP runtimes (node, python/uvx, docker, remote-http, other binary) and MCP env-var names (never values). *(built before spec)*
- FR-6: The indexer MUST write `snapshot.json` and `lists/{agents,skills,commands,tools-mcp,hooks,dependencies}.md`. *(built before spec)*
- FR-7: The indexer MUST write `lists/fetch-failures.md` listing every repo that failed to fetch, with the reason. *(not built)*
- FR-8: A single stdio MCP server MUST expose exactly four read-only tools: `stats`, `list`, `search`, `get`. *(built before spec)*
- FR-9: Every MCP tool response MUST be capped at 8,000 characters and say how to page or narrow when truncated. *(not built)*
- FR-10: The server SHOULD be registered in Claude Code user config only after the user approves. *(not built)*
- FR-11: The indexer MAY flag duplicate component names across plugins.
- FR-12: Every MCP tool MUST declare annotations `readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false`, and empty results MUST suggest a next step. *(added 2026-11-07 after mcp-builder review)*
- FR-13: Marketplace entries whose source is `url` or `git-subdir` MUST be fetched like directory repos (pinned `sha` when given, else default branch) and indexed as their own records; `npm` and `command` sources MUST be listed as not fetchable. *(added 2026-11-07 — 70 plugins were missing)*

## Non-Functional Requirements

- NFR-1: The `tools/list` response MUST be ≤ 1,500 characters (≈ 400 tokens).
- NFR-2: Rebuilding the index from local files MUST finish in < 300 s.
- NFR-3: The server MUST use only the Python standard library and make no network calls.
- NFR-4: No secret value MAY appear in `snapshot.json` or any list; env keys only.
- NFR-5: The snapshot MUST stay under 10 GB on disk.

## Acceptance Criteria

### AC-1: (FR-1)
Given the fetch has finished, When `fetch.log` is read, Then it contains `ALLDONE`, and every repo is either `ok`, `skip`, or `FAIL <reason>`.

### AC-2: (FR-2, FR-3)
Given a fetched repo, When its files are listed, Then every non-`.git` file matches the FR-2 pattern, and no `node_modules`, venv or build output exists.

### AC-3: (FR-4)
Given a repo with `skills/x/SKILL.md`, `agents/y.md`, `commands/z.md`, When indexed, Then x is under `skills`, y under `agents`, z under `commands`.

### AC-4: (FR-4)
Given a SKILL.md whose description uses a YAML `>-` block, When indexed, Then the stored description is the joined text, not `>-`.

### AC-5: (FR-5, NFR-4)
Given `.mcp.json` with `{"command":"npx","env":{"API_KEY":"secret"}}`, When indexed, Then runtime contains `node`, env lists `API_KEY`, and `secret` appears nowhere in the outputs.

### AC-6: (FR-6)
Given a finished build, When the output directory is listed, Then `snapshot.json` and all six list files exist and are non-empty.

### AC-7: (FR-7)
Given a repo that failed to fetch, When indexed, Then it appears in `lists/fetch-failures.md` with its reason.

### AC-8: (FR-8)
Given the server, When `tools/list` is called, Then exactly `stats, list, search, get` are returned.

### AC-9: (FR-9)
Given `list` with `limit: 200` on `skills`, When called, Then the text is ≤ 8,000 characters and ends with a paging hint.

### AC-10: (NFR-1)
Given the server, When `tools/list` is serialized, Then its length is ≤ 1,500 characters.

### AC-11: (NFR-2)
Given all repos fetched, When `build_index.py` runs, Then it exits 0 in < 300 s.


### AC-12: (FR-10)
Given the user has not approved registration, When `~/.claude.json` and `~/.claude/settings.json` are searched, Then no `plugin-snapshot` MCP entry exists; Given approval, When `claude mcp list` runs, Then `plugin-snapshot` shows as connected.

### AC-13: (FR-11)
Given two plugins that both ship a skill named `code-review`, When indexed with duplicate flagging on, Then `lists/duplicates.md` lists `code-review` with both plugin names.

### AC-14: (FR-12)
Given the server, When `tools/list` is called, Then every tool has those four annotations; Given `get` with an unknown plugin or `search` with no hits, When called, Then the text names the `search` tool or suggests fewer words.

### AC-15: (FR-13)
Given a marketplace.json entry with a `git-subdir` source pointing at `plugins/p`, When the repo is fetched and indexed, Then a record named after the entry exists with marketplace set and only the components under `plugins/p`; Given an `npm` source, Then the record exists with `fetched: false` and a `not_fetchable` reason.

## Edge Cases

- EC-1: Repo deleted, private or renamed → `FAIL fetch: <stderr>`; the indexer still emits the listing with `fetched: false` and catalog components if known.
- EC-2: `reviewed_commit` no longer fetchable (force-pushed) → same as EC-1.
- EC-3: Malformed JSON/TOML/YAML → that file is skipped; the rest of the repo is indexed.
- EC-4: `hooks.json` shaped as a list instead of a map → events are still extracted.
- EC-5: Several listings share one repo (monorepo) → components are split by the listing's `#subpath`.
- EC-6: `snapshot.json` missing when the server starts → the tool returns an error text, the server stays up.
- EC-7: Unknown tool name or bad JSON on stdin → JSON-RPC error `-32602` / `-32700`; the server keeps running.
- EC-8: Fetch interrupted → rerun resumes; repos with `.done` are skipped.

## API Contracts (MCP tools)

N/A for HTTP — the server is MCP over stdio (JSON-RPC 2.0, one message per line), with no HTTP method or path, so the validator's "HTTP method + path" warning is accepted. Contracts are the MCP tool inputs and outputs below.

```ts
type Kind = "agents" | "skills" | "commands" | "mcp" | "hooks";

// stats — no input
interface StatsOut { plugins: number; fetched: number; agents: number; skills: number;
                     commands: number; mcp: number; hooks: number; }

// list
interface ListIn  { type?: Kind /* default "skills" */; offset?: number; limit?: number /* ≤200 */; }
// out: text — "<total> total, showing a-b\n" + TSV rows "kind\tname\tplugin\tdesc"

// search
interface SearchIn { query: string /* all words must match */; type?: Kind; limit?: number /* ≤200 */; }
// out: TSV rows as above, or "no matches"

// get
interface GetIn { plugin: string /* name or id */; }
// out: compact JSON PluginRecord (component lists reduced to names) or "not found"

interface ToolError { content: [{ type: "text"; text: string }]; isError: true; }
```

## Data Models

**PluginRecord** (`snapshot.json` is `PluginRecord[]`)

| Field | Type | Constraints |
|---|---|---|
| id | string | directory plugin id or `<marketplace>:<subpath>`; unique |
| name | string | required |
| title, summary | string | optional |
| marketplace | string | `directory` or local marketplace name |
| repo, sha, subpath | string | directory entries only |
| fetched | bool | false when fetch failed or pending |
| skills / agents / commands | `{name, desc ≤200, path}[]` | |
| hooks | string[] | event names, deduplicated |
| mcp | `{name, type, command, args ≤6, url, env: string[]}[]` | env = key names only |
| deps | `{npm?, pip?, cargo?, go?, docker?: string[]}` | |
| runtime | string[] | derived from mcp |
| tokens, installs | object, number | from catalog cache, when known |
| source_of_components | string | `catalog-cache` when not fetched |

## Out of Scope

- OS-1: Installing, enabling or running any plugin, hook or MCP server — the user said no installs.
- OS-2: Proxying calls to the *underlying* MCP servers (a real gateway) — needs per-server installs and credentials; separate spec if wanted.
- OS-3: Plugins that only exist in non-directory marketplaces we have not added — we index what is known locally plus the directory.
- OS-4: LLM-written summaries — descriptions are extracted verbatim and truncated, deterministic.
- OS-5: Security vetting of each plugin — the snapshot records what exists; vetting is a later step per plugin.
