# Scripts

This directory contains optional utility scripts that are useful outside the core `/save-chat` workflow.

Each script should have a short entry here. Simple scripts can be fully documented in one or two lines in this index; scripts with non-trivial usage should have a dedicated help document.

## Available Scripts

- [`config-update.md`](config-update.md): agent-facing public protocol for config snapshot comparison, local policy/recipe handling, proposal, approval, and handoff to apply recipes. Thin skills such as `config-manager` should delegate to this file.
- [`config-apply-recipes.md`](config-apply-recipes.md): concrete agent-facing recipes for applying approved configuration changes, including per-recipe risk metadata and the general rule for uncovered snapshot sources.
- [`config-snapshot-mac.py`](config-snapshot-mac.py): collect a read-only live configuration snapshot from a macOS machine and print JSON, write a temporary `scratch/config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json` with `--scratch`, or write the regular sync log under `log/config/` with `--log`. Refuses to run on non-macOS.
- [`config-snapshot-win.py`](config-snapshot-win.py): Windows counterpart to `config-snapshot-mac.py`, with Windows-specific paths, `where.exe`, PowerShell/Git Bash sources, and UTF-8-safe subprocess decoding. Refuses to run on non-Windows.
- [`config-log-helper.py`](config-log-helper.py): inspect `log/config/` snapshots/apply logs, find latest valid snapshots, show raw timelines with apply consistency checks, summarize N-way/latest-snapshot drift, and create apply log skeletons. Read-only except `apply-log-skeleton --write`; use `--self-test` for non-destructive fixture tests.
- [`jsonc-patch-keys.py`](jsonc-patch-keys.py): patch top-level JSONC object keys while preserving comments and unrelated text. Intended for VS Code/Cursor User settings and argv config files; use `--backup` for live config writes and `--self-test` for non-destructive fixture tests.
- [`patch-vscode-webview-ctrlf.js`](patch-vscode-webview-ctrlf.js): patch installed VS Code/Cursor-style webview extensions so macOS `Control-F` moves the caret forward by one character inside Claude Code and Codex chat inputs. See [`patch-vscode-webview-ctrlf.md`](patch-vscode-webview-ctrlf.md).
- [`fix-vscode-r-webview-find.py`](fix-vscode-r-webview-find.py): stop the vscode-R extension from implicitly activating (and showing a spurious `R: (not attached)` status bar item) when Find is opened in an unrelated webview such as a Markdown preview. Idempotent, with `--dry-run`, `--restore`, and `--extensions-dir`. See [`fix-vscode-r-webview-find.md`](fix-vscode-r-webview-find.md).
- [`patch-retired-local-target-comments.py`](patch-retired-local-target-comments.py): remove obsolete JSONC comments in VS Code/Cursor User settings that point at retired `local/` editor target/template files. Comment-only, with `--dry-run`, `--write`, `--backup`, and `--self-test`.

## Conventions

- Keep `README.md` as an index.
- For simple scripts, a short README entry is enough.
- For scripts with detailed usage, caveats, or examples, add a script-specific `.md` file.
- Prefer reversible scripts with `--dry-run`, `--status`, and restore-style commands when they modify local installed software.
