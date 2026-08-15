#!/usr/bin/env python3
"""Give the Codex sidebar view a branded icon so it survives being relocated.

Background:
  The Codex extension (`openai.chatgpt`) declares its blossom icon on its *view
  containers*, not on the views themselves:

      viewsContainers.activitybar      codexViewContainer          icon: blossom-white.svg
      viewsContainers.secondarySidebar codexSecondaryViewContainer icon: blossom-white.svg
      views.codexSecondaryViewContainer  chatgpt.sidebarSecondaryView   (no icon)

  Since Cursor 3.15.5/3.15.6 an extension can no longer register a view container
  in the Secondary Side Bar, so the Codex view falls back into the Explorer. The
  usual workaround is "View: Move View" -> "New Side Bar Entry", which puts Codex
  on the Activity Bar. But VS Code builds that generated container's icon from the
  *view's* `icon` field, and Codex's views do not declare one, so the container
  ends up with the generic `default-view-icon` instead of the Codex blossom.

What this script does (one structural edit in the extension's `package.json`):
  For every view container that declares an icon, copy that icon down to each of
  its views that has none. Nothing else is touched. After a reload, a user-created
  container built from such a view shows the extension's real icon.

Notes:
  - Idempotent: views that already declare an icon are left alone.
  - Formatting-safe: the file is only rewritten when `json.dumps(..., indent='\\t')`
    reproduces the current bytes exactly, so the diff is limited to the added
    lines. Use --force-format to accept normalization if a future release ships a
    differently formatted manifest.
  - Makes a one-time byte-for-byte `package.json.orig` backup (restore with
    --restore).
  - Reverted by extension updates -- just re-run it afterwards. To make the patch
    persist, disable Auto Update for Codex (Extensions panel -> right-click Codex
    -> uncheck "Auto Update"), or set `"extensions.autoUpdate": false` globally.
  - After patching or restoring, run "Developer: Reload Window" in the editor. If
    the Activity Bar icon does not change, the generated container has cached its
    icon: move the view back to the Explorer and out to "New Side Bar Entry" again.
  - Cross-platform: scans the extension directories of VS Code, VS Code Insiders,
    VSCodium and Cursor under the home directory. Override with --extensions-dir
    or the $VSCODE_EXTENSIONS environment variable.

Usage:
  python3 patch-codex-sidebar-icon.py                  # apply to the active version
  python3 patch-codex-sidebar-icon.py --status         # report current state
  python3 patch-codex-sidebar-icon.py --dry-run        # show what would change
  python3 patch-codex-sidebar-icon.py --restore        # restore from .orig
  python3 patch-codex-sidebar-icon.py --all-versions   # include stale version dirs
  python3 patch-codex-sidebar-icon.py --extension anthropic.claude-code
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

DEFAULT_EXTENSION_ID = "openai.chatgpt"

# Common per-user extension directories across VS Code variants.
DEFAULT_EXT_ROOTS = [
    "~/.vscode/extensions",
    "~/.vscode-insiders/extensions",
    "~/.vscode-oss/extensions",   # VSCodium
    "~/.cursor/extensions",       # Cursor
]

INDENT = "\t"


def extension_roots(cli_dir):
    if cli_dir:
        return [cli_dir]
    env = os.environ.get("VSCODE_EXTENSIONS")
    if env:
        return [env]
    return [os.path.expanduser(p) for p in DEFAULT_EXT_ROOTS]


def active_locations(root, extension_id):
    """Relative dir names marked active in the root's extensions.json."""
    index = os.path.join(root, "extensions.json")
    try:
        with open(index, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(entries, list):
        return None
    found = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ident = entry.get("identifier")
        got = ident.get("id") if isinstance(ident, dict) else None
        if got != extension_id:
            continue
        location = entry.get("relativeLocation")
        if isinstance(location, str) and location:
            found.append(location)
    return found or None


def find_targets(cli_dir, extension_id, all_versions=False):
    paths = []
    for root in extension_roots(cli_dir):
        active = None if all_versions else active_locations(root, extension_id)
        if active:
            candidates = [os.path.join(root, name) for name in active]
        else:
            candidates = glob.glob(os.path.join(root, extension_id + "-*"))
        for directory in candidates:
            manifest = os.path.join(directory, "package.json")
            if os.path.isfile(manifest):
                paths.append(manifest)
    return sorted(set(paths))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def dump(data):
    return json.dumps(data, indent=INDENT, ensure_ascii=False)


def container_icons(data):
    """Map view container id -> declared icon, across all container locations."""
    icons = {}
    containers = data.get("contributes", {}).get("viewsContainers", {})
    if not isinstance(containers, dict):
        return icons
    for group in containers.values():
        if not isinstance(group, list):
            continue
        for container in group:
            if not isinstance(container, dict):
                continue
            cid, icon = container.get("id"), container.get("icon")
            if isinstance(cid, str) and isinstance(icon, str):
                icons[cid] = icon
    return icons


def plan(data, icon_override=None):
    """Return [(container_id, view_id, icon)] for views missing an icon."""
    icons = container_icons(data)
    views = data.get("contributes", {}).get("views", {})
    if not isinstance(views, dict):
        return []
    pending = []
    for container_id, group in views.items():
        icon = icon_override or icons.get(container_id)
        if not icon or not isinstance(group, list):
            continue
        for view in group:
            if not isinstance(view, dict) or view.get("icon"):
                continue
            view_id = view.get("id")
            if isinstance(view_id, str):
                pending.append((container_id, view_id, icon))
    return pending


def apply_plan(data, icon_override=None):
    """Mutate data in place; return the list of applied (container, view, icon)."""
    pending = plan(data, icon_override)
    wanted = {(c, v): i for c, v, i in pending}
    for container_id, group in data.get("contributes", {}).get("views", {}).items():
        if not isinstance(group, list):
            continue
        for view in group:
            if not isinstance(view, dict):
                continue
            icon = wanted.get((container_id, view.get("id")))
            if icon is None:
                continue
            # Rebuild so "icon" lands next to "name" rather than after "when".
            ordered = {}
            for key, value in view.items():
                ordered[key] = value
                if key == "name":
                    ordered["icon"] = icon
            if "icon" not in ordered:
                ordered["icon"] = icon
            view.clear()
            view.update(ordered)
    return pending


def describe(data):
    views = data.get("contributes", {}).get("views", {})
    if not isinstance(views, dict):
        return "no view contributions"
    total = 0
    with_icon = 0
    for group in views.values():
        if not isinstance(group, list):
            continue
        for view in group:
            if isinstance(view, dict) and isinstance(view.get("id"), str):
                total += 1
                if view.get("icon"):
                    with_icon += 1
    if total == 0:
        return "no view contributions"
    return "views with icon: %d/%d" % (with_icon, total)


def status(path):
    data = json.loads(read(path))
    print("  version: %s | %s" % (data.get("version", "?"), describe(data)))
    for container_id, view_id, icon in plan(data):
        print("  [missing] %s / %s -> would use %s" % (container_id, view_id, icon))
    print("  backup: %s" % ("present" if os.path.exists(path + ".orig") else "none"))
    return False


def restore(path):
    orig = path + ".orig"
    if not os.path.exists(orig):
        print("  [skip] no backup found: %s" % orig)
        return False
    shutil.copy2(orig, path)
    print("  [restored] %s from .orig" % path)
    return True


def apply_fix(path, icon_override=None, dry_run=False, force_format=False):
    text = read(path)
    data = json.loads(text)
    print("  before: " + describe(data))

    faithful = dump(data) == text
    if not faithful and not force_format:
        print("  [warn] manifest formatting is not reproducible by this script;")
        print("         writing would reformat the whole file. Re-run with "
              "--force-format to accept that.")
        return False

    applied = apply_plan(data, icon_override)
    if not applied:
        print("  [clean] every view already declares an icon; nothing to do")
        return False
    for container_id, view_id, icon in applied:
        print("  [patch] %s / %s <- %s" % (container_id, view_id, icon))
    print("  after:  " + describe(data))

    if dry_run:
        print("  [dry-run] no changes written")
        return False

    orig = path + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(path, orig)
        print("  [backup] wrote %s" % orig)

    write(path, dump(data))
    print("  [done] patched")
    return True


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, actual))


