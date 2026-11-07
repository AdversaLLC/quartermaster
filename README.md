# Quartermaster

A local MCP server for Claude Code. You describe a task once. It answers with:

- the team the task belongs to (for example `security-reverse-eng`, `debug`, `research`)
- a kit for each step (discuss, plan, execute, verify, ship): the skills, agents,
  commands and MCP servers from the plugin directory that fit that step
- a risk grade (A to D) for each item, and whether you have it installed
- call-a-friend checkpoints: after the plan, before anything irreversible,
  after two failures, and before saying the work is done

It uses the Python standard library only. At serve time it reads one prebuilt
index file and makes no network calls.

## Honest limits

- Grades are declared risk read from a plugin's files (hooks, install scripts,
  hidden unicode, and similar). Grade A means "nothing risky declared", not
  "safe". Nothing is executed during the audit, and a grade is not a safety
  guarantee.
- Routing quality is checked against a small labeled task set. The labels were
  written by the author, so treat the numbers as a sanity check, not a benchmark.
- Plugins whose files could not be fetched are graded `unaudited` and are never
  recommended. In the current snapshot that is 286 plugins.
- By default only grades A and B are recommended. `allow_risky` admits C and D,
  each with a warning.

## Install

Requires Python 3 and Claude Code (the rebuild reads Claude Code's plugin
directory cache at `~/.claude/plugins/plugin-directory-cache-v2.json`).

```
git clone <this repo> quartermaster
cd quartermaster
./rebuild.sh          # optional arg: parallel fetch workers, default 16
claude mcp add quartermaster -- python3 /path/to/quartermaster/qm_mcp.py
```

`rebuild.sh` runs three steps: `fetch.py` (fetches only manifest files of each
plugin repo into `repos/`; nothing is installed or run), `build_index.py`
(writes `snapshot.json` and `lists/`), and `qm_build.py` (writes
`qm_index.json`). Re-run it when the plugin directory changes; the server
refuses to serve an index older than `snapshot.json`.

## Tools

`route`
- `task` (string, required): the task in plain words
- `allow_risky` (boolean, default false): also recommend grade C and D items
- `depth` (`normal` or `deep`, default `normal`): up to 5 or up to 10 items per step

`explain`
- `id` (string): a component as `name@plugin`. A bare name picks the best
  installed, best-graded copy and says which one it picked.
- Returns the component's teams with the rule that matched, its grade, the
  audit reasons, install state, dependencies and description.

## Output shape

```
team: <team> (<matched keyword>) | confidence: high | grades: A,B
## plan
- id | kind | inst y/n | grade | deps | why
## execute
- id | kind | inst y/n | grade | deps | why
...
## checkpoints (run /call-a-friend; it scrubs and logs)
brief: Asked: "<task>". Planned: <3 lines>. What is wrong or missing?
checkpoint after-plan: plan written, before executing
...
```

If no component matches the task well enough, the first line says
`confidence: low`, it asks a clarifying question, and it shows the default
review and research workflow instead.

## Other files

`snapshot_mcp.py` is an older, separate MCP server with search, list and get
over the raw snapshot. It is not needed for routing.

## Tests

```
python3 -m pytest -q tests/test_router.py
```

The tests use synthetic fixtures. Tests marked as needing the real index are
skipped until you have run `./rebuild.sh`.

## License

MIT, see `LICENSE`. Third-party plugin content is not included; see `NOTICE`.
