# `fix-cursor-hidden-agent-views.py`

Restore Claude Code and Codex view containers in a Cursor workspace when they are hidden in the workspace state database.

## When To Use

Use this only when the Cursor secondary panel should contain Claude Code or Codex views, but those views disappeared for one workspace and normal Cursor UI controls do not restore them.

This targets macOS Cursor workspace state databases such as:

```text
~/Library/Application Support/Cursor/User/workspaceStorage/<workspace-id>/state.vscdb
```

## What It Changes

The script updates selected keys in Cursor's `state.vscdb` `ItemTable`:

- shows the auxiliary bar
- hides the unified sidebar
- marks the Claude Code and Codex view containers as visible
- makes Codex the active auxiliary panel

It backs up `state.vscdb` and any `-wal` / `-shm` companions before writing.

## Usage

Quit Cursor completely first.

```bash
python3 scripts/fix-cursor-hidden-agent-views.py --db "/path/to/state.vscdb"
```

Preview current values without writing:

```bash
python3 scripts/fix-cursor-hidden-agent-views.py --db "/path/to/state.vscdb" --dry-run
```

## Restore

Restore from the `.bak-YYYYMMDD-HHMMSS` files created next to `state.vscdb`, then restart Cursor.

Note: the script intentionally does not search for the correct workspace database. Pass the target `state.vscdb` explicitly so the operator verifies the workspace before writing.
