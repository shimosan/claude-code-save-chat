name: "save-chat"
description: "Use when: save the current chat into the user's Obsidian vault as a markdown note, following the shared save-chat core specification with optional slug support."
argument-hint: "[optional-slug]"
agent: "agent"
Save the current conversation as a markdown note. This prompt is a thin Copilot entrypoint for the shared save-chat core; do not duplicate the note format or workflow rules here.

Source of truth (read and follow, in order):
1. <library_path>/scripts/save-chat-core.md — the shared save-chat specification (workflow authority).
2. ~/.claude/CLAUDE.md — the host-info ("ホスト情報") section (vault_path, library_path, ai_note_folder, public_note_folders, private_note_folders) and the Obsidian vault management rules (vault access, wikilink, privacy).

Resolve <library_path>: use the current workspace if it contains scripts/save-chat-core.md; otherwise read library_path from the host-info section of ~/.claude/CLAUDE.md (or, on machines not yet migrated, from ~/.claude/CLAUDE.local.md). If neither defines it, ask the user. Do not invent paths. If the core file cannot be read, stop and report; do not save to a fallback path.

Copilot binding (implements the core's platform binding contract):
- source: github-copilot
- session_id: Copilot's own chat session identifier — the debug-logs folder UUID under <VS Code User dir>/workspaceStorage/<workspace-hash>/GitHub.copilot-chat/debug-logs/<uuid>/ when identifiable; otherwise omit. Never use Claude Code's ~/.claude/projects/*.jsonl method.
- model: the current Copilot model ID if known (the models.json in the same debug-logs session folder is a valid source). If reasoning effort is also reliably available, append it in parentheses per the core format: model: <ID> (<effort>); otherwise record the ID alone. If the model cannot be determined, omit the field. Never guess.
- workspace: current working directory (absolute path); machine: short hostname (hostname -s).

Execution: determine the slug (argument or derived per the core rules), then follow the core's workflow — related-note search, existing-note lookup (current then previous year), new-note or revision mode, tag vocabulary reuse, wikilink scope rules, frontmatter and revision-history formats — applying the Copilot binding above.

Tool conventions: for related-note search and tag-vocabulary extraction, `rg` may be absent in the Copilot execution environment — check availability first and fall back to `find` + `grep` (e.g. `grep -h -e '^tags:' -e '^  - ' <ai_note_folder>/*.md`); do not fail or skip the search just because `rg` is missing. If `rg` is available, use `--no-filename` (not `-h`, which means help) and pass multiple patterns with `-e`.

Behavior constraints:
- Prefer faithful execution of the core specification over a simplified summary.
- If a specific rule cannot be executed in this environment, state exactly what was skipped and continue with the closest compliant result.
- At the end, report the saved path and whether the action was new, a small revision, or a large revision.
