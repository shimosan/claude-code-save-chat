# `patch-codex-sidebar-icon.py`

Give the **Codex** extension's views (`openai.chatgpt`) a branded icon, so that a
Codex panel relocated onto the Activity Bar shows the Codex blossom instead of a
generic placeholder.

## Problem

Since Cursor 3.15.5 / 3.15.6, an extension can no longer register a view
container in the Secondary Side Bar; that area is reserved for Cursor's own agent
UI. Codex's panel therefore loses its home and falls back to a collapsed section
at the bottom of the Explorer.

The usual workaround is to give it an Activity Bar entry of its own:

```text
Cmd+Shift+P -> View: Move View -> Codex -> New Side Bar Entry
```

That works, but the new icon is VS Code's generic `default-view-icon` rather than
the Codex blossom.

### Cause

Codex declares its icon on the **view containers**, not on the **views**:

```json
"viewsContainers": {
  "activitybar":      [{ "id": "codexViewContainer",          "icon": "resources/blossom-white.svg", ... }],
  "secondarySidebar": [{ "id": "codexSecondaryViewContainer", "icon": "resources/blossom-white.svg", ... }]
},
"views": {
  "codexSecondaryViewContainer": [
    { "id": "chatgpt.sidebarSecondaryView", "type": "webview", "name": "Codex", "when": "..." }
  ]
}
```

When a view is moved into a user-created container, VS Code builds that
container's icon from the **view's** `icon` field. Codex's views declare none, so
the container falls back to `default-view-icon`. The container declarations are
never consulted, because neither of them is in play.

Claude Code is not affected in the same way: it registers an extra Activity Bar
container (`claude-sessions-sidebar`) whose `when` clause does not depend on
Secondary Side Bar support, so its own icon survives.

## What It Changes

One structural edit in the extension's `package.json`: for every view container
that declares an icon, the icon is copied down to each of that container's views
that has none. The new key is placed right after `name`.

```json
{ "id": "chatgpt.sidebarSecondaryView", "type": "webview", "name": "Codex",
  "icon": "resources/blossom-white.svg", "when": "!chatgpt.doesNotSupportSecondarySidebar" }
```

Nothing else is touched. No `when` clause, container, or command is modified, so
the extension's own behaviour is unchanged; only the icon used for a relocated
view is affected.

The rule is generic rather than hardcoded to one view id, so it keeps working if
Codex renames or adds views. It also works for other extensions with the same
shape via `--extension`.

## Usage

From this repository:

```bash
python3 scripts/patch-codex-sidebar-icon.py
```

Then reload the editor window (`Developer: Reload Window`).

Report which views still lack an icon, without writing:

```bash
python3 scripts/patch-codex-sidebar-icon.py --status
```

Preview the change:

```bash
python3 scripts/patch-codex-sidebar-icon.py --dry-run
```

The script is idempotent: views that already declare an icon are left alone, and
re-running with nothing to do is a no-op.

If the Activity Bar icon does not change after a reload, the generated container
has cached its icon. Move the view back to the Explorer and out to
`New Side Bar Entry` again to rebuild the container.

## Restore

Restore `package.json` from the byte-for-byte `.orig` backup the script made:

```bash
python3 scripts/patch-codex-sidebar-icon.py --restore
```

Then reload the editor window.

## Version Selection

By default the script patches only the **active** version of the extension, read
from each root's `extensions.json`. Stale version directories left behind by
previous updates are skipped. To patch every installed version directory:

```bash
python3 scripts/patch-codex-sidebar-icon.py --all-versions
```

## Extension Directories

By default the script scans common per-user extension roots:

- `~/.vscode/extensions`
- `~/.vscode-insiders/extensions`
- `~/.vscode-oss/extensions` (VSCodium)
- `~/.cursor/extensions` (Cursor)

For unusual installs, point it at a specific directory:

```bash
python3 scripts/patch-codex-sidebar-icon.py --extensions-dir /path/to/extensions
```

or set `$VSCODE_EXTENSIONS`.

Note that VS Code proper does not have the Cursor symptom, since extensions can
still register Secondary Side Bar containers there. Patching a VS Code install is
harmless and only matters if the view is relocated by hand.

## Other Extensions

The container-icon-to-view rule is not Codex-specific:

```bash
python3 scripts/patch-codex-sidebar-icon.py --extension anthropic.claude-code --dry-run
```

`--icon resources/blossom-black.svg` overrides the icon instead of inheriting
each container's own.

## Extension Updates

Updating Codex installs a new version directory, so the patch is lost. Just
re-run the script and reload. Codex has shipped several builds per week, so
expect to re-run it often. To make the patch persist, disable Auto Update for
Codex (Extensions panel -> right-click **Codex** -> uncheck **Auto Update**), or
set `"extensions.autoUpdate": false` globally.

## Safety Notes

This is an unofficial local patch. It modifies installed extension files on your
machine only.

The manifest is rewritten with `json.dumps(..., indent='\t')`, which reproduces
the current Codex manifest byte for byte, so the diff is limited to the added
lines. If a future release ships a differently formatted manifest, the script
refuses to write and says so; `--force-format` accepts the reformatting.

Run `--self-test` for non-destructive tests against temporary files:

```bash
python3 scripts/patch-codex-sidebar-icon.py --self-test
```
