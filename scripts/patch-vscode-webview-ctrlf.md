# `patch-vscode-webview-ctrlf.js`

Patch installed VS Code/Cursor-style webview extensions so macOS `Control-F` moves the caret forward by one character inside Claude Code and Codex chat inputs.

## Problem

Claude Code and Codex render their chat UIs inside VS Code webviews. Their prompt inputs can be `contenteditable` DOM elements rather than native macOS text fields. Chromium handles some macOS/Emacs-style editing keys there, but `Control-F` is not reliably mapped to forward-character.

Native editor surfaces such as VS Code Copilot or Cursor Agent may not show the problem because they use host-integrated input components.

## What It Changes

The script patches local installed extension assets:

- Claude Code: appends a small JavaScript block to `webview/index.js`
- Codex/OpenAI ChatGPT: adds `ctrlf-forward-char-shim.js` and loads it from `webview/index.html`

The injected handler is intentionally narrow:

- only handles `Control-F`
- only runs when focus is in an editable element
- moves the caret forward by one character
- does not modify VS Code/Cursor keybindings or user settings

## Usage

From this repository:

```bash
node scripts/patch-vscode-webview-ctrlf.js
```

Then reload the editor window:

```text
Developer: Reload Window
```

## Status And Diagnostics

List detected installs:

```bash
node scripts/patch-vscode-webview-ctrlf.js --list
```

Check patch state:

```bash
node scripts/patch-vscode-webview-ctrlf.js --status
```

Show what would change without writing files:

```bash
node scripts/patch-vscode-webview-ctrlf.js --dry-run
```

Patch all non-obsolete detected installs rather than only the latest per editor:

```bash
node scripts/patch-vscode-webview-ctrlf.js --all
```

## Restore

Remove this patch from detected installs:

```bash
node scripts/patch-vscode-webview-ctrlf.js --restore
```

Then reload the editor window.

The script also creates `.bak-YYYYMMDDHHMMSS` backups next to modified files before changing bundled extension assets.

## Extension Updates

VS Code-family editors install extensions into versioned directories. When Claude Code or Codex updates, the patched webview files may be replaced. Re-run:

```bash
node scripts/patch-vscode-webview-ctrlf.js
```

The script automatically scans common extension roots such as:

- `~/.vscode/extensions`
- `~/.cursor/extensions`
- `~/.vscode-insiders/extensions`
- `~/.vscodium/extensions`
- `~/.windsurf/extensions`
- remote/server variants such as `~/.vscode-server/extensions`

It reads `.obsolete` to avoid stale extension folders and verifies `package.json` before patching.

For unusual installs, provide extra roots with `CTRL_F_FIX_EXTENSION_ROOTS`:

```bash
CTRL_F_FIX_EXTENSION_ROOTS="$HOME/.local/share/code-server/extensions" \
  node scripts/patch-vscode-webview-ctrlf.js
```

Use the platform path delimiter for multiple roots (`:` on macOS/Linux).

## Safety Notes

This is an unofficial local patch. It modifies installed extension files on your machine only. Extension updates can remove the patch, and extension internals may change in ways that require updating the script.

Run `--dry-run` and `--status` first if you are applying it on a new machine.
