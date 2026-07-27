# `patch-mpe-zoom-sensitivity.py`

Tame the trackpad pinch-zoom in the **Markdown Preview Enhanced** (MPE) preview
(`shd101wyy.markdown-preview-enhanced`) so a light pinch no longer slams the zoom
straight to its minimum or maximum.

## Problem

In the MPE preview on macOS, a small trackpad pinch makes the zoom "fly off" to
the extreme (0.2 or 5.0) almost instantly. Neither MPE nor VS Code/Cursor exposes
a setting to change this.

### Cause

MPE's preview installs its own `wheel` listener that zooms whenever `ctrlKey` or
`metaKey` is held. On macOS a trackpad **pinch** is delivered to Chromium as a
stream of `wheel` events with `ctrlKey: true`. MPE's handler steps the zoom by a
**fixed** amount per event and **ignores the event's deltaY magnitude**, so one
light pinch fires dozens of events, each adding a full step:

```js
zoomIn : f1(F1 => Math.min(F1 + .1, 5))     // +0.1 per event, max 5.0
zoomOut: f1(F1 => Math.max(F1 - .1, .2))    // -0.1 per event, min 0.2
// wheel handler: (ctrlKey||metaKey) && (deltaY<0 ? zoomIn() : zoomOut())
```

The built-in Cursor/VS Code Markdown preview does not have this problem (its
webview sets `user-scalable=no`); this is specific to MPE.

## What It Changes

Two edits in the MPE preview bundle `crossnote/webview/preview.js`:

1. **Throttle** the wheel-zoom handler to at most one step per `--throttle-ms`
   milliseconds (default 20). A quick brush = at most one step; a deliberate pinch
   still zooms gradually. A unique marker `__mpezw` is injected so the patch is
   detectable and re-appliable.
2. **Shrink the step** from the stock `0.1` to `--step` (default `0.01`, i.e. 10x
   finer) so the zoom looks nearly continuous instead of chunky.

The min/max clamps (0.2 / 5.0) and the keyboard `Cmd -/=/0` shortcuts are kept.
With the defaults (0.01 step, 20 ms) the perceived zoom speed matches the stock
0.1-per-... feel but with 1/10 the granularity.

## Usage

From this repository:

```bash
python3 scripts/patch-mpe-zoom-sensitivity.py
```

Then reload the editor window (`Developer: Reload Window`).

Report the current state (stock / throttled@Nms / step value) without writing:

```bash
python3 scripts/patch-mpe-zoom-sensitivity.py --status
```

Preview changes, or tune the feel:

```bash
python3 scripts/patch-mpe-zoom-sensitivity.py --dry-run
python3 scripts/patch-mpe-zoom-sensitivity.py --step .02 --throttle-ms 30
```

- Larger `--throttle-ms` = slower/less sensitive.
- Smaller `--step` = smoother (more continuous), but slower to cover the same range.

The script is idempotent: re-running updates the throttle/step values in place,
and running with the same values is a no-op.

## Restore

Restore `preview.js` from the byte-for-byte `.orig` backup the script made:

```bash
python3 scripts/patch-mpe-zoom-sensitivity.py --restore
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
python3 scripts/patch-mpe-zoom-sensitivity.py --extensions-dir /path/to/extensions
```

or set `$VSCODE_EXTENSIONS`.

## Extension Updates

Updating MPE reinstalls the original `preview.js`, reverting the patch. Just
re-run the script and reload. To make the patch persist, disable Auto Update for
MPE (Extensions panel -> right-click **Markdown Preview Enhanced** -> uncheck
**Auto Update**), or set `"extensions.autoUpdate": false` globally.

The regexes match MPE's minified identifier names generically (via
backreferences), so they survive across MPE versions as long as the handler /
step structure is unchanged. If MPE's layout changes, the script prints a
`[warn]` and makes no partial write; re-check with a newer regex if that happens.

## Safety Notes

This is an unofficial local patch. It modifies installed extension files on your
machine only. Run `--dry-run` (or `--status`) first when applying on a new machine.
