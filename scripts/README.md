# Scripts

This directory holds the library's workflow authorities (specification documents that thin platform entrypoints read at runtime) and optional utility scripts. Nothing here is deployed to machines; everything is referenced in place via `library_path`.

Each script should have a short entry here. Simple scripts can be fully documented in one or two lines in this index; scripts with non-trivial usage should have a dedicated help document.

## Available Scripts

### Workflow Authorities

- [`save-chat-core.md`](save-chat-core.md): the shared save-chat specification (note format, slug/tag rules, revision rules, wikilink scope, platform binding contract). The Claude Code command, Codex skill, and Copilot prompt are thin skins that read this file at runtime.

### Conversation History

- [`chat-list.py`](chat-list.py): deterministic, read-only browser that lists **Claude Code, Codex, Cursor, and Copilot** conversation history together, per workspace. The default lists the current workspace's merged history (newest first), one row per conversation with a `#` / start time / origin (`CC`/`CX`/`CU`/`CP` + surface, e.g. `CC/vscode` `CX/exec` `CU/cursor` `CP/cli`) / id / size / title. Each tool has multiple surfaces under one harness (Claude vscode/desktop/cli, Codex vscode/cli/exec/subagent, Cursor cursor/subagent, Copilot panel/cli). `--ws <name|path>` (repeatable / comma-separated, NFC-normalized substring or exact path; mutually exclusive with `--all-ws`) targets other workspaces and bundles rename/normalization-split directories. `--workspaces` prints a numbered per-workspace census (CC/CX/CU/CP counts, the total shown as `N (A)` where `A` = archived/hidden count, total size, span). Filter with `--title` (titles, fast) or `--grep` (full-text body search, showing matching lines), plus `--tool claude|codex|cursor|copilot` / `--since`. `--long` (`-l`) adds a model column. Sort with `--sort time|mtime|size|count|name` (default newest-first; `mtime` = last in-content activity, `size` = byte count, `count` is `--workspaces`-only) and `--reverse`. `--head/--tail N` previews each conversation. `--dump <id>` emits a conversation's full text to stdout, `--out FILE`, an editor buffer (`--open [cursor|code]`, or pipe to `cursor -` / `code -`), or raw jsonl (`--raw`). **Archived/hidden conversations are always listed (never excluded), marked `*` after origin** (`--long`: claude `*c`=Cursor-hidden `*v`=VS Code `*cv`=both, others `*`); only subagents are excluded by default (`--include-subagents`). Sources (read-only): claude `~/.claude/projects/*.jsonl`, codex `~/.codex/sqlite/state_5.sqlite` `threads`, cursor `…/Cursor/…/globalStorage/state.vscdb` (`cursorDiskKV`), copilot `…/Code/…/workspaceStorage/<hash>/chatSessions/*` + the Copilot CLI `~/.copilot/` (session-store.db + session-state/*/events.jsonl); archive flags read from each tool's local store. WAL sqlite DBs open `mode=ro` with an `immutable=1` fallback (read whether or not the app is running). Start time comes from in-file timestamps (never the OS file mtime, which Dropbox sync rewrites); sessions are de-duplicated by `(harness, id)`. The `chat-list` Claude Code command (`dotclaude/commands/chat-list.md`) and Codex skill (`dotcodex/skills/chat-list/SKILL.md`) are thin skins that resolve natural-language selectors to exact ids/paths and run this script; the script is also fully usable directly from the terminal. To expose it as a bare `chat-list` command: on macOS/Linux symlink the script into a PATH dir; on Windows the companion [`chat-list.cmd`](chat-list.cmd) wrapper (calls the adjacent `.py` via `%~dp0`) makes `<library_path>\scripts` on PATH enough. See the README's `/chat-list` section.

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
