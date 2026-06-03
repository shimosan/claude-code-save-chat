# Scripts

This directory contains optional utility scripts that are useful outside the core `/save-chat` workflow.

Each script should have a short entry here. Simple scripts can be fully documented in one or two lines in this index; scripts with non-trivial usage should have a dedicated help document.

## Available Scripts

- [`patch-vscode-webview-ctrlf.js`](patch-vscode-webview-ctrlf.js): patch installed VS Code/Cursor-style webview extensions so macOS `Control-F` moves the caret forward by one character inside Claude Code and Codex chat inputs. See [`patch-vscode-webview-ctrlf.md`](patch-vscode-webview-ctrlf.md).

## Conventions

- Keep `README.md` as an index.
- For simple scripts, a short README entry is enough.
- For scripts with detailed usage, caveats, or examples, add a script-specific `.md` file.
- Prefer reversible scripts with `--dry-run`, `--status`, and restore-style commands when they modify local installed software.
