#!/usr/bin/env python3
"""Tame Markdown Preview Enhanced (MPE) trackpad pinch-zoom sensitivity.

Background:
  The MPE preview (extension `shd101wyy.markdown-preview-enhanced`) renders in a
  webview and installs its own `wheel` listener that zooms whenever `ctrlKey` or
  `metaKey` is held. On macOS a trackpad *pinch* gesture is delivered to Chromium
  as a stream of `wheel` events with `ctrlKey: true`. MPE's handler steps the zoom
  by a FIXED amount per event and ignores the event's deltaY magnitude, so a single
  light pinch fires dozens of events and instantly slams the zoom to its min (0.2)
  or max (5.0). Neither MPE nor VS Code/Cursor exposes a setting to change this.

What this script does (two edits in `crossnote/webview/preview.js`):
  1. Throttle the wheel-zoom handler so it steps at most once per --throttle-ms
     milliseconds (a quick brush = at most one step; a deliberate pinch still
     zooms gradually). A unique marker `__mpezw` is injected so the patch is
     detectable and re-appliable.
  2. Shrink the per-step zoom increment from the stock 0.1 to --step (default
     0.01, i.e. 10x finer) so the zoom looks nearly continuous instead of chunky.
  The min/max clamps (0.2 / 5.0) and the keyboard Cmd -/=/0 shortcuts are kept.

Notes:
  - Idempotent: re-running updates the throttle/step values in place; running with
    the same values is a no-op. The regexes match MPE's minified identifier names
    generically (via backreferences), so they survive across MPE versions as long
    as the code structure is unchanged.
  - Makes a one-time byte-for-byte `preview.js.orig` backup (restore with --restore).
  - Reverted by extension updates -- just re-run it afterwards. To make the patch
    persist, disable Auto Update for MPE (Extensions panel -> right-click MPE ->
    uncheck "Auto Update"), or set `"extensions.autoUpdate": false` globally.
  - After patching or restoring, run "Developer: Reload Window" in the editor.
  - Cross-platform: scans the extension directories of VS Code, VS Code Insiders,
    VSCodium and Cursor under the home directory. Override with --extensions-dir
    or the $VSCODE_EXTENSIONS environment variable.

Usage:
  python3 patch-mpe-zoom-sensitivity.py                    # apply (step .01, 20ms)
  python3 patch-mpe-zoom-sensitivity.py --step .02 --throttle-ms 30
  python3 patch-mpe-zoom-sensitivity.py --status          # report current state
  python3 patch-mpe-zoom-sensitivity.py --dry-run         # show what would change
  python3 patch-mpe-zoom-sensitivity.py --restore         # restore from .orig
  python3 patch-mpe-zoom-sensitivity.py --extensions-dir /path/to/extensions
"""
import argparse
import glob
import os
import re
import shutil
import sys

EXT_GLOB = "shd101wyy.markdown-preview-enhanced-*"
TARGET_REL = os.path.join("crossnote", "webview", "preview.js")

# Common per-user extension directories across VS Code variants.
DEFAULT_EXT_ROOTS = [
    "~/.vscode/extensions",
    "~/.vscode-insiders/extensions",
    "~/.vscode-oss/extensions",   # VSCodium
    "~/.cursor/extensions",       # Cursor
]

# Stock wheel-zoom handler (minified identifier names captured generically):
#   let F1=H1=>{(H1.ctrlKey||H1.metaKey)&&(H1.preventDefault(),H1.stopPropagation(),
#   H1.deltaY<0?_1():xt())};return document.addEventListener("wheel",F1,{passive:!1,capture:!0})
HANDLER_ORIG = re.compile(
    r'let (?P<hv>\w+)=(?P<ev>\w+)=>\{'
    r'\((?P=ev)\.ctrlKey\|\|(?P=ev)\.metaKey\)&&\('
    r'(?P=ev)\.preventDefault\(\),(?P=ev)\.stopPropagation\(\),'
    r'(?P=ev)\.deltaY<0\?(?P<zin>\w+)\(\):(?P<zout>\w+)\(\)\)\};'
    r'return document\.addEventListener\("wheel",(?P=hv),'
    r'\{passive:!1,capture:!0\}\)'
)

# Our throttled form (with the __mpezw marker), used to detect / re-apply.
HANDLER_PATCHED = re.compile(
    r'let __mpezw=0,(?P<hv>\w+)=(?P<ev>\w+)=>\{'
    r'if\((?P=ev)\.ctrlKey\|\|(?P=ev)\.metaKey\)\{'
    r'(?P=ev)\.preventDefault\(\);(?P=ev)\.stopPropagation\(\);'
    r'var __mpezt=Date\.now\(\);if\(__mpezt-__mpezw<(?P<thr>\d+)\)return;'
    r'__mpezw=__mpezt;(?P=ev)\.deltaY<0\?(?P<zin>\w+)\(\):(?P<zout>\w+)\(\)\}\};'
    r'return document\.addEventListener\("wheel",(?P=hv),'
    r'\{passive:!1,capture:!0\}\)'
)

# Per-step increments (numeric captured so any current value re-applies cleanly):
#   f1(F1=>Math.min(F1+.1,5))   /   f1(F1=>Math.max(F1-.1,.2))
STEP_IN = re.compile(
    r'(?P<f>\w+)\((?P<p>\w+)=>Math\.min\((?P=p)\+(?P<n>[\d.]+),5\)\)'
)
STEP_OUT = re.compile(
    r'(?P<f>\w+)\((?P<p>\w+)=>Math\.max\((?P=p)-(?P<n>[\d.]+),\.2\)\)'
)


