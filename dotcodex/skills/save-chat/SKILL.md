---
name: save-chat
description: Save the current Codex conversation into the user's Obsidian vault as a markdown note. Use when the user asks to "save-chat", "/save-chat", save this chat/conversation/session, or save the current discussion to Obsidian, with optional slug support.
---

# save-chat (Codex skin)

Thin Codex entrypoint for the shared save-chat core. Do not duplicate the note format or
workflow rules in this skill.

## Source Of Truth

For any save-chat task, read and follow:

1. `<library_path>/scripts/save-chat-core.md` — the shared save-chat specification
   (workflow authority).
2. `~/.claude/CLAUDE.md` — the host-info ("ホスト情報") section (`vault_path`, `library_path`,
   `ai_note_folder`, `public_note_folders`, `private_note_folders`) and the Obsidian vault
   management rules (vault access, wikilink, privacy).

## Resolve `<library_path>`

Use the current workspace if it contains `scripts/save-chat-core.md`.

If not, read `library_path` from the host-info section of `~/.claude/CLAUDE.md` (or, on machines
not yet migrated to the unified layout, from `~/.claude/CLAUDE.local.md`). If neither defines it,
ask the user. Do not invent paths, vault folder names, or privacy scopes.

If the core file cannot be read, stop and report; do not save to a fallback path unless the user
explicitly asks for it.

## Invocation

Accept natural-language requests such as:

- `save-chatしてください`
- `/save-chat`
- `save-chat <slug>`
- `この会話をObsidianに保存してください`

If the user provides a slug, use it as the core defines. If not, derive one from the
conversation topic per the core's slug rules.

## Codex binding (implements the core's platform binding contract)

- `source`: `codex`
- `model` and `session_id`: read from the local Codex transcript:
  1. Resolve `CODEX_HOME` (default `~/.codex`).
  2. Identify the current thread in `$CODEX_HOME/session_index.jsonl`. Match both thread id and
     thread name; if the current thread cannot be identified with confidence (e.g. multiple
     concurrent Codex windows), omit both fields.
  3. Locate the transcript JSONL containing that thread id under `$CODEX_HOME/sessions/**/`
     (filename like `rollout-<timestamp>-<thread-id>.jsonl`).
  4. Read `payload.model` from the latest `turn_context` line → `model:` (e.g. `gpt-5.5`).
  5. Record the Codex thread id as `session_id:`.
  6. If `payload.effort` (reasoning effort) is available in the same `turn_context`, append it in
     parentheses per the core format: `model: gpt-5.5 (medium)`. If effort is unavailable, record
     the model ID alone.
  7. If any path or schema cannot be read, omit the affected fields. Never guess, never fill from
     UI hearsay, and never use Claude Code's `~/.claude/projects/*.jsonl` method.
- `workspace`: current working directory as an absolute path.
- `machine`: short hostname from `hostname -s`.

Preserve existing frontmatter fields during revision mode according to the core rules.

## Tool conventions

When inspecting tag vocabulary or searching notes with `rg`:

- Use `--no-filename` rather than `-h` (`rg -h` means help).
- Pass multiple patterns with `-e`, for example:
  `rg --no-filename -e '^tags:' -e '^  - ' <ai_note_folder> -g '*.md'`.
- Prefer directory + `-g '*.md'` over shell globs to avoid Windows/Git Bash/PowerShell
  expansion differences.
- `rg` may be absent in the sandbox — check availability first and fall back to
  `find` + `grep` (e.g. `grep -h -e '^tags:' -e '^  - ' <ai_note_folder>/*.md`).
  Do not fail or skip the search just because `rg` is missing; note the substitution
  in the completion report.

## Sandbox And Permissions

If the vault is outside the writable sandbox, request approval for the needed write operation.
If a required read or write is blocked, state exactly which rule could not be executed and
continue only if a compliant result is still possible.

## Quality Bar

- Prefer faithful execution of the core specification over a short summary.
- Keep the saved note useful as an Obsidian knowledge note, not a raw transcript.
- Do not quote private notes or hidden conversation content without the required permission
  checks.
- Do not modify the core specification while saving a chat.
