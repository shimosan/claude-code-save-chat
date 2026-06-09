#!/usr/bin/env python3
"""Remove retired local-target-template comments from editor User settings.

This is a comment-only cleanup helper for old Cursor / VS Code JSONC settings
that mentioned retired ``local/`` editor templates. It does not patch setting
values and it does not make ``local/`` a target-state source.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


REPLACEMENTS = {
    "（雛形 ~/Dropbox/library/claude/local/crossnote-style.less）": "",
    "（雛形 ~/Dropbox/library/claude/local/cursor-markdown-preview.css）": "",
    "（雛形 ~/Dropbox/library/claude/local/cursor-settings.json）": "",
    "（雛形 ~/Dropbox/library/claude/local/cursor-settings.win.json）": "",
}

RETIRED_PATH_MARKERS = (
    "local/crossnote-style.less",
    "local/cursor-markdown-preview.css",
    "local/cursor-settings.json",
    "local/cursor-settings.win.json",
)


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def load_jsonc_validator():
    helper = Path(__file__).with_name("config-jsonc-set-keys.py")
    spec = importlib.util.spec_from_file_location("config_jsonc_set_keys", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load JSONC validator from {helper}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.validate_jsonc


def default_paths(target: str) -> list[Path]:
    home = Path.home()
    paths: list[Path] = []
    is_windows = os.name == "nt"

    if target in {"cursor", "all"}:
        if is_windows:
            appdata = os.environ.get("APPDATA")
            if appdata:
                paths.append(Path(appdata) / "Cursor" / "User" / "settings.json")
        else:
            paths.append(home / "Library" / "Application Support" / "Cursor" / "User" / "settings.json")

    if target in {"code", "all"}:
        if is_windows:
            appdata = os.environ.get("APPDATA")
            if appdata:
                paths.append(Path(appdata) / "Code" / "User" / "settings.json")
        else:
            paths.append(home / "Library" / "Application Support" / "Code" / "User" / "settings.json")

    return paths


def patch_text(text: str) -> tuple[str, list[str]]:
    patched = text
    applied: list[str] = []
    for old, new in REPLACEMENTS.items():
        if old in patched:
            patched = patched.replace(old, new)
            applied.append(old)
    return patched, applied


def remaining_markers(text: str) -> list[str]:
    return [marker for marker in RETIRED_PATH_MARKERS if marker in text]


def patch_file(path: Path, *, write: bool, backup: bool, validate_jsonc) -> tuple[bool, list[str], list[str]]:
    original = path.read_text(encoding="utf-8-sig")
    original_remaining = remaining_markers(original)
    patched, applied = patch_text(original)
    validate_jsonc(patched)
    remaining = remaining_markers(patched)
    changed = patched != original

    if write and changed:
        if backup:
            backup_path = path.with_name(f"{path.name}.bak.{ts()}")
            shutil.copy2(path, backup_path)
            print(f"backup: {backup_path}")
        path.write_text(patched, encoding="utf-8")

    return changed, applied, remaining if changed else original_remaining


def run_self_test(validate_jsonc) -> int:
    sample = """{
    // 配色本体は ~/.local/state/crossnote/style.less（雛形 ~/Dropbox/library/claude/local/crossnote-style.less）。
    "markdown-preview-enhanced.previewTheme": "github-dark.css"
}
"""
    patched, applied = patch_text(sample)
    assert applied
    assert "local/crossnote-style.less" not in patched
    assert "配色本体は ~/.local/state/crossnote/style.less。" in patched
    validate_jsonc(patched)

    with tempfile.TemporaryDirectory(prefix="retired-local-target-comments-") as tmp:
        target = Path(tmp) / "settings.json"
        target.write_text(sample, encoding="utf-8")
        changed, _, remaining = patch_file(target, write=True, backup=True, validate_jsonc=validate_jsonc)
        assert changed
        assert not remaining
        assert list(Path(tmp).glob("settings.json.bak.*"))
        assert "local/crossnote-style.less" not in target.read_text(encoding="utf-8")

    print("ok self-test")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="remove retired local-template comments from editor settings JSONC")
    parser.add_argument("--target", choices=["cursor", "code", "all"], default="cursor")
    parser.add_argument("--path", action="append", default=[], help="explicit settings.json path; may be repeated")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    validate_jsonc = load_jsonc_validator()

    if args.self_test:
        return run_self_test(validate_jsonc)

    if args.dry_run == args.write:
        parser.error("specify exactly one of --dry-run or --write")

    paths = [Path(os.path.expanduser(p)) for p in args.path] if args.path else default_paths(args.target)
    if not paths:
        parser.error("no target paths resolved; pass --path")

    failures = 0
    for path in paths:
        if not path.exists():
            print(f"skip missing: {path}")
            continue
        changed, applied, remaining = patch_file(path, write=args.write, backup=args.backup, validate_jsonc=validate_jsonc)
        action = "would patch" if args.dry_run and changed else "patched" if args.write and changed else "no change"
        print(f"{action}: {path}")
        for item in applied:
            print(f"  removed: {item}")
        if remaining:
            failures += 1
            print("  remaining retired path markers require manual review:")
            for marker in remaining:
                print(f"    {marker}")
        elif not changed:
            print("  retired local-target markers: none")

    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