def js_num(x):
    """Format a number the way minified JS would (e.g. 0.01 -> '.01')."""
    s = ("%g" % float(x))
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s


def extension_roots(cli_dir):
    if cli_dir:
        return [cli_dir]
    env = os.environ.get("VSCODE_EXTENSIONS")
    if env:
        return [env]
    return [os.path.expanduser(p) for p in DEFAULT_EXT_ROOTS]


def find_targets(cli_dir):
    paths = []
    for root in extension_roots(cli_dir):
        paths.extend(glob.glob(os.path.join(root, EXT_GLOB, TARGET_REL)))
    return sorted(set(paths))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def describe(text):
    """Return a short human description of the current handler/step state."""
    if HANDLER_ORIG.search(text):
        handler = "stock (no throttle)"
    else:
        mp = HANDLER_PATCHED.search(text)
        handler = ("throttled @ %sms" % mp["thr"]) if mp else "UNKNOWN"
    mi, mo = STEP_IN.search(text), STEP_OUT.search(text)
    step = mi["n"] if mi else "?"
    step_out = mo["n"] if mo else "?"
    same = " " if step == step_out else " in=%s out=%s " % (step, step_out)
    step_str = ("step %s" % step) if step == step_out else ("step%s" % same)
    return "handler: %s | %s" % (handler, step_str)


def status(path):
    print("  " + describe(read(path)))
    return False


def restore(path):
    orig = path + ".orig"
    if not os.path.exists(orig):
        print(f"  [skip] no backup found: {orig}")
        return False
    shutil.copy2(orig, path)
    print(f"  [restored] {path} from .orig")
    return True


def apply_fix(path, step, throttle, dry_run=False):
    text = read(path)
    print("  before: " + describe(text))
    new = text

    # --- 1. throttle the wheel handler ---
    if HANDLER_ORIG.search(new):
        def _repl(m):
            hv, ev, zin, zout = m["hv"], m["ev"], m["zin"], m["zout"]
            return (
                f'let __mpezw=0,{hv}={ev}=>{{if({ev}.ctrlKey||{ev}.metaKey){{'
                f'{ev}.preventDefault();{ev}.stopPropagation();'
                f'var __mpezt=Date.now();if(__mpezt-__mpezw<{throttle})return;'
                f'__mpezw=__mpezt;{ev}.deltaY<0?{zin}():{zout}()}}}};'
                f'return document.addEventListener("wheel",{hv},'
                f'{{passive:!1,capture:!0}})'
            )
        new, n = HANDLER_ORIG.subn(_repl, new, count=1)
    elif HANDLER_PATCHED.search(new):
        # already throttled -> just update the throttle value
        new = HANDLER_PATCHED.sub(
            lambda m: m.group(0).replace(
                "__mpezw<%s)" % m["thr"], "__mpezw<%d)" % throttle, 1),
            new, count=1)
    else:
        print("  [warn] wheel handler not found (MPE layout changed?)")

    # --- 2. shrink the per-step increment ---
    sn = js_num(step)
    new, ni = STEP_IN.subn(
        lambda m: f'{m["f"]}({m["p"]}=>Math.min({m["p"]}+{sn},5))', new, count=1)
    new, no = STEP_OUT.subn(
        lambda m: f'{m["f"]}({m["p"]}=>Math.max({m["p"]}-{sn},.2))', new, count=1)
    if ni == 0 or no == 0:
        print("  [warn] zoom step expression not found (MPE layout changed?)")

    if new == text:
        print("  [clean] already at requested values; nothing to do")
        return False

    print("  after:  " + describe(new))
    if dry_run:
        print("  [dry-run] no changes written")
        return False

    orig = path + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(path, orig)
        print(f"  [backup] wrote {orig}")

    write(path, new)
    print("  [done] patched")
    return True


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--step", type=float, default=0.01,
                    help="per-step zoom increment (default 0.01; stock is 0.1)")
    ap.add_argument("--throttle-ms", type=int, default=20, dest="throttle",
                    help="min milliseconds between zoom steps (default 20)")
    ap.add_argument("--status", action="store_true",
                    help="report the current handler/step state and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change without writing")
    ap.add_argument("--restore", action="store_true",
                    help="restore preview.js from the .orig backup")
    ap.add_argument("--extensions-dir", metavar="DIR",
                    help="path to the extensions directory to scan")
    args = ap.parse_args()

    paths = find_targets(args.extensions_dir)
    if not paths:
        roots = ", ".join(extension_roots(args.extensions_dir))
        print(f"No Markdown Preview Enhanced install found under: {roots}",
              file=sys.stderr)
        print("Use --extensions-dir to point at your extensions directory.",
              file=sys.stderr)
        return 1

    changed = False
    for p in paths:
        print(p)
        if args.restore:
            changed |= restore(p)
        elif args.status:
            status(p)
        else:
            changed |= apply_fix(p, args.step, args.throttle,
                                 dry_run=args.dry_run)

    if changed and not args.dry_run:
        print('\n>>> Run "Developer: Reload Window" in the editor to apply.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
