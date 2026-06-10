# Scripts

This directory holds the library's workflow authorities (specification documents that thin platform entrypoints read at runtime) and optional utility scripts. Nothing here is deployed to machines; everything is referenced in place via `library_path`.

Each script should have a short entry here. Simple scripts can be fully documented in one or two lines in this index; scripts with non-trivial usage should have a dedicated help document.

## Available Scripts

### Workflow Authorities

- [`save-chat-core.md`](save-chat-core.md): the shared save-chat specification (note format, slug/tag rules, revision rules, wikilink scope, platform binding contract). The Claude Code command, Codex skill, and Copilot prompt are thin skins that read this file at runtime.

### Config Workflow And Helpers

- [`config-update.md`](config-update.md): agent-facing public protocol for config snapshot comparison, local policy/recipe handling, proposal, approval, and handoff to recipes. Thin skills such as `config-manager` should delegate to this file.
- [`config-apply-recipes.md`](config-apply-recipes.md): concrete agent-facing config recipes for applying approved snapshot-visible configuration changes, including per-recipe risk metadata and the general rule for uncovered snapshot sources.
- [`config-apply-patches.md`](config-apply-patches.md): agent-facing index for optional local patch recipes. Separate from snapshot-driven config recipes.
- [`config-snapshot-mac.py`](config-snapshot-mac.py): collect a read-only live configuration snapshot from a macOS machine and print JSON, write a temporary `scratch/config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json` with `--scratch`, or write the regular sync log under `log/config/` with `--log`. Refuses to run on non-macOS.
- [`config-snapshot-win.py`](config-snapshot-win.py): Windows counterpart to `config-snapshot-mac.py`, with Windows-specific paths, `where.exe`, PowerShell/Git Bash sources, and UTF-8-safe subprocess decoding. Refuses to run on non-Windows.
- [`config-log-helper.py`](config-log-helper.py): inspect `log/config/` snapshots/apply logs, find latest valid snapshots, show raw timelines with apply consistency checks, summarize N-way/latest-snapshot drift, and create apply log skeletons. Read-only except `apply-log-skeleton --write`; use `--self-test` for non-destructive fixture tests.
- [`config-jsonc-set-keys.py`](config-jsonc-set-keys.py): set top-level JSONC object keys while preserving comments and unrelated text. Intended for VS Code/Cursor User settings and argv config files; use `--backup` for live config writes and `--self-test` for non-destructive fixture tests.

### Patch And Recovery Utilities

- [`patch-vscode-webview-ctrlf.js`](patch-vscode-webview-ctrlf.js): patch installed VS Code/Cursor-style webview extensions so macOS `Control-F` moves the caret forward by one character inside Claude Code and Codex chat inputs. See [`patch-vscode-webview-ctrlf.md`](patch-vscode-webview-ctrlf.md).
- [`patch-vscode-r-webview-find.py`](patch-vscode-r-webview-find.py): stop the vscode-R extension from implicitly activating (and showing a spurious `R: (not attached)` status bar item) when Find is opened in an unrelated webview such as a Markdown preview. Idempotent, with `--dry-run`, `--restore`, and `--extensions-dir`. See [`patch-vscode-r-webview-find.md`](patch-vscode-r-webview-find.md).
- [`fix-retired-local-target-comments.py`](fix-retired-local-target-comments.py): remove obsolete JSONC comments in VS Code/Cursor User settings that point at retired `local/` editor target/template files. Comment-only, with `--dry-run`, `--write`, `--backup`, and `--self-test`.
- [`fix-cursor-hidden-agent-views.py`](fix-cursor-hidden-agent-views.py): restore hidden Claude Code and Codex view containers in a Cursor workspace `state.vscdb`. Requires an explicit `--db` path and backs up the database before writing. See [`fix-cursor-hidden-agent-views.md`](fix-cursor-hidden-agent-views.md).
- [`patch-cursor-agent-worker-disable.py`](patch-cursor-agent-worker-disable.py): disable or re-enable Cursor's built-in `anysphere.cursor-agent-worker` through globalStorage `state.vscdb` when it is stuck showing Restart Extension / Reload Window prompts. Includes `--status`, `--apply`, `--remove`, `--dry-run`, and `--self-test`. See [`patch-cursor-agent-worker-disable.md`](patch-cursor-agent-worker-disable.md).
- [`patch-codex-git-fsmonitor-env.sh`](patch-codex-git-fsmonitor-env.sh): set `CODEX_APPLY_GIT_CFG=0` through macOS `launchctl`/LaunchAgent so Codex does not inject Git fsmonitor config. Includes `status`, `apply`, `remove`, and repo-local fallback blocker commands. See [`patch-codex-git-fsmonitor-env.md`](patch-codex-git-fsmonitor-env.md).

## Conventions

- Keep `README.md` as an index.
- For simple scripts, a short README entry is enough.
- For scripts with detailed usage, caveats, or examples, add a script-specific `.md` file.
- Prefer reversible scripts with `--dry-run`, `--status`, and restore-style commands when they modify local installed software.
