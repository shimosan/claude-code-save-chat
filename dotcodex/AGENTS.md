<!-- BEGIN claude-library-codex-adapter -->
# Claude Library Codex Adapter

This file is the library-side source for the managed adapter block in
`~/.codex/AGENTS.md`. When editing this repository, treat the repository
maintenance rules in `.claude/CLAUDE.md` as canonical.

This Codex setup shares policy with the local Claude Code setup.

Before tasks involving the user's Obsidian vault, save-chat, local machine
policy, or this configuration library, read this file when available:

1. `~/.claude/CLAUDE.md` — shared rules, machine-local settings (the "ホスト情報" /
   host-info section), and memory are all unified here.

On machines not yet migrated to the unified layout, `~/.claude/CLAUDE.local.md` may
still exist holding the machine-local settings; read it as a fallback only when
`CLAUDE.md` has no host-info section.

Treat those files as policy sources, not as Codex files to edit.

Interpret "Claude" and "Claude Code" as "the agent" when a rule is about
privacy, vault access, notes, save-chat, Dropbox temp cleanup, or shared
configuration safety. Interpret those names literally when a rule describes
Claude Code files, commands, or distribution targets.

Do not interpret Claude-specific mechanisms as Codex mechanisms:

- `@...` import lines are Claude Code syntax. Read the referenced file
  explicitly when needed.
- `#` and `/memory` behavior is Claude Code-specific.
- Do not append to `~/.claude/CLAUDE.md` (including its memory zone below the
  `claude-library:end` marker) unless the user explicitly asks for a memory or
  configuration update and approves the target scope.

For save-chat, use the installed Codex skill when available. The skill should
read the Claude Code save-chat command spec as the canonical workflow.

For vault access, follow the folder privacy rules and the concrete paths and folder
names in `~/.claude/CLAUDE.md` (the host-info section). On machines not yet migrated,
those paths may still live in `~/.claude/CLAUDE.local.md` — fall back to it if needed.

If a required file is missing or blocked by sandbox permissions, explain which
policy source could not be read and ask before inventing paths, folder names,
privacy scopes, or fallback behavior.
<!-- END claude-library-codex-adapter -->
