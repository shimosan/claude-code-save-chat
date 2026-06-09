# Config Apply Patches

Agent-facing reference for optional local patch and recovery utilities.

This file is separate from [`config-apply-recipes.md`](config-apply-recipes.md). Recipes apply snapshot-visible configuration drift. Patches here are local maintenance or recovery actions that may not appear in snapshots.

## Core Rules

- Apply only after explicit user approval for the concrete patch command.
- Prefer `--dry-run`, `status`, or other non-destructive checks before writing.
- Report what local file, installed extension, database, LaunchAgent, or repository artifact will be changed.
- Create or rely on the patcher's backup/restore path before writing.
- Do not duplicate detailed patch docs here. Link to the script-specific document.
- Treat these as unofficial local patches. Use at your own risk.

## Patch Utilities

### `webview.ctrlf-patch`

- Script: [`patch-vscode-webview-ctrlf.js`](patch-vscode-webview-ctrlf.js)
- Docs: [`patch-vscode-webview-ctrlf.md`](patch-vscode-webview-ctrlf.md)
- Purpose: patch installed VS Code/Cursor-style webview extensions so macOS `Control-F` moves the caret forward inside Claude Code and Codex chat inputs.
- Preview: `node scripts/patch-vscode-webview-ctrlf.js --dry-run`
- Apply: `node scripts/patch-vscode-webview-ctrlf.js`
- Verify: `node scripts/patch-vscode-webview-ctrlf.js --status`
- Restore: `node scripts/patch-vscode-webview-ctrlf.js --restore`

### `vscode-r.webview-find-patch`

- Script: [`patch-vscode-r-webview-find.py`](patch-vscode-r-webview-find.py)
- Docs: [`patch-vscode-r-webview-find.md`](patch-vscode-r-webview-find.md)
- Purpose: stop the vscode-R extension from activating when Find is opened in unrelated webviews.
- Preview: `python3 scripts/patch-vscode-r-webview-find.py --dry-run`
- Apply: `python3 scripts/patch-vscode-r-webview-find.py`
- Restore: `python3 scripts/patch-vscode-r-webview-find.py --restore`

### `editor.retired-local-target-comments-fix`

- Script: [`fix-retired-local-target-comments.py`](fix-retired-local-target-comments.py)
- Purpose: remove obsolete comments in VS Code/Cursor User settings that point at retired `local/` editor target/template files.
- Preview: `python3 scripts/fix-retired-local-target-comments.py --dry-run`
- Apply: `python3 scripts/fix-retired-local-target-comments.py --write --backup`
- Test: `python3 scripts/fix-retired-local-target-comments.py --self-test`

### `cursor.hidden-agent-views-fix`

- Script: [`fix-cursor-hidden-agent-views.py`](fix-cursor-hidden-agent-views.py)
- Docs: [`fix-cursor-hidden-agent-views.md`](fix-cursor-hidden-agent-views.md)
- Purpose: restore hidden Claude Code and Codex view containers in a Cursor workspace `state.vscdb`.
- Preview: `python3 scripts/fix-cursor-hidden-agent-views.py --db "/path/to/state.vscdb" --dry-run`
- Apply: `python3 scripts/fix-cursor-hidden-agent-views.py --db "/path/to/state.vscdb"`

### `codex.git-fsmonitor-env-patch`

- Script: [`patch-codex-git-fsmonitor-env.sh`](patch-codex-git-fsmonitor-env.sh)
- Docs: [`patch-codex-git-fsmonitor-env.md`](patch-codex-git-fsmonitor-env.md)
- Purpose: set `CODEX_APPLY_GIT_CFG=0` for the macOS GUI session to reduce Codex-created Git fsmonitor artifacts under Dropbox.
- Status: `bash scripts/patch-codex-git-fsmonitor-env.sh status [repo]`
- Apply: `bash scripts/patch-codex-git-fsmonitor-env.sh apply`
- Remove: `bash scripts/patch-codex-git-fsmonitor-env.sh remove`
- Fallback blocker: `bash scripts/patch-codex-git-fsmonitor-env.sh blocker-apply /path/to/repo`
