---
name: config-manager
description: Review, compare, and safely apply local machine configuration changes using this library's config snapshot/update workflow. Use when the user asks to inspect config drift, compare machines, review recent config changes, apply settings from another machine, roll back a setting, or manage config policy/recipes.
---

# config-manager

Thin Codex entrypoint for the library config workflow.

## Source Of Truth

For any review/apply/config-policy task, read and follow:

1. `<library_path>/scripts/config-update.md`
2. Only when that workflow tells you to: `<library_path>/scripts/config-apply-recipes.md`

Do not duplicate policy, private recipes, or apply rules in this skill.

## Resolve `<library_path>`

Use the current workspace if it contains `scripts/config-update.md`.

If not, read `~/.claude/CLAUDE.local.md` and resolve `library_path` from there. If that file is missing or does not define `library_path`, ask the user. Do not invent paths.

## Invocation

Trigger for requests such as:

- `config-manager`
- `設定の差分を見て`
- `最近の config 変更を見せて`
- `<machine> の設定をこの端末に取り込みたい`
- `この設定を前の状態に戻して`
- `config policy に記録して`

## Behavior

- For review/apply/config-policy work, read `scripts/config-update.md` first and follow it.
- For pure overview requests, you may directly run `scripts/config-log-helper.py timeline`, `drift`, or `nway`; if interpretation, proposal, policy updates, or apply work is needed, return to `scripts/config-update.md`.
- Treat `local/config-policy.md` and `local/config-local-recipes.md` as private files managed by `scripts/config-update.md`. Do not edit them unless that workflow calls for it and the user explicitly approves the exact change.
- Do not edit live VS Code, Cursor, shell, Git, extension, skill, prompt, or other configuration before explicit approval for the concrete change.
- Prefer non-login shell execution for snapshot helpers when the tool supports it.

## Reporting

Keep user-facing responses concise:

- state the active mode (`review-only` or `apply`)
- summarize the snapshots/logs consulted
- show proposed old/new values and target before applying
- after apply, report backup, verification snapshot, apply log, and any reload/restart requirement
