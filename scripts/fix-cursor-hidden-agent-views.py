#!/usr/bin/env python3
"""Restore hidden Cursor agent view containers in a workspace state database."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


KEYS = [
    "workbench.unifiedSidebar.hidden",
    "workbench.auxiliaryBar.hidden",
    "workbench.agentLayoutControl.visibilityState",
    "workbench.auxiliarybar.activepanelid",
    "workbench.auxiliarybar.viewContainersWorkspaceState",
    "workbench.view.extension.claude-sidebar.state",
    "workbench.view.extension.codexViewContainer.state",
]

CLAUDE_CONTAINER = "workbench.view.extension.claude-sidebar"
CODEX_CONTAINER = "workbench.view.extension.codexViewContainer"


def ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def cursor_running() -> bool:
    checks = [
        ["pgrep", "-x", "Cursor"],
        ["pgrep", "-f", "Cursor.app/Contents/MacOS/Cursor"],
        ["pgrep", "-f", "Cursor Helper"],
    ]
    for args in checks:
        try:
            if subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return True
        except FileNotFoundError:
            return False
    return False


def rows(conn: sqlite3.Connection) -> dict[str, str]:
    placeholders = ",".join("?" for _ in KEYS)
    result = conn.execute(
        f"SELECT key, value FROM ItemTable WHERE key IN ({placeholders}) ORDER BY key",
        KEYS,
    )
    return {key: value for key, value in result.fetchall()}


def print_rows(title: str, values: dict[str, str]) -> None:
    print(f"--- {title} ---")
    for key in KEYS:
        if key in values:
            print(f"{key}={values[key]}")


def upsert_view_state(conn: sqlite3.Connection, key: str, view_id: str) -> None:
    row = conn.execute("SELECT value FROM ItemTable WHERE key = ?", (key,)).fetchone()
    if row is None:
        value = {}
    else:
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError:
            value = {}
    view_state = value.get(view_id)
    if not isinstance(view_state, dict):
        view_state = {}
    view_state["collapsed"] = False
    view_state["isHidden"] = False
    value[view_id] = view_state
    conn.execute(
        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
        (key, json.dumps(value, separators=(",", ":"))),
    )


def patch_state(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
        [
            ("workbench.unifiedSidebar.hidden", "true"),
            ("workbench.auxiliaryBar.hidden", "false"),
            (
                "workbench.agentLayoutControl.visibilityState",
                json.dumps({"auxBarVisible": True, "unifiedSidebarVisible": False}, separators=(",", ":")),
            ),
            ("workbench.auxiliarybar.activepanelid", CODEX_CONTAINER),
        ],
    )
    upsert_view_state(conn, "workbench.view.extension.claude-sidebar.state", "claudeVSCodeSidebar")
    upsert_view_state(conn, "workbench.view.extension.codexViewContainer.state", "chatgpt.sidebarView")

    conn.execute(
        """
        INSERT OR REPLACE INTO ItemTable (key, value)
        SELECT 'workbench.auxiliarybar.viewContainersWorkspaceState',
               COALESCE(value, '[]')
        FROM ItemTable
        WHERE key = 'workbench.auxiliarybar.viewContainersWorkspaceState'
        UNION ALL
        SELECT 'workbench.auxiliarybar.viewContainersWorkspaceState', '[]'
        WHERE NOT EXISTS (
          SELECT 1 FROM ItemTable WHERE key = 'workbench.auxiliarybar.viewContainersWorkspaceState'
        )
        LIMIT 1
        """
    )
    conn.execute(
        """
        UPDATE ItemTable
        SET value = (
          SELECT json_group_array(
            CASE
              WHEN json_extract(item.value, '$.id') IN (?, ?)
              THEN json_set(item.value, '$.visible', json('true'))
              ELSE item.value
            END
          )
          FROM json_each(ItemTable.value) AS item
        )
        WHERE key = 'workbench.auxiliarybar.viewContainersWorkspaceState'
        """,
        (CLAUDE_CONTAINER, CODEX_CONTAINER),
    )
    for container in (CLAUDE_CONTAINER, CODEX_CONTAINER):
        conn.execute(
            """
            UPDATE ItemTable
            SET value = json_insert(value, '$[#]', json(?))
            WHERE key = 'workbench.auxiliarybar.viewContainersWorkspaceState'
              AND NOT EXISTS (
                SELECT 1
                FROM json_each(ItemTable.value)
                WHERE json_extract(value, '$.id') = ?
              )
            """,
            (json.dumps({"id": container, "visible": True}, separators=(",", ":")), container),
        )


def backup_companions(db: Path) -> list[Path]:
    stamp = ts()
    backups: list[Path] = []
    for path in [db, Path(f"{db}-wal"), Path(f"{db}-shm")]:
        if path.exists():
            backup = path.with_name(f"{path.name}.bak.{stamp}")
            shutil.copy2(path, backup)
            backups.append(backup)
    return backups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="restore Claude Code and Codex views hidden in a Cursor workspace state.vscdb"
    )
    parser.add_argument("--db", required=True, help="path to Cursor workspaceStorage state.vscdb")
    parser.add_argument("--dry-run", action="store_true", help="show current values without writing")
    parser.add_argument("--no-process-check", action="store_true", help="allow running while Cursor processes exist")
    args = parser.parse_args(argv)

    db = Path(args.db).expanduser()
    if not db.is_file():
        print(f"ERROR: state database not found: {db}", file=sys.stderr)
        return 1
    if not args.no_process_check and cursor_running():
        print("ERROR: Cursor or Cursor Helper appears to be running. Quit Cursor fully before patching.", file=sys.stderr)
        return 1

    mode = "ro" if args.dry_run else "rw"
    conn = sqlite3.connect(f"file:{db}?mode={mode}", uri=True)
    try:
        before = rows(conn)
        print_rows("before", before)
        if args.dry_run:
            print("dry-run: no changes written")
            return 0

        backups = backup_companions(db)
        for backup in backups:
            print(f"backup: {backup}")
        patch_state(conn)
        conn.commit()
        print_rows("after", rows(conn))
    finally:
        conn.close()

    print("done. Restart Cursor and verify the secondary panel views.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
