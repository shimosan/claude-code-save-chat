#!/usr/bin/env python3
"""Stop the vscode-R extension from activating on Find in unrelated webviews.

Background (see https://github.com/REditorSupport/vscode-R/issues/1711):
  The vscode-R extension declares the built-in command
  `editor.action.webvieweditor.showFind` in its `contributes.commands`
  (titled "R: Find in WebView"). Since VS Code 1.74.0, a contributed command
  implicitly activates the extension whenever that command is invoked. Because
  this is the *shared* built-in "find in webview" command, opening Find (Cmd/Ctrl+F)
  in ANY webview -- e.g. a Markdown preview, even in a workspace with no R files and
  on a machine where R is not installed -- activates vscode-R and shows its
  `R: (not attached)` status bar item.

What this script does:
  In the vscode-R extension's `package.json`, it removes
    - the `contributes.commands` entry for `editor.action.webvieweditor.showFind`
      (this is what causes the implicit activation), and
    - any `contributes.menus` entries referencing that command
      (the Find button on R's own help/browser webview title bars).
  The built-in webview Find still works everywhere; only the spurious activation
  and the (cosmetic) title-bar button on R's panels are removed.

Notes:
  - Idempotent: running it again when already patched does nothing.
  - Makes a one-time byte-for-byte `package.json.orig` backup (restore with --restore).
  - Reverted by extension updates -- just re-run it afterwards.
  - After patching or restoring, run "Developer: Reload Window" in VS Code.
  - Cross-platform: scans the extension directories of VS Code, VS Code Insiders,
    VSCodium and Cursor under the home directory (works on macOS / Linux / Windows).
    Override with --extensions-dir or the $VSCODE_EXTENSIONS environment variable.

Upstream issue:
  https://github.com/REditorSupport/vscode-R/issues/1711

Usage:
  python3 fix-vscode-r-webview-find.py                 # apply the patch
  python3 fix-vscode-r-webview-find.py --dry-run        # show what would change
  python3 fix-vscode-r-webview-find.py --restore        # restore from .orig
  python3 fix-vscode-r-webview-find.py --extensions-dir /path/to/extensions
"""
import argparse
import glob
import json
import os
import shutil
import sys

TARGET_CMD = "editor.action.webvieweditor.showFind"
EXT_GLOB = "reditorsupport.r-[0-9]*"  # main extension only (excludes r-syntax)

# Common per-user extension directories across VS Code variants.
DEFAULT_EXT_ROOTS = [
    "~/.vscode/extensions",
    "~/.vscode-insiders/extensions",
    "~/.vscode-oss/extensions",   # VSCodium
    "~/.cursor/extensions",       # Cursor
]


def extension_roots(cli_dir):
    """Return the list of extension directories to scan."""
    if cli_dir:
        return [cli_dir]
    env = os.environ.get("VSCODE_EXTENSIONS")
    if env:
        return [env]
    return [os.path.expanduser(p) for p in DEFAULT_EXT_ROOTS]


def find_package_jsons(cli_dir):
    paths = []
    for root in extension_roots(cli_dir):
        paths.extend(glob.glob(os.path.join(root, EXT_GLOB, "package.json")))
    return sorted(set(paths))


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent="\t")
        f.write("\n")


def restore(path):
    orig = path + ".orig"
    if not os.path.exists(orig):
        print(f"  [skip] no backup found: {orig}")
        return False
    shutil.copy2(orig, path)
    print(f"  [restored] {path} from .orig")
    return True


def apply_fix(path, dry_run=False):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    contrib = data.get("contributes", {})

    cmds = contrib.get("commands", [])
    cmd_hits = [c for c in cmds if c.get("command") == TARGET_CMD]

    menus = contrib.get("menus", {})
    menu_hits = {
        loc: [e for e in arr if e.get("command") == TARGET_CMD]
        for loc, arr in menus.items()
    }
    menu_hit_count = sum(len(v) for v in menu_hits.values())

    if not cmd_hits and menu_hit_count == 0:
        print("  [clean] already patched; nothing to do")
        return False

    print(f"  found: {len(cmd_hits)} command(s) / {menu_hit_count} menu item(s)")
    for loc, hits in menu_hits.items():
        if hits:
            print(f"    - {len(hits)} in menus['{loc}']")

    if dry_run:
        print("  [dry-run] no changes written")
        return False

    orig = path + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(path, orig)
        print(f"  [backup] wrote {orig}")

    contrib["commands"] = [c for c in cmds if c.get("command") != TARGET_CMD]
    for loc in list(menus.keys()):
        menus[loc] = [e for e in menus[loc] if e.get("command") != TARGET_CMD]

    write_json(path, data)
    print("  [done] patched")
    return True


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--restore", action="store_true",
                    help="restore package.json from the .orig backup")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change without writing")
    ap.add_argument("--extensions-dir", metavar="DIR",
                    help="path to the VS Code extensions directory to scan")
    args = ap.parse_args()

    paths = find_package_jsons(args.extensions_dir)
    if not paths:
        roots = ", ".join(extension_roots(args.extensions_dir))
        print(f"No vscode-R extension found under: {roots}", file=sys.stderr)
        print("Use --extensions-dir to point at your extensions directory.",
              file=sys.stderr)
        return 1

    changed = False
    for p in paths:
        print(p)
        if args.restore:
            changed |= restore(p)
        else:
            changed |= apply_fix(p, dry_run=args.dry_run)

    if changed and not args.dry_run:
        print('\n>>> Run "Developer: Reload Window" in VS Code to apply.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
