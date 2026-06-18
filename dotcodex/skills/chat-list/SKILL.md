---
name: chat-list
description: List Claude Code and Codex conversation history together, per workspace (read-only). Use when the user asks to "chat-list", "/chat-list", list/browse past chats or conversations, see a workspace's chat history, show the chat list across tools, search past conversations by title or content, or dump a past conversation's full text.
---

# chat-list (Codex skin)

Thin Codex entrypoint for the shared chat-list core (`scripts/chat-list.py`). Do not duplicate the
enumeration logic, data sources, or output format in this skill — the script is the authority.

Lists Claude Code and Codex conversation history together for a workspace, read-only. Listing and
full-text extraction only; no summarization, no resume (those are future layers).

## Source Of Truth

For any chat-list task, run and trust:

1. `<library_path>/scripts/chat-list.py` — the output and behavior authority (deterministic,
   read-only).
2. `python3 <library_path>/scripts/chat-list.py --help` — the authoritative option reference.

Prefer what the script actually does over this skill's prose; this skill only adds natural-language
selector resolution and a confirmation step.

## Roles

- **Core (`scripts/chat-list.py`, deterministic)**: takes exact selectors only (`--ws` is a cwd
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

Show the output rows (`#`, time, origin, id, title, plus any `--grep` / `--head` / `--tail`
matching or preview lines) with their numbers and ids intact — those are the handles the user
needs to follow up (`--dump <id>`, picking a workspace, etc.). A one- or two-line orienting note
above the list is fine, but do not replace the rows with a digest. For long results, still show
the rows (or the most relevant / top-N, saying so) rather than summarizing them away.

`--help` is the authoritative option reference. Main options:

- no args: the current cwd's workspace, claude+codex merged, time-sorted.
- `--ws <value>`: target a workspace. A leading `/` is an exact absolute path; otherwise a cwd
  substring (NFC-normalized; bundles rename/normalization-split dirs). Repeatable / comma-separated
  for multiple workspaces. Works in the default list and with `--workspaces`. **Mutually exclusive
  with `--all-ws`** (giving both is an error).
- `--all-ws`: every workspace (no cwd restriction). Cannot be combined with `--ws`.
- `--workspaces`: numbered per-workspace census (conversation counts, span; archived codex shown
  as a separate `⊘N`). `--sort last|count|name|first` orders it.
- `--head N` / `--tail N`: preview each conversation's first / last N lines.
- `--title <text>`: filter by title (fast, metadata only).
- `--grep <text>`: full-text search of conversation bodies, showing matching lines (reads bodies,
  slower; limited to the `--ws` scope).
- `--dump <id>`: a conversation's full text to stdout, `--out FILE`, or `--open [cursor|code]` for
  an editor buffer; `--raw` for raw jsonl.
- `--limit N`: keep only the newest N of the conversation list ("last/recent N"; does not affect
  `--workspaces`).
- `--tool claude|codex`, `--since YYYY-MM-DD`, `--include-subagents`, `--include-archived`,
  `--format json`.

## Natural language → selector

- "○○ workspace's history": `--ws ○○` (substring). If it spans multiple workspaces, show
  `--workspaces` and let the user pick. Multiple at once: `--ws a --ws b`.
- "workspace number N": from a `--workspaces` listing, look up that row's path and pass `--ws
  <path>` (the leading `#` is a per-listing unstable key; the path is the stable selector; use
  `--format json`'s `i` to map mechanically).
- "show conversation N in full" / "the ○○ conversation": resolve the listing number or title to a
  conversation id and run `--dump <id>`. **First** show that one conversation's title / start time
  / last few lines and confirm.
- "find conversations containing ○○": `--grep ○○` (body full-text). Title only: `--title ○○`.
- Numbers (`#`) in both the conversation list and the workspace list are reassigned per display
  (unstable). The stable selector is always an id or a workspace path.
- Do not paste large dumps inline — open with `--open` / `--out` or excerpt the key parts.

## Sandbox And Permissions

The script reads `~/.claude/projects/*.jsonl` (claude) and `~/.codex/sqlite/state_5.sqlite`
(codex). These live outside the workspace, so in a restricted sandbox the read (or running
`python3`) may need approval. It is strictly read-only — it never writes session stores. Request
approval for the read if blocked; if it cannot be granted, state exactly what could not run.

## Quality Bar

- Read-only: never modify Claude/Codex session stores, and do not write notes.
- Start time comes from in-file timestamps, not mtime (the core handles this; do not second-guess
  with file dates).
- Confirm before `--dump`; do not surface another user's or private conversation content beyond
  what the user asked for.
- Do not modify the core script while listing.
