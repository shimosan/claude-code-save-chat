#!/usr/bin/env python3
"""Disable Cursor's built-in cursor-agent-worker through globalStorage state."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


KEY = "extensionsIdentifiers/disabled"
EXTENSION_ID = "anysphere.cursor-agent-worker"
DEFAULT_DB = "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"


class PatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    comm: str
    args: str

    @property
    def text(self) -> str:
        return f"{self.comm} {self.args}"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def display_path(path: Path) -> str:
    try:
        home = Path.home().resolve()
        resolved = path.expanduser().resolve()
    except OSError:
        return str(path)
    try:
        return f"~/{resolved.relative_to(home)}"
    except ValueError:
        return str(path)


def run_ps() -> list[ProcessInfo] | None:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid,ppid,comm,args"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, PermissionError):
        return None
    if result.returncode != 0:
        return None

    processes: list[ProcessInfo] = []
    output = result.stdout.decode("utf-8", errors="replace")
    for line in output.splitlines()[1:]:
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        processes.append(ProcessInfo(pid=pid, ppid=ppid, comm=parts[2], args=parts[3]))
    return processes


def is_cursor_process(process: ProcessInfo) -> bool:
    text = process.text
    return (
        "Cursor.app/Contents/MacOS/Cursor" in text
        or "Cursor Helper" in text
        or "cursor-agent-worker" in text
    )


def cursor_processes(processes: list[ProcessInfo]) -> list[ProcessInfo]:
    current_pid = os.getpid()
    return [process for process in processes if process.pid != current_pid and is_cursor_process(process)]


def cursor_ancestor(processes: list[ProcessInfo]) -> ProcessInfo | None:
    by_pid = {process.pid: process for process in processes}
    seen: set[int] = set()
    pid = os.getpid()
    while pid and pid not in seen:
        seen.add(pid)
        process = by_pid.get(pid)
        if process is None:
            return None
        if is_cursor_process(process):
            return process
        pid = process.ppid
    return None


def process_warning(db: Path) -> str | None:
    processes = run_ps()
    if processes is None:
        return "\n".join(
            [
                "Cursor process state could not be inspected; write commands will be refused.",
                f"Target DB: {display_path(db)}",
                "Run from macOS Terminal.app or iTerm2 after quitting Cursor, or use --no-process-check only if you have verified Cursor is fully stopped.",
            ]
        )
    running = cursor_processes(processes)
    ancestor = cursor_ancestor(processes)
    if not running and ancestor is None:
        return None

    details: list[str] = []
    if ancestor is not None:
        details.append(f"current process appears to be running inside Cursor: pid {ancestor.pid}")
    if running:
        details.append(f"Cursor-related processes are running: {len(running)} found")

    return "\n".join(
        [
            "Cursor is running; write commands will be refused.",
            f"Target DB: {display_path(db)}",
            *details,
        ]
    )


def process_error(db: Path) -> str | None:
    warning = process_warning(db)
    if warning is None:
        return None
    if warning.startswith("Cursor process state could not be inspected"):
        heading = "ERROR: Cursor process state could not be inspected."
        reason = "This patch refuses to write unless it can verify that Cursor is fully stopped."
    else:
        heading = "ERROR: Cursor is currently running."
        reason = "If it is run while Cursor is open, Cursor may overwrite the change when it exits."
    return "\n".join(
        [
            heading,
            "",
            f"This patch edits Cursor's globalStorage state.vscdb:",
            f"  {display_path(db)}",
            "",
            reason,
            "",
            "Please:",
            "  1. Quit Cursor completely with Cmd+Q.",
            "  2. Open macOS Terminal.app, iTerm2, or another non-Cursor terminal.",
            "  3. Run this command again from there.",
            "",
            warning,
        ]
    )


def read_value(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM ItemTable WHERE key = ?", (KEY,)).fetchone()
    if row is None:
        return None
    value = row[0]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise PatchError(f"unsupported value type for {KEY}: {type(value).__name__}")


def parse_disabled_list(raw: str | None) -> list[Any]:
    if raw is None or raw == "":
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PatchError(f"{KEY} contains invalid JSON: {exc}") from exc
    if not isinstance(value, list):
        raise PatchError(f"{KEY} must be a JSON array, got {type(value).__name__}")
    return value


def extension_entry_id(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
        return entry["id"]
    return None


def has_extension(entries: list[Any], extension_id: str = EXTENSION_ID) -> bool:
    return any(extension_entry_id(entry) == extension_id for entry in entries)


def serialize(entries: list[Any]) -> str:
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def apply_entries(entries: list[Any]) -> tuple[list[Any], bool]:
    if has_extension(entries):
        return entries, False
    return [*entries, {"id": EXTENSION_ID}], True


def remove_entries(entries: list[Any]) -> tuple[list[Any], bool]:
    new_entries = [entry for entry in entries if extension_entry_id(entry) != EXTENSION_ID]
    return new_entries, len(new_entries) != len(entries)


def write_entries(conn: sqlite3.Connection, entries: list[Any]) -> None:
    if entries:
        conn.execute(
            "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
            (KEY, serialize(entries)),
        )
    else:
        conn.execute("DELETE FROM ItemTable WHERE key = ?", (KEY,))


def open_db(db: Path, writable: bool) -> sqlite3.Connection:
    mode = "rw" if writable else "ro"
    return sqlite3.connect(f"file:{db}?mode={mode}", uri=True)


def backup_database(db: Path) -> Path:
    backup = db.with_name(f"{db.name}.bak.{timestamp()}")
    source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        dest = sqlite3.connect(backup)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return backup


def companion_status(db: Path) -> list[Path]:
    return [path for path in (Path(f"{db}-wal"), Path(f"{db}-shm")) if path.exists()]


def print_state(label: str, entries: list[Any], raw: str | None) -> None:
    print(f"--- {label} ---")
    print(f"{KEY}: {serialize(entries) if raw is not None or entries else '(not set)'}")
    print(f"{EXTENSION_ID}: {'disabled' if has_extension(entries) else 'enabled'}")


def status(db: Path) -> int:
    if not db.is_file():
        print(f"ERROR: state database not found: {db}", file=sys.stderr)
        return 1
    warning = process_warning(db)
    if warning:
        print(warning, file=sys.stderr)
    companions = companion_status(db)
    if companions:
        print("SQLite companion files present:")
        for path in companions:
            print(f"  {display_path(path)}")
    conn = open_db(db, writable=False)
    try:
        raw = read_value(conn)
        entries = parse_disabled_list(raw)
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print_state("status", entries, raw)
    return 0


def change(db: Path, action: str, dry_run: bool, no_process_check: bool) -> int:
    if not db.is_file():
        print(f"ERROR: state database not found: {db}", file=sys.stderr)
        return 1

    if not no_process_check and not dry_run:
        error = process_error(db)
        if error is not None:
            print(error, file=sys.stderr)
            return 1
    elif not no_process_check and dry_run:
        warning = process_warning(db)
        if warning:
            print(warning, file=sys.stderr)

    conn = open_db(db, writable=False)
    try:
        raw = read_value(conn)
        before = parse_disabled_list(raw)
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    if action == "apply":
        after, changed = apply_entries(before)
    elif action == "remove":
        after, changed = remove_entries(before)
    else:
        raise AssertionError(action)

    print_state("before", before, raw)
    print_state("planned after" if dry_run else "after", after, serialize(after) if after else None)

    if dry_run:
        print("dry-run: no changes written")
        return 0
    if not changed:
        print("no changes needed")
        return 0

    backup = backup_database(db)
    print(f"backup: {display_path(backup)}")
    companions = companion_status(db)
    if companions:
        print("SQLite companion files were present; backup was created with sqlite3.Connection.backup():")
        for path in companions:
            print(f"  {display_path(path)}")

    conn = open_db(db, writable=True)
    try:
        write_entries(conn, after)
        conn.commit()
        raw_after = read_value(conn)
        actual_after = parse_disabled_list(raw_after)
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print_state("written", actual_after, raw_after)
    print("done. Restart Cursor and verify the Extensions view.")
    return 0


def create_test_db(path: Path, raw: str | None = None) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
        if raw is not None:
            conn.execute("INSERT INTO ItemTable (key, value) VALUES (?, ?)", (KEY, raw))
        conn.commit()
    finally:
        conn.close()


def read_test_entries(path: Path) -> list[Any]:
    conn = sqlite3.connect(path)
    try:
        return parse_disabled_list(read_value(conn))
    finally:
        conn.close()


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        db1 = root / "missing-key.vscdb"
        create_test_db(db1)
        before = read_test_entries(db1)
        after, changed = apply_entries(before)
        assert_equal(changed, True, "missing key apply changed")
        assert_equal(after, [{"id": EXTENSION_ID}], "missing key apply")
        conn = sqlite3.connect(db1)
        try:
            write_entries(conn, after)
            conn.commit()
        finally:
            conn.close()
        assert_equal(read_test_entries(db1), [{"id": EXTENSION_ID}], "missing key written")

        existing = [{"id": "example.disabled"}, {"id": EXTENSION_ID}]
        after, changed = apply_entries(existing)
        assert_equal(changed, False, "idempotent apply changed")
        assert_equal(after, existing, "idempotent apply")

        mixed = [{"id": "example.disabled"}]
        after, changed = apply_entries(mixed)
        assert_equal(changed, True, "existing list apply changed")
        assert_equal(after, [{"id": "example.disabled"}, {"id": EXTENSION_ID}], "existing list apply")

        after, changed = remove_entries([{"id": "example.disabled"}, {"id": EXTENSION_ID}])
        assert_equal(changed, True, "mixed remove changed")
        assert_equal(after, [{"id": "example.disabled"}], "mixed remove preserves other ids")

        after, changed = remove_entries([{"id": EXTENSION_ID}])
        assert_equal(changed, True, "single remove changed")
        assert_equal(after, [], "single remove empties list")

        db_bad = root / "bad-json.vscdb"
        create_test_db(db_bad, "{not json")
        try:
            read_test_entries(db_bad)
        except PatchError:
            pass
        else:
            raise AssertionError("invalid JSON should raise PatchError")

        db_backup = root / "backup.vscdb"
        create_test_db(db_backup, serialize([{"id": EXTENSION_ID}]))
        backup = backup_database(db_backup)
        assert_equal(backup.exists(), True, "backup exists")
        assert_equal(read_test_entries(backup), [{"id": EXTENSION_ID}], "backup contents")

    print("self-test: ok")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="disable or re-enable Cursor's built-in cursor-agent-worker via globalStorage state.vscdb"
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="show current disabled extension state")
    action.add_argument("--apply", action="store_true", help=f"add {EXTENSION_ID} to the disabled list")
    action.add_argument("--remove", action="store_true", help=f"remove {EXTENSION_ID} from the disabled list")
    action.add_argument("--self-test", action="store_true", help="run non-destructive tests against temporary DBs")
    parser.add_argument("--dry-run", action="store_true", help="show planned apply/remove change without writing")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Cursor globalStorage state DB (default: {DEFAULT_DB})")
    parser.add_argument(
        "--no-process-check",
        action="store_true",
        help="advanced/unsafe: allow writes even when Cursor processes are detected",
    )
    args = parser.parse_args(argv)
    if args.dry_run and not (args.apply or args.remove):
        parser.error("--dry-run requires --apply or --remove")
    if args.no_process_check and not (args.apply or args.remove):
        parser.error("--no-process-check is only valid with --apply or --remove")
    if not (args.status or args.apply or args.remove or args.self_test):
        args.status = True
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()

    db = Path(args.db).expanduser()
    if args.status:
        return status(db)
    if args.apply:
        return change(db, action="apply", dry_run=args.dry_run, no_process_check=args.no_process_check)
    if args.remove:
        return change(db, action="remove", dry_run=args.dry_run, no_process_check=args.no_process_check)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
