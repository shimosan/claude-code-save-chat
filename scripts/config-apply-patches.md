# Config Apply Patches

Agent-facing reference for optional local patch and recovery recipes.

This file is separate from [`config-apply-recipes.md`](config-apply-recipes.md). Config recipes apply snapshot-visible configuration drift. Patch recipes here are local maintenance or recovery actions whose state is not captured in config snapshots, even when an individual patcher has its own status check. Recipes in this file use `recipe_type: patch`.

## Core Rules

- Apply only after explicit user approval for the concrete patch recipe command.
- Prefer `--dry-run`, `status`, or other non-destructive checks before writing.
- Report what local file, installed extension, database, LaunchAgent, or repository artifact will be changed.
- Create or rely on the patcher's backup/restore path before writing.
- When run through `config-manager`, record a `log/config/config_apply_<machine>_*.md` apply log with `recipe_type: patch`, just like snapshot-driven config recipes.
- Do not duplicate detailed patch docs here. Link to the script-specific document.
- Treat these as unofficial local patches. Use at your own risk.

## Patch Recipes

### `webview.ctrlf-patch`

- Recipe type: `patch`
- Script: [`patch-vscode-webview-ctrlf.js`](patch-vscode-webview-ctrlf.js)
- Docs: [`patch-vscode-webview-ctrlf.md`](patch-vscode-webview-ctrlf.md)
- Applies to: VS Code-family local or remote extension installs that contain Claude Code or Codex/OpenAI ChatGPT webview assets. Most useful on macOS because the symptom is macOS `Control-F` behavior.
- Log target: installed extension files reported by `--status` or `--dry-run`.
- Purpose: patch installed VS Code/Cursor-style webview extensions so macOS `Control-F` moves the caret forward inside Claude Code and Codex chat inputs.
- Preview: `node scripts/patch-vscode-webview-ctrlf.js --dry-run`
- Apply: `node scripts/patch-vscode-webview-ctrlf.js`
- Verify: `node scripts/patch-vscode-webview-ctrlf.js --status`
- Restore: `node scripts/patch-vscode-webview-ctrlf.js --restore`

### `vscode-r.webview-find-patch`

- Recipe type: `patch`
- Script: [`patch-vscode-r-webview-find.py`](patch-vscode-r-webview-find.py)
- Docs: [`patch-vscode-r-webview-find.md`](patch-vscode-r-webview-find.md)
- Applies to: per-user VS Code-family extension installs containing `reditorsupport.r`; scans common macOS/Linux-style extension roots plus Cursor, or an explicit `--extensions-dir`.
- Log target: vscode-R `package.json` files changed or restored.
- Purpose: stop the vscode-R extension from activating when Find is opened in unrelated webviews.
- Preview: `python3 scripts/patch-vscode-r-webview-find.py --dry-run`
- Apply: `python3 scripts/patch-vscode-r-webview-find.py`
- Restore: `python3 scripts/patch-vscode-r-webview-find.py --restore`

### `editor.retired-local-target-comments-fix`

- Recipe type: `patch`
- Script: [`fix-retired-local-target-comments.py`](fix-retired-local-target-comments.py)
- Applies to: VS Code/Cursor User `settings.json` files on macOS or Windows that still contain retired `local/` target/template comments.
- Log target: settings JSONC files whose comments were changed.
- Purpose: remove obsolete comments in VS Code/Cursor User settings that point at retired `local/` editor target/template files.
- Preview: `python3 scripts/fix-retired-local-target-comments.py --dry-run`
- Apply: `python3 scripts/fix-retired-local-target-comments.py --write --backup`
- Test: `python3 scripts/fix-retired-local-target-comments.py --self-test`

### `cursor.hidden-agent-views-fix`

- Recipe type: `patch`
- Script: [`fix-cursor-hidden-agent-views.py`](fix-cursor-hidden-agent-views.py)
- Docs: [`fix-cursor-hidden-agent-views.md`](fix-cursor-hidden-agent-views.md)
- Applies to: macOS Cursor workspace `state.vscdb` files when Claude Code or Codex view containers are hidden for one workspace.
- Log target: explicit `state.vscdb` path and backup files.
- Purpose: restore hidden Claude Code and Codex view containers in a Cursor workspace `state.vscdb`.
- Preview: `python3 scripts/fix-cursor-hidden-agent-views.py --db "/path/to/state.vscdb" --dry-run`
- Apply: `python3 scripts/fix-cursor-hidden-agent-views.py --db "/path/to/state.vscdb"`

### `cursor.agent-worker-disable-patch`

- Recipe type: `patch`
- Script: [`patch-cursor-agent-worker-disable.py`](patch-cursor-agent-worker-disable.py)
- Docs: [`patch-cursor-agent-worker-disable.md`](patch-cursor-agent-worker-disable.md)
- Applies to: macOS Cursor globalStorage `state.vscdb` when built-in `anysphere.cursor-agent-worker` is stuck showing Restart Extension / Reload Window prompts and the UI cannot disable it.
- Log target: Cursor globalStorage `state.vscdb`, backup DB path, and `extensionsIdentifiers/disabled` before/after values.
- Purpose: disable or re-enable Cursor's built-in `cursor-agent-worker` by editing Cursor's disabled extension identifier list without modifying installed application files.
- Status: `python3 scripts/patch-cursor-agent-worker-disable.py --status`
- Preview apply: `python3 scripts/patch-cursor-agent-worker-disable.py --apply --dry-run`
- Apply: `python3 scripts/patch-cursor-agent-worker-disable.py --apply`
- Remove: `python3 scripts/patch-cursor-agent-worker-disable.py --remove`
- Test: `python3 scripts/patch-cursor-agent-worker-disable.py --self-test`

### `codex.git-fsmonitor-env-patch`

- Recipe type: `patch`
- Script: [`patch-codex-git-fsmonitor-env.sh`](patch-codex-git-fsmonitor-env.sh)
- Docs: [`patch-codex-git-fsmonitor-env.md`](patch-codex-git-fsmonitor-env.md)
- Applies to: macOS GUI sessions running Codex in Cursor or Codex Desktop app against Git repositories where Codex-created fsmonitor artifacts are a problem.
- Log target: LaunchAgent path, GUI-session `CODEX_APPLY_GIT_CFG` state, and optional repository artifact status.
- Purpose: set `CODEX_APPLY_GIT_CFG=0` for the macOS GUI session to reduce Codex-created Git fsmonitor artifacts under Dropbox.
- Status: `bash scripts/patch-codex-git-fsmonitor-env.sh status [repo]`
- Apply: `bash scripts/patch-codex-git-fsmonitor-env.sh apply`
- Remove: `bash scripts/patch-codex-git-fsmonitor-env.sh remove`
- Fallback blocker: `bash scripts/patch-codex-git-fsmonitor-env.sh blocker-apply /path/to/repo`
