---
name: chat-list
description: List Claude Code, Codex, Cursor, and Copilot conversation history together, per workspace (read-only). Use when the user asks to "chat-list", "/chat-list", list/browse past chats or conversations, see a workspace's chat history, show the chat list across tools, search past conversations by title or content, or dump a past conversation's full text.
---

# chat-list (Codex skin)

Thin Codex entrypoint for the shared chat-list core (`scripts/chat-list.py`). Do not duplicate the
enumeration logic, data sources, or output format in this skill — the script is the authority.

Lists **Claude Code / Codex / Cursor (native) / Copilot (VS Code extension + CLI)** conversation
history together for a workspace, read-only. Listing and full-text extraction only; no
summarization, no resume (those are future layers). Origin column = `<WS-letter> CC|CX|CU|CP/<surface>`
(CC=Claude Code, CX=Codex, CU=Cursor, CP=Copilot).

## Source Of Truth

For any chat-list task, run and trust:

1. `<library_path>/scripts/chat-list.py` — the output and behavior authority (deterministic,
   read-only).
2. `python3 <library_path>/scripts/chat-list.py --help` — the authoritative option reference.

Prefer what the script actually does over this skill's prose; this skill only adds natural-language
selector resolution and a confirmation step.

## Roles

- **Core (`scripts/chat-list.py`, deterministic)**: takes exact selectors only (`--path` is a cwd
  path / substring, `--dump` is a conversation id). No LLM, read-only.
- **Skin (this agent)**: resolve the user's natural language into exact selectors. For ambiguous
  requests, run `--workspaces` or a list to present candidates and narrow down. **Before `--dump`,
  show the target's title / start time / a preview and get the user's confirmation** (safety lives
  in this confirmation).

## Resolve `<library_path>`

Use the current workspace if it contains `scripts/chat-list.py`. If not, read `library_path` from
the host-info ("ホスト情報") section of `~/.claude/CLAUDE.md` (or, on machines not yet migrated, from
`~/.claude/CLAUDE.local.md`). If neither defines it, ask the user. Do not invent paths. If the
script cannot be run, stop and report.

## Invocation

Run the core and **present the listing itself, not a prose summary**:

```bash
python3 <library_path>/scripts/chat-list.py [options]
```

(On Windows use `python` / `py` instead of `python3`, or the `chat-list` command if it is on PATH.)

Show the output rows (`#`, time, origin, id, size, title, plus any `--grep` / `--head` / `--tail`
matching or preview lines) with their numbers and ids intact — those are the handles the user
needs to follow up (`--dump <id>`, picking a workspace, etc.). A one- or two-line orienting note
above the list is fine, but do not replace the rows with a digest. For long results, still show
the rows (or the most relevant / top-N, saying so) rather than summarizing them away.

`--help` is the authoritative option reference. Main options:

- no args: the current cwd's workspace, all four tools merged, newest first.
- `--path <value>`: target a workspace by path. **Substring by default** (NFC-normalized; bundles
  rename/normalization-split dirs); `--exact` for full equality. Repeatable / comma-separated.
  Works in the default list and with `--workspaces`. **Mutually exclusive with `--all`**.
- `--all`: every workspace (no path restriction). Cannot be combined with `--path`.
- `--exact`: make `--path` / `--title` match exactly (default is substring).
- `--workspaces`: numbered per-workspace census (per-tool counts CC/CX/CU/CP, a `total`, an `arch`
  column `-N` = archived/hidden of total, size, and separate `start`/`end` date columns).
- `--sort` / `--reverse`: ordering, **default `start` = start time, newest first**. Keys match the
  column headers: shared `start`, `end` (last activity = last in-content timestamp, not OS mtime),
  `size`; conversation-list-only `title`; `--workspaces`-only `total` (count) and `path`.
  start/end/size/total descending, title/path ascending; `--reverse` (`-r`) flips. A key invalid
  for the mode is an error.
- `--head N` / `--tail N`: keep the first / last N rows of the output (Unix-like; both modes).
- `--preview [N]`: in the conversation list, show each conversation's body preview — `N` first N
  lines, `--preview=-N` last N lines, bare `--preview` = 10. Each line is prefixed `[role HH:MM]`.
- `--title <text>` / `--grep <text>`: filter by title (substring, or exact with `--exact`) / by
  body full-text (reads bodies, slower). Both work in both modes.
- `--tool claude|codex|cursor|copilot`, `--include-subagents`: both modes.
- `--dump <id>`: a conversation's full text to stdout (`> file` to save) or `--open [cursor|code]`
  for an editor buffer; `--json` for a structured message array. Opens with an info block
  (`# key : value` framed by `# ────` rules: id/origin/model/messages/events/span/size/cwd/path/
  title); each message is preceded by a rule and a header `### <role> [i/N] <time>` (role first, so
  it greps cleanly). A `ts` field appears per message under `--json`. Grep message positions with
  `grep -nE '^### \w+ +\[[0-9]+/[0-9]+\] '` (or `^### user ` to filter a role); for machine use
  prefer `--json` (boundaries are array elements = 100% reliable).
- `--long` (`-l`): add a model column (cursor/copilot from records; claude from jsonl, codex from
  rollout head). Omitted by default.
- archived/hidden rows are **always shown** (never excluded) with a `*` mark after origin; under
  `--long`, claude shows `*c`(hidden in Cursor) `*v`(VS Code) `*cv`(both), others `*`. `--workspaces`
  shows the count in the `arch` column (`-N`).
- `--json`: machine-readable structured JSON (any mode; dump = message array).

## Natural language → selector

- "○○ workspace's history": `--path ○○` (substring). If it spans multiple workspaces, show
  `--workspaces` and let the user pick. Multiple at once: `--path a --path b`. Exact: add `--exact`.
- "workspace number N": from a `--workspaces` listing, look up that row's path and pass `--path
  <path> --exact` (the leading `#` is a per-listing unstable key; the path is the stable selector;
  use `--json`'s `cwd` to map mechanically).
- "show conversation N in full" / "the ○○ conversation": resolve the listing number or title to a
  conversation id and run `--dump <id>`. **First** show that one conversation's title / start time
  / a body preview (`--preview`) and confirm.
- "find conversations containing ○○": `--grep ○○` (body full-text). Title only: `--title ○○`.
- Numbers (`#`) in both the conversation list and the workspace list are reassigned per display
  (unstable). The stable selector is always an id or a workspace path.
- Do not paste large dumps inline — open with `--open` or redirect to a file; or excerpt key parts.

## Sandbox And Permissions

The script reads, read-only, from outside the workspace: `~/.claude/projects/*.jsonl` (claude),
`~/.codex/state_5.sqlite` (codex; older builds use `~/.codex/sqlite/`, newest by mtime wins), Cursor/VS Code `…/globalStorage/state.vscdb` and
`…/workspaceStorage/<hash>/` (cursor native + copilot), and `~/.copilot/` (copilot CLI). WAL
sqlite DBs are opened `mode=ro` with an `immutable=1` fallback so they read whether or not the
owning app is running. In a restricted sandbox the read (or running `python3`) may need approval.
It never writes session stores. Request approval for the read if blocked; if it cannot be granted,
state exactly what could not run.

## Quality Bar

- Read-only: never modify Claude/Codex session stores, and do not write notes.
- Start time comes from in-file timestamps, not mtime (the core handles this; do not second-guess
  with file dates).
- Confirm before `--dump`; do not surface another user's or private conversation content beyond
  what the user asked for.
- Do not modify the core script while listing.
