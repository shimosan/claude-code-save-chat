# `fix-vscode-r-webview-find.py`

Stop the vscode-R extension (`reditorsupport.r`) from activating when you open Find (`Cmd/Ctrl+F`) inside an unrelated webview, which otherwise makes a spurious `R: (not attached)` item appear in the status bar.

## Problem

You see `R: (not attached)` (shown compactly as just `R`) in the status bar even though:

- the workspace has no R files (`.R`, `.Rmd`, `.Rproj`, ...), and
- R is not even installed on the machine.

Clicking it starts R in a terminal (`r.attachActive`) rather than opening a language picker.

### Cause

The vscode-R extension declares the **built-in** command `editor.action.webvieweditor.showFind` (title "R: Find in WebView") in its `contributes.commands`. Since VS Code 1.74.0, a contributed command **implicitly activates** the extension whenever that command is invoked.

Because this is the *shared* built-in "find in webview" command, opening Find in **any** webview (e.g. a Markdown preview) activates vscode-R. Once active, `r.sessionWatcher` (default on) shows its session status bar item, which reads `R: (not attached)` when nothing is connected.

Activation events are additive and cannot be overridden by another extension, so the only fix is to remove vscode-R's own registration.

## What It Changes

In the vscode-R extension's `package.json`, the script removes:

- the `contributes.commands` entry for `editor.action.webvieweditor.showFind` (the cause of the implicit activation), and
- any `contributes.menus` entries referencing that command (the Find button on R's own help/browser webview title bars).

The built-in webview Find still works everywhere; only the spurious activation and the cosmetic title-bar button on R's own panels are removed.

## Usage

From this repository:

```bash
python3 scripts/fix-vscode-r-webview-find.py
```

Then reload the editor window:

```text
Developer: Reload Window
```

Show what would change without writing files:

```bash
python3 scripts/fix-vscode-r-webview-find.py --dry-run
```

## Restore

Restore `package.json` from the byte-for-byte `.orig` backup the script made:

```bash
python3 scripts/fix-vscode-r-webview-find.py --restore
```

Then reload the editor window.

## Extension Directories

By default the script scans common per-user extension roots:

- `~/.vscode/extensions`
- `~/.vscode-insiders/extensions`
- `~/.vscode-oss/extensions` (VSCodium)
- `~/.cursor/extensions` (Cursor)

For unusual installs, point it at a specific directory:

```bash
python3 scripts/fix-vscode-r-webview-find.py --extensions-dir /path/to/extensions
```

or set `$VSCODE_EXTENSIONS`.

## Extension Updates

Updating the vscode-R extension reinstalls the original `package.json`, reverting the patch. Just re-run the script and reload the window afterwards. The script is idempotent, so re-running it when already patched does nothing.

## Safety Notes

This is an unofficial local patch. It modifies installed extension files on your machine only. Run `--dry-run` first if you are applying it on a new machine.

## Links

- Upstream issue: [REditorSupport/vscode-R#1711](https://github.com/REditorSupport/vscode-R/issues/1711)
