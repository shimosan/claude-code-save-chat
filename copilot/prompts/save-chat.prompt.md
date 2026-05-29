name: "save-chat"
description: "Use when: save the current chat into the user's Obsidian vault as a markdown note, following the Claude save-chat workflow with optional slug support."
argument-hint: "[optional-slug]"
agent: "agent"
Save the current conversation as a markdown note by following the existing Claude save-chat workflow as closely as possible.

Runtime requirements:
- Treat ~/.claude/commands/save-chat.md as the source specification. If it is missing, resolve library_path from ~/.claude/CLAUDE.local.md and read <library_path>/commands/save-chat.md instead.
- Read ~/.claude/CLAUDE.local.md to resolve vault_path, library_path, and machine-local vault settings. This file is required and has no library fallback (it is machine-local and defines both vault_path and library_path); if it is missing, ask the user instead of guessing.
- Read ~/.claude/CLAUDE.md if needed for vault scope, wikilink, and privacy rules. If it is missing, fall back to <library_path>/CLAUDE.md.
- Use the current year to target <vault_path>/claudeYYYY/.
- Accept an optional slug argument. If no slug is provided, derive a 3-6 word lowercase kebab-case slug from the conversation topic.

Copilot-specific frontmatter (override the canonical defaults):
- source: github-copilot
- session_id: use your own Copilot session identifier if one is available (e.g. the Copilot chat session UUID); otherwise omit it. Do NOT use the canonical ~/.claude/projects/<encoded>/*.jsonl method — those are Claude Code's sessions and are unrelated to this Copilot chat.
- model / workspace / machine: follow the canonical rules (current Copilot model if known; workspace = cwd; machine = `hostname -s`).

Execution steps:
1. Read the source specification (~/.claude/commands/save-chat.md, or <library_path>/commands/save-chat.md if the former is missing) and follow its rules unless a required tool is unavailable.
2. Determine the slug.
3. Search for an existing note matching *-{slug}.md in the current year folder, then the previous year folder.
4. If a matching note exists, update it in revision mode.
5. If no matching note exists, create a new note in the current year folder.
6. Reuse existing tag vocabulary where practical by inspecting notes in the target year.
7. Preserve the workflow's frontmatter, title, revision history, and revision-size rules, applying the Copilot-specific frontmatter overrides above.
8. Obey the private/public note access and wikilink rules from the Claude memory files.
9. At the end, report the saved path and whether the action was new, small revision, or large revision.

Behavior constraints:
- Prefer a faithful implementation over a simplified summary.
- If a specific rule cannot be executed in this environment, state exactly what was skipped and continue with the closest compliant result.
- Do not invent vault paths or metadata; read them from the configured Claude files.
