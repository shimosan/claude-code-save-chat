# `patch-cursor-agent-worker-disable.py`

Disable Cursor's built-in `anysphere.cursor-agent-worker` extension by adding it to Cursor's global disabled extension list.

## When To Use

Use this only when Cursor repeatedly shows a `Restart Extension` / `Reload Window` prompt or badge for the built-in `cursor-agent-worker` extension and the Cursor UI does not offer a normal Disable action.

This is an unofficial local patch. It changes Cursor user state, not installed application files.

### Status (likely unnecessary on Cursor 3.8.11+)

Cursor staff confirmed this as a "known, purely cosmetic issue" (2026-05-29) and announced a fix in Cursor 3.8 (2026-06-17). v3.8.11 (2026-06-18) is a *partial* fix: the devcontainer prompt is gone, but some users still report the local `INSTALLED` prompt persisting. See the [Cursor forum thread](https://forum.cursor.com/t/cursor-v3-6-21-caught-in-loop-for-cursor-agent-worker-reload-window/161933).

As of 2026-06-20, removing the patch under v3.8.11 on the machines tested did **not** bring the reload loop back, so on 3.8.11+ this patch is normally unnecessary. The script/recipe is kept anyway because the upstream fix is incomplete — re-apply with `--apply` if the loop returns and the UI still offers no Disable action.

## What It Changes

The script edits Cursor's global storage database:

```text
~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
```

It updates `ItemTable` key:

```text
extensionsIdentifiers/disabled
```

and adds or removes this JSON entry:

```json
{"id":"anysphere.cursor-agent-worker"}
```

It does not modify installed Cursor application files or extension files.

## Safety

Quit Cursor completely before applying or removing the patch. Do not run write commands from a Cursor integrated terminal.

If Cursor is running, write commands stop with instructions to quit Cursor and rerun from Terminal.app, iTerm2, or another non-Cursor terminal. This matters because Cursor can overwrite `state.vscdb` on exit.

Before writing, the script creates a SQLite-consistent backup with `sqlite3.Connection.backup()`:

```text
state.vscdb.bak.<YYYYmmdd-HHMMSS>
```

This avoids the weak `cp state.vscdb ...` pattern when SQLite WAL files are present.

## Usage

Check current state:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --status
```

Preview disable without writing:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --apply --dry-run
```

Disable `cursor-agent-worker`:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --apply
```

Re-enable it:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --remove
```

Use a non-default DB:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --db "/path/to/state.vscdb" --status
```

## Expected Impact

Normal Cursor chat and agent use has been observed to keep working with this patch applied. If any Cursor agent feature behaves unexpectedly, remove the patch and restart Cursor before debugging.

Features that may be unavailable while this patch is applied:

- local worker or background-agent features that depend on `cursor-agent-worker`
- Cursor CLI features that depend on `cursor-agent-worker`

If behavior around those features matters, remove the patch and restart Cursor before debugging.

## Restore

Preferred restore:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --remove
```

If the DB must be restored from backup, quit Cursor completely, replace `state.vscdb` with the chosen `state.vscdb.bak.<timestamp>`, then restart Cursor.

## Test

Run the non-destructive self-test:

```bash
python3 scripts/patch-cursor-agent-worker-disable.py --self-test
```