def self_test():
    manifest = {
        "name": "chatgpt",
        "version": "1.2.3",
        "contributes": {
            "viewsContainers": {
                "activitybar": [
                    {"id": "cA", "title": "Codex", "icon": "resources/blossom-white.svg"}
                ],
                "secondarySidebar": [
                    {"id": "cB", "title": "Codex", "icon": "resources/blossom-white.svg"}
                ],
                "panel": [{"id": "cC", "title": "No Icon"}],
            },
            "views": {
                "cA": [{"id": "vA", "type": "webview", "name": "Codex", "when": "x"}],
                "cB": [
                    {"id": "vB", "type": "webview", "name": "Codex", "when": "!x"},
                    {"id": "vB2", "name": "Kept", "icon": "resources/other.svg"},
                ],
                "cC": [{"id": "vC", "name": "Orphan"}],
            },
        },
    }

    pending = plan(manifest)
    assert_equal(
        sorted(pending),
        [("cA", "vA", "resources/blossom-white.svg"),
         ("cB", "vB", "resources/blossom-white.svg")],
        "plan finds only iconless views under icon-bearing containers",
    )

    applied = apply_plan(manifest)
    assert_equal(len(applied), 2, "apply reports two changes")
    views = manifest["contributes"]["views"]
    assert_equal(views["cA"][0]["icon"], "resources/blossom-white.svg", "vA icon set")
    assert_equal(
        list(views["cA"][0]),
        ["id", "type", "name", "icon", "when"],
        "icon inserted after name",
    )
    assert_equal(views["cB"][1]["icon"], "resources/other.svg", "existing icon kept")
    assert_equal("icon" in views["cC"][0], False, "container without icon skipped")
    assert_equal(plan(manifest), [], "second pass is a no-op (idempotent)")

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "package.json")
        stock = {
            "version": "1.0.0",
            "contributes": {
                "viewsContainers": {"activitybar": [{"id": "c", "icon": "i.svg"}]},
                "views": {"c": [{"id": "v", "name": "N"}]},
            },
        }
        write(path, dump(stock))
        assert_equal(apply_fix(path), True, "first apply writes")
        assert_equal(os.path.exists(path + ".orig"), True, "backup created")
        assert_equal(json.loads(read(path))["contributes"]["views"]["c"][0]["icon"],
                     "i.svg", "icon persisted to disk")
        assert_equal(apply_fix(path), False, "re-apply is a no-op")
        assert_equal(restore(path), True, "restore succeeds")
        assert_equal("icon" in json.loads(read(path))["contributes"]["views"]["c"][0],
                     False, "restore brings back the stock manifest")

        rough = os.path.join(tmp, "rough.json")
        write(rough, json.dumps(stock))  # single-line, not tab-indented
        assert_equal(apply_fix(rough), False, "unfaithful formatting refuses to write")
        assert_equal(read(rough), json.dumps(stock), "refused file is untouched")
        assert_equal(apply_fix(rough, force_format=True), True, "--force-format writes")

    print("self-test: ok")
    return True


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--status", action="store_true",
                    help="report which views lack an icon and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change without writing")
    ap.add_argument("--restore", action="store_true",
                    help="restore package.json from the .orig backup")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="run non-destructive tests against temporary files")
    ap.add_argument("--extension", default=DEFAULT_EXTENSION_ID, metavar="ID",
                    help="extension id to patch (default: %s)" % DEFAULT_EXTENSION_ID)
    ap.add_argument("--icon", metavar="REL_PATH",
                    help="icon path to use instead of each container's own icon")
    ap.add_argument("--all-versions", action="store_true", dest="all_versions",
                    help="patch every installed version dir, not just the active one")
    ap.add_argument("--force-format", action="store_true", dest="force_format",
                    help="write even if it reformats the whole manifest")
    ap.add_argument("--extensions-dir", metavar="DIR", dest="extensions_dir",
                    help="path to the extensions directory to scan")
    args = ap.parse_args()

    if args.self_test:
        return 0 if self_test() else 1

    paths = find_targets(args.extensions_dir, args.extension, args.all_versions)
    if not paths:
        roots = ", ".join(extension_roots(args.extensions_dir))
        print("No %s install found under: %s" % (args.extension, roots), file=sys.stderr)
        print("Use --extensions-dir to point at your extensions directory.",
              file=sys.stderr)
        return 1

    changed = False
    for path in paths:
        print(path)
        try:
            if args.restore:
                changed |= restore(path)
            elif args.status:
                status(path)
            else:
                changed |= apply_fix(path, args.icon, args.dry_run, args.force_format)
        except ValueError as exc:
            print("  [error] could not parse manifest: %s" % exc, file=sys.stderr)
            return 1

    if changed and not args.dry_run:
        print('\n>>> Run "Developer: Reload Window" in the editor to apply.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
