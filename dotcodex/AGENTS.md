<!-- BEGIN claude-library-codex-adapter -->
# Claude Library Codex Adapter

This is the managed Codex global adapter for machines using the Claude
configuration library.

The block between the BEGIN/END markers is managed by the Claude configuration
library. Content outside this block in `~/.codex/AGENTS.md` is user-managed and
must be preserved during deployment or merge.

This Codex setup shares selected policy with the local Claude Code setup.

Before tasks involving the user's Obsidian vault, save-chat, local machine
policy, Dropbox-synced notes/configuration, or the Claude configuration library,
read the following file when available:

1. `~/.claude/CLAUDE.md` — shared rules, machine-local settings (the "ホスト情報" /
   host-info section), and memory are all unified here.

Treat that file as a policy source, not as a Codex file to edit.

When editing the Claude configuration library itself (the repository recorded as
`library_path` in host-info), treat that repository's `.claude/CLAUDE.md` as
canonical repository instructions. Do not treat `dotclaude/CLAUDE.md` or
`dotcodex/AGENTS.md` as project instructions by default; they are distribution
masters for end-user configuration.

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

For vault access, follow the folder privacy rules, concrete paths, and folder
names from the host-info section of `~/.claude/CLAUDE.md`.

If a required file is missing or blocked by sandbox permissions, explain which
policy source could not be read and ask before inventing paths, folder names,
privacy scopes, or fallback behavior.
<!-- END claude-library-codex-adapter -->
