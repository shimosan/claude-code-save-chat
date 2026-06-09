#!/usr/bin/env python3
"""Set top-level JSONC object keys while preserving unrelated text.

This helper is intentionally narrow. It edits only top-level object properties,
which is the shape used by VS Code / Cursor User settings and argv JSONC files.

Examples:
    python3 scripts/config-jsonc-set-keys.py ~/.cursor/argv.json --dry-run --set locale '"en"'
    python3 scripts/config-jsonc-set-keys.py ~/.cursor/argv.json --write --backup --set locale '"en"'
    python3 scripts/config-jsonc-set-keys.py settings.json --write --backup --set editor.fontSize 14
    python3 scripts/config-jsonc-set-keys.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Member:
    key: str
    key_start: int
    key_end: int
    value_start: int
    value_end: int
    comma_index: int | None


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def expand(path: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def decode_string(text: str, start: int) -> tuple[str, int]:
    assert text[start] == '"'
    i = start + 1
    escaped = False
    while i < len(text):
        ch = text[i]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            raw = text[start : i + 1]
            return json.loads(raw), i + 1
        i += 1
    raise ValueError(f"unterminated string at byte {start}")


def skip_ws_comments(text: str, i: int, end: int | None = None) -> int:
    end = len(text) if end is None else end
    while i < end:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("//", i):
            i += 2
            while i < end and text[i] not in "\r\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ValueError(f"unterminated block comment at byte {i}")
            i = j + 2
            continue
        break
    return i


def find_top_object(text: str) -> tuple[int, int]:
    start = skip_ws_comments(text, 0)
    if start >= len(text) or text[start] != "{":
        raise ValueError("JSONC document must start with a top-level object")

    depth = 0
    i = start
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if text.startswith("//", i):
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ValueError(f"unterminated block comment at byte {i}")
            i = j + 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                trailer = skip_ws_comments(text, i + 1)
                if trailer != len(text):
                    raise ValueError("unexpected non-comment text after top-level object")
                return start, i
        i += 1
    raise ValueError("unterminated top-level object")


def find_value_end(text: str, start: int, top_end: int) -> tuple[int, int | None]:
    depth = 0
    i = start
    in_string = False
    escaped = False
    while i < top_end:
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if text.startswith("//", i):
            i += 2
            while i < top_end and text[i] not in "\r\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0 or j >= top_end:
                raise ValueError(f"unterminated block comment at byte {i}")
            i = j + 2
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            if depth == 0:
                raise ValueError(f"unexpected closing delimiter at byte {i}")
            depth -= 1
        elif ch == "," and depth == 0:
            return rstrip_ws(text, start, i), i
        i += 1
    return rstrip_ws(text, start, top_end), None


def rstrip_ws(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1].isspace():
        end -= 1
    return end


def parse_members(text: str) -> tuple[int, int, list[Member]]:
    top_start, top_end = find_top_object(text)
    members: list[Member] = []
    i = top_start + 1
    while True:
        i = skip_ws_comments(text, i, top_end)
        if i >= top_end:
            return top_start, top_end, members
        if text[i] == ",":
            i += 1
            continue
        if text[i] != '"':
            raise ValueError(f"expected top-level string key at byte {i}")

        key_start = i
        key, key_end = decode_string(text, i)
        i = skip_ws_comments(text, key_end, top_end)
        if i >= top_end or text[i] != ":":
            raise ValueError(f"expected ':' after key {key!r}")
        i = skip_ws_comments(text, i + 1, top_end)
        value_start = i
        value_end, comma_index = find_value_end(text, value_start, top_end)
        members.append(Member(key, key_start, key_end, value_start, value_end, comma_index))
        i = comma_index + 1 if comma_index is not None else value_end


def column_at(text: str, index: int) -> int:
    line_start = text.rfind("\n", 0, index) + 1
    return index - line_start


def line_indent_at(text: str, index: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    i = line_start
    while i < len(text) and text[i] in " \t":
        i += 1
    return text[line_start:i]


def close_indent(text: str, top_end: int) -> str:
    return line_indent_at(text, top_end)


def member_indent(text: str, members: list[Member], top_end: int) -> str:
    if members:
        return line_indent_at(text, members[0].key_start)
    return close_indent(text, top_end) + "  "


def render_value(value: Any, base_column: int) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2)
    if "\n" not in rendered:
        return rendered
    indent = " " * base_column
    return rendered.replace("\n", "\n" + indent)


def render_member(key: str, value: Any, indent: str) -> str:
    key_text = json.dumps(key, ensure_ascii=False)
    value_text = render_value(value, len(indent) + len(key_text) + 2)
    return f"{indent}{key_text}: {value_text}"


def parse_updates(pairs: list[list[str]]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for key, raw in pairs:
        if key in updates:
            raise ValueError(f"duplicate update key: {key}")
        try:
            updates[key] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--set {key}: value is not valid JSON: {raw}") from exc
    return updates


def set_keys_text(text: str, updates: dict[str, Any]) -> str:
    if not updates:
        return text

    _top_start, top_end, members = parse_members(text)
    by_key: dict[str, Member] = {}
    for member in members:
        if member.key in by_key:
            raise ValueError(f"duplicate top-level key in file: {member.key}")
        by_key[member.key] = member

    replacements: list[tuple[int, int, str]] = []
    missing: list[tuple[str, Any]] = []

    for key, value in updates.items():
        member = by_key.get(key)
        if member is None:
            missing.append((key, value))
            continue
        replacements.append(
            (
                member.value_start,
                member.value_end,
                render_value(value, column_at(text, member.value_start)),
            )
        )

    if missing:
        indent = member_indent(text, members, top_end)
        close = close_indent(text, top_end)
        new_lines = [render_member(key, value, indent) for key, value in missing]
        insertion = "\n" + ",\n".join(new_lines) + "\n" + close
        replacements.append((top_end, top_end, insertion))
        if members and members[-1].comma_index is None:
            replacements.append((members[-1].value_end, members[-1].value_end, ","))

    out = text
    for start, end, replacement in sorted(replacements, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out


def strip_jsonc(text: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ValueError(f"unterminated block comment at byte {i}")
            i = j + 2
            continue
        out.append(ch)
        i += 1
    return strip_trailing_commas("".join(out))


def strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] in "]}":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def validate_jsonc(text: str) -> None:
    json.loads(strip_jsonc(text))


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_fixture(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_jsonc(text: str):
    return json.loads(strip_jsonc(text))


def self_test_update_scalar_preserves_comments(tmp: Path) -> None:
    target = tmp / "argv.json"
    write_fixture(
        target,
        """{
  // Cursor UI language
  "locale": "ja",
  "window.zoomLevel": 1,
}
""",
    )

    result = set_keys_text(target.read_text(encoding="utf-8"), {"locale": "en"})
    data = load_jsonc(result)
    assert data["locale"] == "en"
    assert data["window.zoomLevel"] == 1
    assert "// Cursor UI language" in result


def self_test_add_key_to_object_without_trailing_comma(tmp: Path) -> None:
    target = tmp / "settings.json"
    write_fixture(
        target,
        """{
  "editor.fontSize": 14
}
""",
    )

    result = set_keys_text(target.read_text(encoding="utf-8"), {"editor.wordWrap": "on"})
    data = load_jsonc(result)
    assert data["editor.fontSize"] == 14
    assert data["editor.wordWrap"] == "on"
    assert '"editor.fontSize": 14,' in result


def self_test_update_object_value(tmp: Path) -> None:
    target = tmp / "settings.json"
    write_fixture(
        target,
        """{
  "workbench.colorCustomizations": {
    "editor.background": "#000000"
  },
  "editor.fontSize": 14,
}
""",
    )

    result = set_keys_text(
        target.read_text(encoding="utf-8"),
        {
            "workbench.colorCustomizations": {
                "editor.background": "#111111",
                "sideBar.background": "#222222",
            }
        },
    )
    data = load_jsonc(result)
    assert data["workbench.colorCustomizations"]["editor.background"] == "#111111"
    assert data["workbench.colorCustomizations"]["sideBar.background"] == "#222222"
    assert data["editor.fontSize"] == 14


def self_test_write_backup_and_create(tmp: Path) -> None:
    target = tmp / "new" / "argv.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(target, set_keys_text("{\n}\n", {"locale": "en"}))
    data = load_jsonc(target.read_text(encoding="utf-8"))
    assert data["locale"] == "en"
    assert not list(target.parent.glob("argv.json.bak.*"))

    backup = target.with_name(f"{target.name}.bak.self-test")
    shutil.copy2(target, backup)
    write_atomic(target, set_keys_text(target.read_text(encoding="utf-8"), {"locale": "ja"}))
    data = load_jsonc(target.read_text(encoding="utf-8"))
    assert data["locale"] == "ja"
    assert load_jsonc(backup.read_text(encoding="utf-8"))["locale"] == "en"


def self_test_duplicate_key_fails(tmp: Path) -> None:
    target = tmp / "settings.json"
    write_fixture(
        target,
        """{
  "locale": "ja",
  "locale": "en"
}
""",
    )

    try:
        set_keys_text(target.read_text(encoding="utf-8"), {"locale": "en"})
    except ValueError as exc:
        assert "duplicate top-level key" in str(exc)
    else:
        raise AssertionError("duplicate key did not fail")


def run_self_test() -> int:
    tests = [
        self_test_update_scalar_preserves_comments,
        self_test_add_key_to_object_without_trailing_comma,
        self_test_update_object_value,
        self_test_write_backup_and_create,
        self_test_duplicate_key_fails,
    ]
    with tempfile.TemporaryDirectory(prefix="config-jsonc-set-keys-test-") as tmpdir:
        tmp = Path(tmpdir)
        for test in tests:
            test_dir = tmp / test.__name__
            test_dir.mkdir()
            test(test_dir)
            print(f"ok {test.__name__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="set top-level JSONC keys")
    parser.add_argument("path", nargs="?", help="JSONC file to update")
    parser.add_argument("--set", nargs=2, metavar=("KEY", "JSON"), action="append", default=[])
    parser.add_argument("--dry-run", action="store_true", help="print updated text to stdout")
    parser.add_argument("--write", action="store_true", help="write updated text back to the file")
    parser.add_argument("--backup", action="store_true", help="create <file>.bak.<timestamp> before writing")
    parser.add_argument("--create", action="store_true", help="create a missing file as an empty object")
    parser.add_argument("--self-test", action="store_true", help="run non-destructive temporary-file tests")
    args = parser.parse_args(argv)

    if args.self_test:
        if args.path or args.set or args.dry_run or args.write or args.backup or args.create:
            parser.error("--self-test cannot be combined with set arguments")
        return run_self_test()

    if not args.path:
        parser.error("path is required unless --self-test is used")

    if args.dry_run == args.write:
        parser.error("specify exactly one of --dry-run or --write")

    path = expand(args.path)
    updates = parse_updates(args.set)

    if path.exists():
        original = path.read_text(encoding="utf-8-sig")
    elif args.create:
        original = "{\n}\n"
    else:
        raise SystemExit(f"error: file does not exist: {path}")

    updated_text = set_keys_text(original, updates)
    validate_jsonc(updated_text)

    if args.dry_run:
        sys.stdout.write(updated_text)
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    if args.backup and path.exists():
        backup = path.with_name(f"{path.name}.bak.{ts()}")
        shutil.copy2(path, backup)
        print(backup)
    write_atomic(path, updated_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
