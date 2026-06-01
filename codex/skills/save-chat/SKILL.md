---
name: save-chat
description: Save the current Codex conversation into the user's Obsidian vault as a markdown note. Use when the user asks to "save-chat", "/save-chat", save this chat/conversation/session, or save the current discussion to Obsidian, with optional slug support.
---

# save-chat

Save the current Codex conversation to the user's Obsidian vault by following the Claude Code `save-chat` workflow as the source specification.

## Source Of Truth

Before saving, read these files in order:

1. `~/.claude/commands/save-chat.md` - canonical save-chat specification.
2. `~/.claude/CLAUDE.local.md` - machine-local `vault_path`, `library_path`, `ai_note_folder`, `public_note_folders`, `private_note_folders`, and host naming.
3. `~/.claude/CLAUDE.md` - vault access, wikilink, and privacy rules when needed.

Any `<library_path>/...` fallback below needs `library_path`, which is only defined in `~/.claude/CLAUDE.local.md` — read that first to resolve it. If `~/.claude/commands/save-chat.md` is missing, try `<library_path>/commands/save-chat.md`; likewise `~/.claude/CLAUDE.md` falls back to `<library_path>/dotclaude/CLAUDE.md`. `~/.claude/CLAUDE.local.md` itself is machine-local and has no library fallback — if it is missing, ask the user. Do not invent vault paths, folder names, or privacy scopes.

## Invocation

Accept natural-language requests such as:

- `save-chatしてください`
- `/save-chat`
- `save-chat <slug>`
- `この会話をObsidianに保存してください`

If the user provides a slug, use it as the canonical spec defines. If not, derive one from the conversation topic.

## Codex-Specific Metadata

Follow the canonical frontmatter format, with these Codex-specific adjustments:

- `source: codex`
- `workspace`: current working directory as an absolute path.
- `machine`: short hostname from `hostname -s`.
- `model`: include the current Codex model only if it is explicitly available in the session context; otherwise omit the field rather than guessing.
- `session_id`: omit unless a stable Codex session identifier is explicitly available. Do NOT use the canonical ~/.claude/projects/<encoded>/*.jsonl method — those are Claude Code's sessions and are unrelated to this Codex chat.

Preserve existing frontmatter fields during revision mode according to the canonical rules. Do not change initial-context fields except where the canonical spec allows it.

## Workflow

1. Read the source-of-truth files.
2. Resolve `vault_path` and target the current-year AI note folder. If `ai_note_folder` contains `{YYYY}`, replace it with the current year; otherwise follow the canonical `<vault_path>/claudeYYYY/` rule unless local settings explicitly define a different target.
3. Determine the slug:
   - If the user supplied a slug, use it.
   - Otherwise generate a 3-6 word lowercase ASCII kebab-case noun phrase, avoiding generic words like `note`, `discussion`, `meeting`, and `chat`.
4. Search for an existing `*-{slug}.md` note in the current-year AI note folder, then previous-year AI note folder.
5. If a match exists, use revision mode:
   - Read the existing note.
   - Preserve the existing template unless changing it is necessary and the user approves.
   - Classify the change as small or large using the canonical criteria.
   - Update `last_revised`.
   - Merge same-day small revisions with the canonical `×N` notation; otherwise append a new revision-history row.
   - Overwrite the existing file; do not create `-2`, `-3`, or duplicate files.
6. If no match exists, use new-note mode:
   - Create the target folder if needed.
   - Inspect existing AI notes for tag vocabulary.
   - Use `default` unless another canonical template clearly fits; ask before using any non-default template.
   - Write `{YYYY-MM-DD}-{slug}.md`.
7. Apply the canonical wikilink rules:
   - AI and public note folders may be linked automatically after existence checks.
   - Private folders may be listed by filename, but content reads, quotations, or wikilinks require explicit user direction and any additional confirmation required by the canonical rules.
   - Write Obsidian wikilinks bare, for example `[[2026-05-29-example]]`, not inside backticks.
8. Report the saved path as a clickable markdown file link when possible, and state whether the result was new, a small revision, or a large revision.

## Sandbox And Permissions

If the vault is outside the writable sandbox, request approval for the needed write operation. Do not save to a fallback path unless the user explicitly asks for it.

If a required read or write is blocked, state exactly which rule could not be executed and continue only if a compliant result is still possible.

## Quality Bar

- Prefer faithful execution of the canonical spec over a short summary.
- Keep the saved note useful as an Obsidian knowledge note, not a raw transcript.
- Do not quote private notes or hidden conversation content without the required permission checks.
- Do not modify the canonical Claude command while saving a chat.
