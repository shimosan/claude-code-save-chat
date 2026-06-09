#!/usr/bin/env python3
"""Inspect config snapshot/apply logs without touching live configuration.

This helper is intentionally limited to files under log/config. It is a stable
tool for agents that follow scripts/config-update.md.

Examples:
    python3 scripts/config-log-helper.py latest --machine anomura --expected-os mac
    python3 scripts/config-log-helper.py list --machine anomura --kind snapshot
    python3 scripts/config-log-helper.py compare-summary before.json reference.json
    python3 scripts/config-log-helper.py timeline --machine anomura --expected-os mac
    python3 scripts/config-log-helper.py timeline --all-machines
    python3 scripts/config-log-helper.py drift --base-machine anomura --expected-os mac
    python3 scripts/config-log-helper.py nway --expected-os mac
    python3 scripts/config-log-helper.py apply-log-skeleton --machine anomura --recipe-id editor.settings-key --recipe-type config
    python3 scripts/config-log-helper.py drift --base-machine isopoda --expected-os mac --group-lines
    python3 scripts/config-log-helper.py --self-test
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import socket
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SNAPSHOT_RE = re.compile(
    r"^config_snapshot_(?P<machine>.+)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.json$"
)
LEGACY_SNAPSHOT_RE = re.compile(
    r"^config_(?P<machine>.+)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.json$"
)
APPLY_RE = re.compile(
    r"^config_apply_(?P<machine>.+)_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.md$"
)
APPLY_FIELD_RE = re.compile(r"^- (?P<key>[a-zA-Z_ -]+): `?(?P<value>.*?)`?\s*$")
APPLY_SNAPSHOT_RE = re.compile(r"^- (?P<key>before|reference|verification): `(?P<value>.*?)`\s*$")
APPLY_VALUE_RE = re.compile(r"^- (?P<role>old|new) `(?P<expr>[^`]+)`: `(?P<value>.*?)`\s*$")
CAPTURE_ONLY_TOP_LEVEL = {"machine", "os", "captured_at"}
METADATA_KEYS = {"mtime"}


@dataclass(frozen=True)
class LogEntry:
    kind: str
    path: Path
    machine_from_name: str
    timestamp: datetime
    machine: str | None = None
    os_name: str | None = None
    captured_at: str | None = None
    applied_at: str | None = None
    logged_at: str | None = None
    title: str | None = None
    recipe_id: str | None = None
    recipe_type: str | None = None
    application: str | None = None
    platform: str | None = None
    target: str | None = None
    approved_request: str | None = None
    snapshots: dict[str, str] | None = None
    value_assertions: list[dict[str, Any]] | None = None
    valid: bool = True
    error: str | None = None

    def sort_key(self) -> tuple[datetime, str, str]:
        return (self.timestamp, self.kind, self.path.name)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "path": str(self.path),
            "filename": self.path.name,
            "machine_from_name": self.machine_from_name,
            "timestamp": format_ts(self.timestamp),
            "valid": self.valid,
        }
        if self.machine is not None:
            data["machine"] = self.machine
        if self.os_name is not None:
            data["os"] = self.os_name
        if self.captured_at is not None:
            data["captured_at"] = self.captured_at
        if self.applied_at is not None:
            data["applied_at"] = self.applied_at
        if self.logged_at is not None:
            data["logged_at"] = self.logged_at
        if self.title is not None:
            data["title"] = self.title
        if self.recipe_id is not None:
            data["recipe_id"] = self.recipe_id
        if self.recipe_type is not None:
            data["recipe_type"] = self.recipe_type
        if self.application is not None:
            data["application"] = self.application
        if self.platform is not None:
            data["platform"] = self.platform
        if self.target is not None:
            data["target"] = self.target
        if self.approved_request is not None:
            data["approved_request"] = self.approved_request
        if self.snapshots:
            data["snapshots"] = self.snapshots
        if self.value_assertions:
            data["value_assertions"] = self.value_assertions
        if self.error is not None:
            data["error"] = self.error
        return data


def parse_ts(text: str) -> datetime:
    normalized = text.strip().replace("T", "_").replace(" ", "_").replace(":", "-")
    return datetime.strptime(normalized, "%Y-%m-%d_%H-%M-%S")


def format_ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%d_%H-%M-%S")


def format_iso_ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def now_ts() -> str:
    return format_ts(datetime.now())


def default_machine() -> str:
    return socket.gethostname().split(".", 1)[0] or "unknown"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_log_dir() -> Path:
    return repo_root() / "log" / "config"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_entry(path: Path, match: re.Match[str]) -> LogEntry:
    machine_from_name = match.group("machine")
    ts_value = parse_ts(match.group("ts"))
    try:
        data = load_json(path)
        if not isinstance(data, dict):
            raise ValueError("snapshot JSON is not an object")
        machine = data.get("machine")
        os_name = data.get("os")
        captured_at = data.get("captured_at")
        if not isinstance(machine, str) or not machine:
            raise ValueError("snapshot missing string machine")
        if not isinstance(os_name, str) or not os_name:
            raise ValueError("snapshot missing string os")
        if not isinstance(captured_at, str) or not captured_at:
            raise ValueError("snapshot missing string captured_at")
        return LogEntry(
            kind="snapshot",
            path=path,
            machine_from_name=machine_from_name,
            timestamp=ts_value,
            machine=machine,
            os_name=os_name,
            captured_at=captured_at,
        )
    except Exception as exc:
        return LogEntry(
            kind="snapshot",
            path=path,
            machine_from_name=machine_from_name,
            timestamp=ts_value,
            valid=False,
            error=str(exc),
        )


def clean_apply_value(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        return value[1:-1]
    return value


def parse_apply_value(value: str) -> Any:
    value = clean_apply_value(value)
    if value in {"true", "false", "null"} or re.fullmatch(r"-?\d+(\.\d+)?", value):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if value.startswith(("{", "[", '"')):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def parse_apply_log(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {"snapshots": {}, "value_assertions": []}
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if line.startswith("# Config Apply: "):
            data["title"] = line.removeprefix("# Config Apply: ").strip()
            continue
        snap = APPLY_SNAPSHOT_RE.match(line)
        if snap:
            data["snapshots"][snap.group("key")] = snap.group("value").strip()
            continue
        value_match = APPLY_VALUE_RE.match(line)
        if value_match:
            data["value_assertions"].append(
                {
                    "role": value_match.group("role"),
                    "expr": value_match.group("expr"),
                    "value": parse_apply_value(value_match.group("value")),
                }
            )
            continue
        field = APPLY_FIELD_RE.match(line)
        if not field:
            continue
        key = field.group("key").strip().lower().replace(" ", "_").replace("-", "_")
        value = clean_apply_value(field.group("value"))
        if key in {"machine", "applied_at", "logged_at", "recipe_id", "recipe_type", "application", "platform", "target"}:
            if key in {"applied_at", "logged_at"}:
                try:
                    value = format_iso_ts(parse_ts(value))
                except ValueError:
                    pass
            data[key] = value
        elif key == "approved_request":
            data["approved_request"] = value
    return data


def apply_entry(path: Path, match: re.Match[str]) -> LogEntry:
    machine_from_name = match.group("machine")
    timestamp = parse_ts(match.group("ts"))
    try:
        parsed = parse_apply_log(path)
        machine = parsed.get("machine") or machine_from_name
        applied_at = parsed.get("applied_at") or format_iso_ts(timestamp)
        logged_at = parsed.get("logged_at") or format_iso_ts(timestamp)
        return LogEntry(
            kind="apply",
            path=path,
            machine_from_name=machine_from_name,
            timestamp=timestamp,
            machine=machine,
            applied_at=applied_at,
            logged_at=logged_at,
            title=parsed.get("title"),
            recipe_id=parsed.get("recipe_id"),
            recipe_type=parsed.get("recipe_type"),
            application=parsed.get("application"),
            platform=parsed.get("platform"),
            target=parsed.get("target"),
            approved_request=parsed.get("approved_request"),
            snapshots=parsed.get("snapshots") or None,
            value_assertions=parsed.get("value_assertions") or None,
        )
    except Exception as exc:
        return LogEntry(
            kind="apply",
            path=path,
            machine_from_name=machine_from_name,
            timestamp=timestamp,
            machine=machine_from_name,
            applied_at=format_iso_ts(timestamp),
            logged_at=format_iso_ts(timestamp),
            valid=False,
            error=str(exc),
        )


def iter_entries(log_dir: Path) -> list[LogEntry]:
    entries: list[LogEntry] = []
    if not log_dir.exists():
        return entries
    for path in log_dir.iterdir():
        if not path.is_file():
            continue
        snapshot_match = SNAPSHOT_RE.match(path.name)
        if snapshot_match:
            entries.append(snapshot_entry(path, snapshot_match))
            continue
        legacy_snapshot_match = LEGACY_SNAPSHOT_RE.match(path.name)
        if legacy_snapshot_match:
            entries.append(snapshot_entry(path, legacy_snapshot_match))
            continue
        apply_match = APPLY_RE.match(path.name)
        if apply_match:
            entries.append(apply_entry(path, apply_match))
    return sorted(entries, key=LogEntry.sort_key)


def matches_common(
    entry: LogEntry,
    *,
    kind: str,
    machine: str | None,
    expected_os: str | None,
    before: datetime | None,
    valid_only: bool,
) -> bool:
    if kind != "all" and entry.kind != kind:
        return False
    if machine and (entry.machine or entry.machine_from_name) != machine:
        return False
    if before and entry.timestamp > before:
        return False
    if valid_only and not entry.valid:
        return False
    if expected_os:
        if entry.kind != "snapshot":
            return False
        if entry.os_name != expected_os:
            return False
    return True


def filtered_entries(
    log_dir: Path,
    *,
    kind: str = "all",
    machine: str | None = None,
    expected_os: str | None = None,
    before: datetime | None = None,
    valid_only: bool = False,
) -> list[LogEntry]:
    return [
        entry
        for entry in iter_entries(log_dir)
        if matches_common(
            entry,
            kind=kind,
            machine=machine,
            expected_os=expected_os,
            before=before,
            valid_only=valid_only,
        )
    ]


def latest_snapshot(
    log_dir: Path,
    *,
    machine: str | None,
    expected_os: str | None,
    before: datetime | None,
) -> LogEntry | None:
    entries = filtered_entries(
        log_dir,
        kind="snapshot",
        machine=machine,
        expected_os=expected_os,
        before=before,
        valid_only=True,
    )
    return entries[-1] if entries else None


def latest_snapshots_by_machine(
    log_dir: Path,
    *,
    expected_os: str | None,
    before: datetime | None,
) -> dict[str, LogEntry]:
    snapshots = filtered_entries(
        log_dir,
        kind="snapshot",
        expected_os=expected_os,
        before=before,
        valid_only=True,
    )
    latest: dict[str, LogEntry] = {}
    for entry in snapshots:
        machine = entry.machine or entry.machine_from_name
        latest[machine] = entry
    return latest


def apply_logs_for_machine(
    log_dir: Path,
    *,
    machine: str,
    before: datetime | None = None,
) -> list[LogEntry]:
    return filtered_entries(
        log_dir,
        kind="apply",
        machine=machine,
        expected_os=None,
        before=before,
        valid_only=True,
    )


def snapshot_ref_matches_value(ref: str | None, snapshot_path: Path) -> bool:
    if not ref:
        return False
    return ref == str(snapshot_path) or Path(ref).name == snapshot_path.name


def snapshot_ref_matches(entry: LogEntry, snapshot_path: Path) -> bool:
    refs = entry.snapshots or {}
    return any(snapshot_ref_matches_value(ref, snapshot_path) for ref in refs.values())


def entry_event_time(entry: LogEntry) -> datetime:
    if entry.kind == "snapshot" and entry.captured_at:
        return parse_ts(entry.captured_at)
    if entry.kind == "apply" and entry.applied_at:
        return parse_ts(entry.applied_at)
    return entry.timestamp


def entry_timeline_sort_key(entry: LogEntry) -> tuple[datetime, int, str]:
    kind_rank = {"snapshot": 0, "apply": 1}.get(entry.kind, 9)
    return (entry_event_time(entry), kind_rank, entry.path.name)


def resolve_log_ref(log_dir: Path, ref: str | None) -> Path | None:
    if not ref or ref == "TODO":
        return None
    path = Path(ref)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    candidates.extend([repo_root() / ref, log_dir / path.name])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def snapshot_entry_for_path(path: Path) -> LogEntry:
    match = SNAPSHOT_RE.match(path.name)
    if not match:
        raise ValueError(f"not a snapshot filename: {path.name}")
    return snapshot_entry(path, match)


def source_and_path_from_expr(expr: str) -> tuple[str, str]:
    bracket = re.fullmatch(r'(?P<source>.+)\.value\["(?P<key>.*)"\]', expr)
    if bracket:
        return bracket.group("source"), bracket.group("key")
    if expr.endswith(".value"):
        return expr[: -len(".value")], "."
    return expr, "."


def display_key_from_expr(expr: str) -> str:
    source, path = source_and_path_from_expr(expr)
    if path == ".":
        return source
    return f"{source}.{path}"


def resolve_snapshot_expr(snapshot_data: dict[str, Any], expr: str) -> Any:
    semantic = semantic_snapshot(snapshot_data)
    source, path = source_and_path_from_expr(expr)
    if source not in semantic:
        raise KeyError(source)
    value = semantic[source]
    if path == ".":
        return value
    if not isinstance(value, dict):
        raise KeyError(path)
    return value[path]


def check_value_assertions(entry: LogEntry, before_path: Path | None, verification_path: Path | None) -> dict[str, Any]:
    conflicts: list[str] = []
    warnings: list[str] = []
    keys: list[str] = []
    assertions = entry.value_assertions or []
    before_data = load_json(before_path) if before_path else None
    verification_data = load_json(verification_path) if verification_path else None

    for assertion in assertions:
        role = assertion["role"]
        expr = assertion["expr"]
        expected = assertion["value"]
        key = display_key_from_expr(expr)
        if key not in keys:
            keys.append(key)
        target_data = before_data if role == "old" else verification_data
        conflict_side = "before" if role == "old" else "after"
        if target_data is None:
            conflicts.append(conflict_side)
            warnings.append(f"{conflict_side} snapshot unavailable for {expr}")
            continue
        try:
            actual = resolve_snapshot_expr(target_data, expr)
        except (KeyError, TypeError) as exc:
            conflicts.append(conflict_side)
            warnings.append(f"{conflict_side} missing {expr}: {exc}")
            continue
        if actual != expected:
            conflicts.append(conflict_side)
            warnings.append(f"{conflict_side} mismatch {expr}: expected {compact(expected)} got {compact(actual)}")

    return {
        "keys": keys,
        "conflicts": sorted(set(conflicts)),
        "warnings": warnings,
    }


def apply_consistency(entry: LogEntry, log_dir: Path) -> dict[str, Any]:
    refs = entry.snapshots or {}
    checks: list[str] = []
    warnings: list[str] = []
    conflicts: list[str] = []
    before_path = resolve_log_ref(log_dir, refs.get("before"))
    verification_path = resolve_log_ref(log_dir, refs.get("verification"))
    reference_path = resolve_log_ref(log_dir, refs.get("reference"))

    if refs.get("before") and before_path is None:
        warnings.append(f"missing before snapshot: {refs.get('before')}")
        conflicts.append("before")
    if refs.get("verification") and verification_path is None:
        warnings.append(f"missing verification snapshot: {refs.get('verification')}")
        conflicts.append("after")
    if refs.get("reference") and reference_path is None:
        warnings.append(f"missing reference snapshot: {refs.get('reference')}")

    before_entry = snapshot_entry_for_path(before_path) if before_path else None
    verification_entry = snapshot_entry_for_path(verification_path) if verification_path else None
    reference_entry = snapshot_entry_for_path(reference_path) if reference_path else None

    for role, snap in [("before", before_entry), ("verification", verification_entry)]:
        if snap and entry.machine and snap.machine != entry.machine:
            warnings.append(f"{role} machine mismatch: apply={entry.machine} snapshot={snap.machine}")
            conflicts.append("before" if role == "before" else "after")
        if snap and entry.platform and snap.os_name != entry.platform:
            warnings.append(f"{role} platform mismatch: apply={entry.platform} snapshot={snap.os_name}")
            conflicts.append("before" if role == "before" else "after")
    source = None
    if reference_entry:
        source = f"{reference_entry.machine}/{reference_entry.os_name}"
        checks.append(f"reference={reference_entry.machine}/{reference_entry.os_name}")

    if before_path and verification_path:
        summary = compare_snapshots(before_path, verification_path, limit=None)
        diff_count = len(summary["diffs"])
        checks.append(f"before->verification diffs={diff_count}")
        if diff_count == 0:
            warnings.append("before and verification snapshots are semantically identical")

    assertion_check = check_value_assertions(entry, before_path, verification_path)
    warnings.extend(assertion_check["warnings"])
    conflicts.extend(assertion_check["conflicts"])

    conflicts = sorted(set(conflicts), key=lambda side: {"before": 0, "after": 1}.get(side, 9))
    status = "ok" if not conflicts and not warnings else "warn"
    return {
        "status": status,
        "source": source,
        "keys": assertion_check["keys"],
        "conflicts": conflicts,
        "checks": checks,
        "warnings": warnings,
    }


def semantic_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key in CAPTURE_ONLY_TOP_LEVEL:
            continue
        if isinstance(value, dict) and "value" in value:
            result[key] = value["value"]
        elif isinstance(value, dict):
            result[key] = {k: v for k, v in value.items() if k not in METADATA_KEYS}
        else:
            result[key] = value
    return result


def diff_key(diff: dict[str, Any]) -> str:
    path = diff["path"]
    if path == ".":
        return diff["source"]
    if path == "[]" or str(path).startswith("["):
        return f"{diff['source']}{path}"
    return f"{diff['source']}.{path}"


def compact(value: Any, max_len: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None)))


def domain_rank(source: str) -> tuple[int, str]:
    if source in {"code.settings", "cursor.settings", "code.locale", "cursor.locale"}:
        return (0, source)
    if source in {"code.extensions", "cursor.extensions"}:
        return (1, source)
    if source in {"git", "zsh", "powershell", "gitbash"}:
        return (2, source)
    return (3, source)


def diff_sort_key(diff: dict[str, Any]) -> tuple[int, str, str]:
    return (*domain_rank(diff["source"]), diff["path"])


def diff_values(source: str, left: Any, right: Any, limit: int | None = None) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    if isinstance(left, dict) and isinstance(right, dict):
        left_keys = set(left)
        right_keys = set(right)
        for key in sorted(left_keys - right_keys):
            diffs.append({"source": source, "path": key, "change": "removed", "old": left[key]})
        for key in sorted(right_keys - left_keys):
            diffs.append({"source": source, "path": key, "change": "added", "new": right[key]})
        for key in sorted(left_keys & right_keys):
            if left[key] != right[key]:
                diffs.append(
                    {
                        "source": source,
                        "path": key,
                        "change": "changed",
                        "old": left[key],
                        "new": right[key],
                    }
                )
        return diffs if limit is None else diffs[:limit]

    if isinstance(left, list) and isinstance(right, list) and all(
        is_scalar(item) for item in left + right
    ):
        left_set = set(left)
        right_set = set(right)
        for item in sorted(left_set - right_set, key=lambda x: str(x)):
            diffs.append({"source": source, "path": "[]", "change": "removed", "old": item})
        for item in sorted(right_set - left_set, key=lambda x: str(x)):
            diffs.append({"source": source, "path": "[]", "change": "added", "new": item})
        if not diffs and left != right:
            diffs.append({"source": source, "path": "[]", "change": "reordered", "old": left, "new": right})
        return diffs if limit is None else diffs[:limit]

    if left != right:
        return [{"source": source, "path": ".", "change": "changed", "old": left, "new": right}]
    return []


def compare_snapshots(left_path: Path, right_path: Path, limit: int | None) -> dict[str, Any]:
    left_raw = load_json(left_path)
    right_raw = load_json(right_path)
    if not isinstance(left_raw, dict) or not isinstance(right_raw, dict):
        raise ValueError("snapshot inputs must be JSON objects")
    left = semantic_snapshot(left_raw)
    right = semantic_snapshot(right_raw)

    diffs: list[dict[str, Any]] = []
    left_sources = set(left)
    right_sources = set(right)
    for source in sorted(left_sources - right_sources):
        diffs.append({"source": source, "path": ".", "change": "removed", "old": left[source]})
    for source in sorted(right_sources - left_sources):
        diffs.append({"source": source, "path": ".", "change": "added", "new": right[source]})
    for source in sorted(left_sources & right_sources):
        remaining = None if limit is None else max(limit - len(diffs), 0)
        diffs.extend(diff_values(source, left[source], right[source], remaining))
        if limit is not None and len(diffs) >= limit:
            break
    diffs = sorted(diffs, key=diff_sort_key)
    if limit is not None:
        diffs = diffs[:limit]

    return {
        "left": {
            "path": str(left_path),
            "machine": left_raw.get("machine"),
            "os": left_raw.get("os"),
            "captured_at": left_raw.get("captured_at"),
        },
        "right": {
            "path": str(right_path),
            "machine": right_raw.get("machine"),
            "os": right_raw.get("os"),
            "captured_at": right_raw.get("captured_at"),
        },
        "diff_count_shown": len(diffs),
        "diffs": diffs,
    }


def is_minor_version_diff(diff: dict[str, Any]) -> bool:
    source = diff["source"]
    path = diff["path"]
    if source in {"code.extensions", "cursor.extensions"} and path == "[]":
        return True
    if path == "version":
        return True
    if source in {"brew.version", "R.version", "python.version", "node.version"}:
        return True
    return False


def important_diffs(diffs: list[dict[str, Any]], *, include_minor: bool) -> list[dict[str, Any]]:
    if include_minor:
        return diffs
    return [diff for diff in diffs if not is_minor_version_diff(diff)]


def summarize_diff_counts(diffs: list[dict[str, Any]]) -> str:
    if not diffs:
        return "0 diffs"
    counts: dict[str, int] = {}
    for diff in diffs:
        counts[diff["source"]] = counts.get(diff["source"], 0) + 1
    pieces = [f"{source}={count}" for source, count in sorted(counts.items(), key=lambda item: domain_rank(item[0]))]
    return f"{len(diffs)} diffs (" + ", ".join(pieces) + ")"


def format_diff_line(diff: dict[str, Any]) -> str:
    prefix = diff_key(diff)
    change = diff["change"]
    if change == "added":
        return f"+ {prefix}: {compact(diff.get('new'))}"
    if change == "removed":
        return f"- {prefix}: {compact(diff.get('old'))}"
    if change == "reordered":
        return f"~ {prefix}: reordered"
    return f"~ {prefix}: {compact(diff.get('old'))} -> {compact(diff.get('new'))}"


def grouped_diff_line_key(diff: dict[str, Any]) -> str:
    return format_diff_line(diff)


def grouped_diff_line_sort_key(group: dict[str, Any]) -> tuple[int, int, str, str, str]:
    return (
        -group["machine_count"],
        *domain_rank(group["source"]),
        group["path"],
        group["line"],
    )


def format_diff_summary(diffs: list[dict[str, Any]], limit: int) -> str:
    if not diffs:
        return "none"
    pieces: list[str] = []
    for diff in diffs[:limit]:
        key = diff_key(diff)
        change = diff["change"]
        if change == "added":
            pieces.append(f"+{key}={compact(diff.get('new'), 48)}")
        elif change == "removed":
            pieces.append(f"-{key}")
        elif change == "reordered":
            pieces.append(f"~{key}=reordered")
        else:
            pieces.append(f"~{key}:{compact(diff.get('old'), 32)}->{compact(diff.get('new'), 32)}")
    remaining = len(diffs) - len(pieces)
    if remaining > 0:
        pieces.append(f"+{remaining} more")
    return "; ".join(pieces)


def format_apply_line(apply: dict[str, Any]) -> str:
    title = apply.get("title") or apply.get("filename")
    recipe = apply.get("recipe_id") or "unknown-recipe"
    recipe_type = apply.get("recipe_type")
    recipe_label = f"{recipe_type}:{recipe}" if recipe_type else recipe
    application = apply.get("application") or "unknown-app"
    applied_at = apply.get("applied_at") or apply.get("timestamp")
    return f"apply {applied_at}: {recipe_label} / {application} / {title}"


def timeline_summary(
    log_dir: Path,
    *,
    machine: str | None,
    expected_os: str | None,
    before: datetime | None,
    limit: int,
    diff_limit: int,
    include_minor: bool,
) -> dict[str, Any]:
    all_entries = filtered_entries(
        log_dir,
        kind="all",
        machine=machine,
        expected_os=None,
        before=before,
        valid_only=True,
    )
    if expected_os:
        all_entries = [
            entry
            for entry in all_entries
            if (entry.kind == "snapshot" and entry.os_name == expected_os)
            or (entry.kind == "apply" and (entry.platform is None or entry.platform == expected_os))
        ]
    all_entries = sorted(all_entries, key=entry_timeline_sort_key)
    entries = all_entries[-limit:]
    previous_snapshot: dict[str, LogEntry] = {}
    for entry in all_entries:
        if entry.kind == "snapshot":
            previous_snapshot[str(entry.path)] = latest_previous_snapshot(all_entries, entry)

    items: list[dict[str, Any]] = []
    for entry in entries:
        item = entry.to_json()
        if entry.kind == "snapshot":
            prev = previous_snapshot.get(str(entry.path))
            if prev:
                summary = compare_snapshots(prev.path, entry.path, limit=None)
                diffs = important_diffs(summary["diffs"], include_minor=include_minor)
                item["previous_snapshot"] = prev.to_json()
                item["previous_diff_count"] = len(diffs)
                item["previous_diffs"] = diffs[:diff_limit]
        if entry.kind == "apply":
            item["consistency"] = apply_consistency(entry, log_dir)
        items.append(item)
    return {
        "machine": machine or "all",
        "expected_os": expected_os,
        "items": items,
    }


def latest_previous_snapshot(entries: list[LogEntry], current: LogEntry) -> LogEntry | None:
    previous = None
    for entry in entries:
        if entry.path == current.path:
            return previous
        if (
            entry.kind == "snapshot"
            and entry.machine == current.machine
            and entry.os_name == current.os_name
        ):
            previous = entry
    return previous


def format_timeline_text(summary: dict[str, Any]) -> str:
    lines = [f"timeline: {summary['machine']} / {summary.get('expected_os') or 'any-os'}"]
    if not summary["items"]:
        lines.append("No log entries found.")
        return "\n".join(lines)
    for item in summary["items"]:
        if item["kind"] == "snapshot":
            diff_text = "first"
            if "previous_diffs" in item:
                diff_text = format_diff_summary(item["previous_diffs"], len(item["previous_diffs"]))
                if item.get("previous_diff_count", 0) > len(item["previous_diffs"]):
                    hidden = item["previous_diff_count"] - len(item["previous_diffs"])
                    diff_text = f"{diff_text}; +{hidden} more" if diff_text != "none" else f"+{hidden} more"
            lines.append(
                f"{item.get('captured_at') or item['timestamp']} snapshot {item.get('machine')}/{item.get('os')} diff={diff_text}"
            )
            continue
        consistency = item.get("consistency", {})
        parts = [
            item.get("applied_at") or item["timestamp"],
            "apply",
            f"{item.get('machine')}/{item.get('platform') or 'unknown-os'}",
        ]
        source = consistency.get("source")
        if source:
            parts.append(f"source={source}")
        key_text = ",".join(consistency.get("keys") or [])
        if key_text:
            parts.append(f"key={key_text}")
        else:
            recipe_text = item.get("recipe_id") or "unknown-recipe"
            recipe_type = item.get("recipe_type")
            if recipe_type:
                recipe_text = f"{recipe_type}:{recipe_text}"
            parts.append(f"recipe={recipe_text}")
        conflicts = consistency.get("conflicts") or []
        if conflicts:
            parts.append(f"conflict: {','.join(conflicts)}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def format_compare_text(summary: dict[str, Any]) -> str:
    lines = [
        f"left:  {summary['left']['machine']} / {summary['left']['os']} / {summary['left']['captured_at']}",
        f"right: {summary['right']['machine']} / {summary['right']['os']} / {summary['right']['captured_at']}",
        "",
    ]
    diffs = summary["diffs"]
    if not diffs:
        lines.append("No semantic config differences found.")
        return "\n".join(lines)
    for diff in diffs:
        lines.append(format_diff_line(diff))
    return "\n".join(lines)


def flatten_value(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        rows: list[tuple[str, Any]] = []
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_value(value[key], child_prefix))
        return rows or [(prefix or ".", {})]
    return [(prefix or ".", value)]


def aggregate_key(source: str, path: str) -> str:
    if path == ".":
        return source
    return f"{source}.{path}"


def canonical_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_minor_key(source: str, path: str) -> bool:
    if source in {"code.extensions", "cursor.extensions"} and path in {".", "[]"}:
        return True
    if path == "version":
        return True
    if source in {"brew.version", "R.version", "python.version", "node.version"}:
        return True
    return False


def classify_nway_groups(groups: list[dict[str, Any]]) -> str:
    missing_count = sum(group["count"] for group in groups if group.get("missing"))
    value_group_count = sum(1 for group in groups if not group.get("missing"))
    if missing_count == 0 and value_group_count == 1:
        return "uniform"
    if missing_count > 0 and value_group_count == 1:
        return "partial"
    if missing_count == 0:
        return "split"
    return "split-with-missing"


def nway_importance(row: dict[str, Any], machine_count: int) -> dict[str, Any]:
    source = str(row["source"])
    path = str(row["path"])
    key = str(row["key"])
    normalized_key = key.lower()
    classification = row["classification"]
    score = 0
    reasons: list[str] = []

    classification_score = {
        "split": 30,
        "split-with-missing": 26,
        "partial": 18,
        "uniform": 0,
    }.get(classification, 0)
    if classification_score:
        score += classification_score

    if any(part in normalized_key for part in ("window.zoomlevel", "editor.font", "locale", "theme")):
        score += 70
        reasons.append("editor-ui")
    elif normalized_key in {"git.user.email", "git.user.name"}:
        score += 68
        reasons.append("git-identity")
    elif source in {"code.settings", "cursor.settings"}:
        score += 52
        reasons.append("editor-setting")
    elif source in {"codex", "claude", "copilot"}:
        score += 45
        reasons.append("agent-config")
    elif source in {"zsh", "venvs", "python3", "conda"}:
        score += 36
        reasons.append("runtime-env")
    elif source in {"fonts", "jupyter", "karabiner", "ollama"}:
        score += 30
        reasons.append("user-tooling")
    elif source == "git":
        score += 26
        reasons.append("git-config")
    elif source == "brew":
        score += 20
        reasons.append("package-list")
    elif source in {"code.extensions", "cursor.extensions"}:
        score += 12
        reasons.append("extensions")

    largest_group = max((group["count"] for group in row["groups"]), default=0)
    if machine_count > 1 and largest_group == machine_count - 1:
        score += 8
        reasons.append("one-outlier")
    elif machine_count > 1 and len(row["groups"]) > 2:
        score += 4
        reasons.append("multi-split")

    return {"score": score, "reasons": reasons}


def nway_pattern_id(groups: list[dict[str, Any]]) -> tuple[tuple[str, ...], ...]:
    machine_groups = [tuple(sorted(group["machines"])) for group in groups]
    return tuple(sorted(machine_groups, key=lambda names: (-len(names), names)))


def format_machine_pattern(pattern: tuple[tuple[str, ...], ...]) -> str:
    return "[" + ", ".join("{" + ", ".join(group) + "}" for group in pattern) + "]"


def nway_patterns(rows: list[dict[str, Any]], sort_mode: str) -> list[dict[str, Any]]:
    patterns: dict[tuple[tuple[str, ...], ...], dict[str, Any]] = {}
    for row in rows:
        pattern = nway_pattern_id(row["groups"])
        item = patterns.setdefault(
            pattern,
            {
                "pattern": [list(group) for group in pattern],
                "pattern_text": format_machine_pattern(pattern),
                "keys": [],
                "key_count": 0,
                "max_importance": 0,
            },
        )
        item["keys"].append(
            {
                "key": row["key"],
                "classification": row["classification"],
                "importance": row["importance"],
                "importance_reasons": row.get("importance_reasons") or [],
            }
        )
        item["key_count"] += 1
        item["max_importance"] = max(item["max_importance"], row["importance"])

    result = list(patterns.values())
    for item in result:
        item["keys"] = sorted(
            item["keys"],
            key=lambda key: (-key["importance"], key["key"]),
        )
    if sort_mode == "key-count-asc":
        return sorted(result, key=lambda item: (item["key_count"], -item["max_importance"], item["pattern_text"]))
    if sort_mode == "importance":
        return sorted(result, key=lambda item: (-item["max_importance"], -item["key_count"], item["pattern_text"]))
    return sorted(result, key=lambda item: (-item["key_count"], -item["max_importance"], item["pattern_text"]))


def nway_summary(
    log_dir: Path,
    *,
    expected_os: str | None,
    before: datetime | None,
    key_limit: int | None,
    include_uniform: bool,
    include_minor: bool,
    sort_mode: str,
    pattern_sort_mode: str,
) -> dict[str, Any]:
    latest = latest_snapshots_by_machine(log_dir, expected_os=expected_os, before=before)
    machines = sorted(latest)
    rows: dict[str, dict[str, Any]] = {}

    for machine in machines:
        snapshot = latest[machine]
        semantic = semantic_snapshot(load_json(snapshot.path))
        for source, subtree in semantic.items():
            for path, value in flatten_value(subtree):
                if not include_minor and is_minor_key(source, path):
                    continue
                key = aggregate_key(source, path)
                row = rows.setdefault(
                    key,
                    {
                        "key": key,
                        "source": source,
                        "path": path,
                        "machine_values": {},
                    },
                )
                row["machine_values"][machine] = value

    output_rows: list[dict[str, Any]] = []
    for row in rows.values():
        value_groups: dict[str, dict[str, Any]] = {}
        for machine in machines:
            if machine in row["machine_values"]:
                value = row["machine_values"][machine]
                canonical = canonical_json_value(value)
                group = value_groups.setdefault(
                    canonical,
                    {"value": value, "machines": [], "count": 0},
                )
            else:
                group = value_groups.setdefault(
                    "__MISSING__",
                    {"missing": True, "machines": [], "count": 0},
                )
            group["machines"].append(machine)
            group["count"] += 1

        groups = sorted(
            value_groups.values(),
            key=lambda group: (
                bool(group.get("missing")),
                -group["count"],
                canonical_json_value(group.get("value")) if not group.get("missing") else "",
            ),
        )
        classification = classify_nway_groups(groups)
        if classification == "uniform" and not include_uniform:
            continue

        output_row = {
            "key": row["key"],
            "source": row["source"],
            "path": row["path"],
            "classification": classification,
            "present_count": sum(1 for machine in machines if machine in row["machine_values"]),
            "missing_count": sum(1 for machine in machines if machine not in row["machine_values"]),
            "group_count": len(groups),
            "groups": groups,
        }
        importance = nway_importance(output_row, len(machines))
        output_row["importance"] = importance["score"]
        output_row["importance_reasons"] = importance["reasons"]
        output_rows.append(output_row)

    if sort_mode == "importance":
        output_rows = sorted(
            output_rows,
            key=lambda row: (
                -row["importance"],
                *domain_rank(row["source"]),
                row["path"],
            ),
        )
    else:
        output_rows = sorted(output_rows, key=lambda row: (*domain_rank(row["source"]), row["path"]))
    row_count = len(output_rows)
    patterns = nway_patterns(output_rows, pattern_sort_mode)
    if key_limit is not None:
        output_rows = output_rows[:key_limit]

    return {
        "expected_os": expected_os,
        "machine_count": len(machines),
        "latest_snapshots": [latest[machine].to_json() for machine in machines],
        "row_count": row_count,
        "shown_row_count": len(output_rows),
        "include_uniform": include_uniform,
        "sort": sort_mode,
        "pattern_sort": pattern_sort_mode,
        "patterns": patterns,
        "rows": output_rows,
    }


def format_nway_text(summary: dict[str, Any]) -> str:
    lines = [f"nway: {summary.get('expected_os') or 'any-os'} / {summary['machine_count']} machines"]
    snapshots = summary.get("latest_snapshots", [])
    if not snapshots:
        lines.append("No matching latest snapshots found.")
        return "\n".join(lines)

    lines.append("latest snapshots:")
    for snapshot in snapshots:
        lines.append(f"- {snapshot.get('machine')} / {snapshot.get('os')} / {snapshot.get('captured_at')}")

    lines.append("")
    key_kind = "all keys" if summary.get("include_uniform") else "non-uniform keys"
    lines.append(
        f"keys: showing {summary['shown_row_count']} of {summary['row_count']} {key_kind} "
        f"(sort={summary.get('sort')})"
    )
    rows = summary["rows"]
    if not rows:
        lines.append("No differing keys found.")
        return "\n".join(lines)

    lines.append("")
    for index, row in enumerate(rows):
        if index:
            lines.append("")
        reason_text = ", ".join(row.get("importance_reasons") or [])
        suffix = f"; {reason_text}" if reason_text else ""
        lines.append(f"{row['key']} [{row['classification']}, importance={row.get('importance', 0)}{suffix}]")
        for group in row["groups"]:
            value = "<missing>" if group.get("missing") else compact(group.get("value"), 96)
            lines.append(f"  {value}: {', '.join(group['machines'])}")
    return "\n".join(lines)


def format_nway_patterns_text(summary: dict[str, Any], key_limit: int) -> str:
    lines = [f"nway patterns: {summary.get('expected_os') or 'any-os'} / {summary['machine_count']} machines"]
    snapshots = summary.get("latest_snapshots", [])
    if not snapshots:
        lines.append("No matching latest snapshots found.")
        return "\n".join(lines)

    lines.append("latest snapshots:")
    for snapshot in snapshots:
        lines.append(f"- {snapshot.get('machine')} / {snapshot.get('os')} / {snapshot.get('captured_at')}")

    patterns = summary.get("patterns", [])
    lines.append("")
    key_kind = "all keys" if summary.get("include_uniform") else "non-uniform keys"
    lines.append(f"patterns={len(patterns)}, {key_kind}={summary['row_count']} (sort={summary.get('pattern_sort')})")
    if not patterns:
        lines.append("No non-uniform key patterns found.")
        return "\n".join(lines)

    for pattern in patterns:
        lines.append("")
        noun = "key" if pattern["key_count"] == 1 else "keys"
        lines.append(f"{pattern['pattern_text']} ({pattern['key_count']} {noun})")
        keys = pattern["keys"][:key_limit]
        for key in keys:
            lines.append(f"  - {key['key']}")
        hidden = pattern["key_count"] - len(keys)
        if hidden > 0:
            lines.append(f"  ... +{hidden} more")
    return "\n".join(lines)


def drift_summary(
    log_dir: Path,
    *,
    base_machine: str,
    expected_os: str | None,
    before: datetime | None,
    diff_limit: int,
    apply_limit: int,
    include_minor: bool,
) -> dict[str, Any]:
    latest = latest_snapshots_by_machine(log_dir, expected_os=expected_os, before=before)
    base = latest.get(base_machine)
    if base is None:
        raise ValueError(f"no latest snapshot found for base machine: {base_machine}")
    base_apply_logs = apply_logs_for_machine(log_dir, machine=base_machine, before=before)
    comparisons: list[dict[str, Any]] = []
    line_groups_by_line: dict[str, dict[str, Any]] = {}
    for machine, entry in sorted(latest.items()):
        if machine == base_machine:
            continue
        machine_apply_logs = apply_logs_for_machine(log_dir, machine=machine, before=before)
        comparison = compare_snapshots(base.path, entry.path, limit=None)
        diffs = important_diffs(comparison["diffs"], include_minor=include_minor)
        for diff in diffs:
            line = grouped_diff_line_key(diff)
            group = line_groups_by_line.setdefault(
                line,
                {
                    "line": line,
                    "source": diff["source"],
                    "path": diff["path"],
                    "change": diff["change"],
                    "machines": [],
                    "machine_count": 0,
                    "representative_diff": diff,
                },
            )
            group["machines"].append(machine)
            group["machine_count"] += 1
        comparisons.append(
            {
                "machine": machine,
                "snapshot": entry.to_json(),
                "recent_apply_logs": [apply.to_json() for apply in machine_apply_logs[-apply_limit:]]
                if apply_limit > 0
                else [],
                "diff_count": len(diffs),
                "diff_counts": summarize_diff_counts(diffs),
                "diffs": diffs[:diff_limit],
            }
        )
    line_groups = sorted(line_groups_by_line.values(), key=grouped_diff_line_sort_key)
    return {
        "base": base.to_json(),
        "base_recent_apply_logs": [apply.to_json() for apply in base_apply_logs[-apply_limit:]]
        if apply_limit > 0
        else [],
        "expected_os": expected_os,
        "comparisons": comparisons,
        "line_group_count": len(line_groups),
        "line_groups": line_groups,
    }


def format_drift_text(summary: dict[str, Any]) -> str:
    base = summary["base"]
    lines = [
        f"base: {base.get('machine')} / {base.get('os')} / {base.get('captured_at')}",
    ]
    for apply in summary.get("base_recent_apply_logs", []):
        lines.append("  " + format_apply_line(apply))
    lines.append("")
    comparisons = summary["comparisons"]
    if not comparisons:
        lines.append("No other matching machine snapshots found.")
        return "\n".join(lines)
    for comparison in comparisons:
        snap = comparison["snapshot"]
        lines.append(f"vs {snap.get('machine')} / {snap.get('os')} / {snap.get('captured_at')}")
        lines.append(f"  {comparison['diff_counts']}")
        for apply in comparison.get("recent_apply_logs", []):
            lines.append("  " + format_apply_line(apply))
        diffs = comparison["diffs"]
        if not diffs:
            lines.append("  no semantic config differences shown")
        else:
            for diff in diffs:
                lines.append("  " + format_diff_line(diff))
        lines.append("")
    return "\n".join(lines).rstrip()


def format_drift_grouped_lines_text(summary: dict[str, Any], group_limit: int) -> str:
    base = summary["base"]
    lines = [
        f"base: {base.get('machine')} / {base.get('os')} / {base.get('captured_at')}",
        "",
    ]
    groups = summary.get("line_groups", [])
    if not summary.get("comparisons"):
        lines.append("No other matching machine snapshots found.")
        return "\n".join(lines)
    if not groups:
        lines.append("No semantic config differences found.")
        return "\n".join(lines)

    shown = groups[:group_limit]
    lines.append(f"grouped diff lines: showing {len(shown)} of {summary.get('line_group_count', len(groups))}")
    for group in shown:
        lines.append(group["line"])
        lines.append(f"  machines: {', '.join(group['machines'])}")
    hidden = summary.get("line_group_count", len(groups)) - len(shown)
    if hidden > 0:
        lines.append(f"... +{hidden} more")
    return "\n".join(lines)


def limited_drift_line_groups(summary: dict[str, Any], group_limit: int) -> dict[str, Any]:
    limited = dict(summary)
    groups = summary.get("line_groups", [])[:group_limit]
    limited["line_groups"] = groups
    limited["shown_line_group_count"] = len(groups)
    return limited


def apply_log_name(machine: str, timestamp: str | None = None) -> str:
    return f"config_apply_{machine}_{timestamp or now_ts()}.md"


def apply_log_skeleton(args: argparse.Namespace) -> str:
    title = args.title or f"{args.machine} config apply"
    applied_at = getattr(args, "applied_at", None)
    if not applied_at:
        applied_at = format_iso_ts(parse_ts(args.timestamp)) if args.timestamp else format_iso_ts(datetime.now())
    logged_at = getattr(args, "logged_at", None)
    if not logged_at:
        logged_at = format_iso_ts(parse_ts(args.timestamp)) if args.timestamp else format_iso_ts(datetime.now())
    lines = [
        f"# Config Apply: {title}",
        "",
        "- mode: apply",
        f"- machine: {args.machine}",
        f"- applied_at: {applied_at}",
        f"- logged_at: {logged_at}",
        f"- recipe_id: {args.recipe_id or 'TODO'}",
        f"- recipe_type: {getattr(args, 'recipe_type', None) or 'TODO'}",
        f"- platform: {args.platform or 'TODO'}",
        f"- application: {args.application or 'TODO'}",
        f"- target: `{args.target or 'TODO'}`",
        f"- approved request: `{args.approved_text or 'TODO'}`",
        "",
        "## Snapshots",
        "",
        f"- before: `{args.before or 'TODO'}`",
        f"- reference: `{args.reference or 'TODO'}`",
        f"- verification: `{args.verification or 'TODO'}`",
        "",
        "## Values",
        "",
        "- old: `TODO`",
        "- new: `TODO`",
        "",
        "## Change",
        "",
        "TODO",
        "",
        "## Backup",
        "",
        "TODO",
        "",
        "## Verification",
        "",
        "TODO",
        "",
    ]
    return "\n".join(lines)


def print_entries(entries: list[LogEntry], json_output: bool) -> None:
    if json_output:
        print(json.dumps([entry.to_json() for entry in entries], ensure_ascii=False, indent=2))
        return
    for entry in entries:
        pieces = [format_ts(entry.timestamp), entry.kind, entry.machine_from_name]
        if entry.kind == "snapshot":
            pieces.extend([entry.os_name or "unknown-os", "valid" if entry.valid else "invalid"])
        elif entry.kind == "apply":
            recipe = entry.recipe_id or "unknown-recipe"
            if entry.recipe_type:
                recipe = f"{entry.recipe_type}:{recipe}"
            pieces.extend([recipe, entry.application or "unknown-app", entry.title or entry.path.name])
        if entry.error:
            pieces.append(entry.error)
        pieces.append(str(entry.path))
        print("\t".join(pieces))


def cmd_latest(args: argparse.Namespace) -> int:
    entry = latest_snapshot(
        args.log_dir,
        machine=args.machine,
        expected_os=args.expected_os,
        before=parse_ts(args.before) if args.before else None,
    )
    if entry is None:
        print("no matching snapshot found", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(entry.to_json(), ensure_ascii=False, indent=2))
    else:
        print(entry.path)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = filtered_entries(
        args.log_dir,
        kind=args.kind,
        machine=args.machine,
        expected_os=args.expected_os,
        before=parse_ts(args.before) if args.before else None,
        valid_only=args.valid_only,
    )
    if args.limit is not None:
        entries = entries[-args.limit :]
    print_entries(entries, args.json)
    return 0


def cmd_compare_summary(args: argparse.Namespace) -> int:
    summary = compare_snapshots(args.left, args.right, args.limit)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_compare_text(summary))
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    machine = None if args.all_machines else args.machine or default_machine()
    summary = timeline_summary(
        args.log_dir,
        machine=machine,
        expected_os=args.expected_os,
        before=parse_ts(args.before) if args.before else None,
        limit=args.limit,
        diff_limit=args.diff_limit,
        include_minor=args.include_minor,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_timeline_text(summary))
    return 0


def cmd_nway(args: argparse.Namespace) -> int:
    summary = nway_summary(
        args.log_dir,
        expected_os=args.expected_os,
        before=parse_ts(args.before) if args.before else None,
        key_limit=args.key_limit,
        include_uniform=args.include_uniform,
        include_minor=args.include_minor,
        sort_mode=args.sort,
        pattern_sort_mode=args.pattern_sort,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.patterns:
        print(format_nway_patterns_text(summary, args.pattern_key_limit))
    else:
        print(format_nway_text(summary))
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    base_machine = args.base_machine or default_machine()
    try:
        summary = drift_summary(
            args.log_dir,
            base_machine=base_machine,
            expected_os=args.expected_os,
            before=parse_ts(args.before) if args.before else None,
            diff_limit=args.diff_limit,
            apply_limit=args.apply_limit,
            include_minor=args.include_minor,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        if args.group_lines:
            summary = limited_drift_line_groups(summary, args.group_limit)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.group_lines:
        print(format_drift_grouped_lines_text(summary, args.group_limit))
    else:
        print(format_drift_text(summary))
    return 0


def cmd_apply_log_skeleton(args: argparse.Namespace) -> int:
    dt = parse_ts(args.timestamp) if args.timestamp else datetime.now()
    args.timestamp = format_ts(dt)
    args.logged_at = format_iso_ts(dt)
    applied_at = getattr(args, "applied_at", None)
    args.applied_at = format_iso_ts(parse_ts(applied_at)) if applied_at else args.logged_at
    text = apply_log_skeleton(args)
    if args.write:
        args.log_dir.mkdir(parents=True, exist_ok=True)
        path = args.log_dir / apply_log_name(args.machine, args.timestamp)
        if path.exists() and not args.force:
            print(f"error: file exists: {path}", file=sys.stderr)
            return 1
        path.write_text(text, encoding="utf-8")
        print(path)
    else:
        sys.stdout.write(text)
    return 0


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_snapshot(path: Path, machine: str, os_name: str, captured_at: str, settings: dict[str, Any]) -> None:
    write_json(
        path,
        {
            "machine": machine,
            "os": os_name,
            "captured_at": captured_at,
            "code.settings": {"mtime": captured_at, "value": settings},
        },
    )


def make_apply_log(
    path: Path,
    *,
    title: str,
    recipe_id: str,
    application: str,
    platform: str,
    before: str,
    reference: str,
    verification: str,
    applied_at: str | None = None,
) -> None:
    logged_at = format_iso_ts(parse_ts(path.name.removeprefix('config_apply_anomura_').removesuffix('.md')))
    applied_at = applied_at or logged_at
    path.write_text(
        "\n".join(
            [
                f"# Config Apply: {title}",
                "",
                "- mode: apply",
                "- machine: anomura",
                f"- applied_at: {applied_at}",
                f"- logged_at: {logged_at}",
                f"- recipe_id: {recipe_id}",
                "- recipe_type: config",
                f"- application: {application}",
                f"- platform: {platform}",
                "- target: `demo`",
                "- approved request: `demo apply`",
                "",
                "## Snapshots",
                "",
                f"- before: `{before}`",
                f"- reference: `{reference}`",
                f"- verification: `{verification}`",
                "",
                "## Values",
                "",
                "- old `code.settings.value[\"window.zoomLevel\"]`: `2`",
                "- new `code.settings.value[\"window.zoomLevel\"]`: `1`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def self_test_latest_and_os_filter(tmp: Path) -> None:
    log_dir = tmp / "log" / "config"
    log_dir.mkdir(parents=True)
    make_snapshot(
        log_dir / "config_snapshot_anomura_2026-06-04_10-00-00.json",
        "anomura",
        "win",
        "2026-06-04T10:00:00",
        {"window.zoomLevel": 2},
    )
    make_snapshot(
        log_dir / "config_snapshot_anomura_2026-06-04_11-00-00.json",
        "anomura",
        "mac",
        "2026-06-04T11:00:00",
        {"window.zoomLevel": 1},
    )
    make_snapshot(
        log_dir / "config_snapshot_anomura_2026-06-04_12-00-00.json",
        "anomura",
        "mac",
        "2026-06-04T12:00:00",
        {"window.zoomLevel": 0},
    )
    make_snapshot(
        log_dir / "config_isopoda_2026-06-04_09-00-00.json",
        "isopoda",
        "mac",
        "2026-06-04T09:00:00",
        {"window.zoomLevel": 1},
    )

    entry = latest_snapshot(log_dir, machine="anomura", expected_os="mac", before=None)
    assert entry is not None
    assert_equal(entry.path.name, "config_snapshot_anomura_2026-06-04_12-00-00.json", "latest mac")

    before = parse_ts("2026-06-04_11-30-00")
    entry = latest_snapshot(log_dir, machine="anomura", expected_os="mac", before=before)
    assert entry is not None
    assert_equal(entry.path.name, "config_snapshot_anomura_2026-06-04_11-00-00.json", "latest before")

    entry = latest_snapshot(log_dir, machine="isopoda", expected_os="mac", before=None)
    assert entry is not None
    assert_equal(entry.path.name, "config_isopoda_2026-06-04_09-00-00.json", "legacy scratch-style snapshot")


def self_test_compare_ignores_capture_metadata(tmp: Path) -> None:
    left = tmp / "left.json"
    right = tmp / "right.json"
    make_snapshot(left, "a", "mac", "2026-06-04T10:00:00", {"editor.fontSize": 14})
    make_snapshot(right, "a", "mac", "2026-06-04T10:01:00", {"editor.fontSize": 14})
    summary = compare_snapshots(left, right, limit=20)
    assert_equal(summary["diffs"], [], "metadata-only diff")

    make_snapshot(right, "a", "mac", "2026-06-04T10:02:00", {"editor.fontSize": 15})
    summary = compare_snapshots(left, right, limit=20)
    assert_equal(summary["diffs"][0]["source"], "code.settings", "changed source")
    assert_equal(summary["diffs"][0]["path"], "editor.fontSize", "changed path")


def self_test_timeline_nway_and_drift(tmp: Path) -> None:
    log_dir = tmp / "log" / "config"
    log_dir.mkdir(parents=True)
    make_snapshot(
        log_dir / "config_snapshot_anomura_2026-06-04_10-00-00.json",
        "anomura",
        "mac",
        "2026-06-04T10:00:00",
        {"window.zoomLevel": 2, "editor.fontSize": 14},
    )
    make_snapshot(
        log_dir / "config_snapshot_anomura_2026-06-04_11-00-00.json",
        "anomura",
        "mac",
        "2026-06-04T11:00:00",
        {"window.zoomLevel": 1, "editor.fontSize": 14},
    )
    make_apply_log(
        log_dir / "config_apply_anomura_2026-06-04_11-00-20.md",
        title="zoom apply",
        recipe_id="editor.settings-key",
        application="vscode",
        platform="mac",
        before="log/config/config_snapshot_anomura_2026-06-04_10-00-00.json",
        reference="log/config/config_snapshot_isopoda_2026-06-04_11-30-00.json",
        verification="log/config/config_snapshot_anomura_2026-06-04_11-00-00.json",
        applied_at="2026-06-04T10:30:00",
    )
    make_apply_log(
        log_dir / "config_apply_anomura_2026-06-04_11-00-30.md",
        title="bad zoom apply",
        recipe_id="editor.settings-key",
        application="vscode",
        platform="mac",
        before="log/config/config_snapshot_anomura_2026-06-04_10-00-00.json",
        reference="log/config/config_snapshot_isopoda_2026-06-04_11-30-00.json",
        verification="log/config/config_snapshot_anomura_2026-06-04_10-00-00.json",
        applied_at="2026-06-04T10:31:00",
    )
    make_snapshot(
        log_dir / "config_snapshot_isopoda_2026-06-04_11-30-00.json",
        "isopoda",
        "mac",
        "2026-06-04T11:30:00",
        {"window.zoomLevel": 1, "editor.fontSize": 15},
    )
    make_snapshot(
        log_dir / "config_snapshot_mysida_2026-06-04_11-40-00.json",
        "mysida",
        "mac",
        "2026-06-04T11:40:00",
        {"window.zoomLevel": 1, "editor.fontSize": 15},
    )

    timeline = timeline_summary(
        log_dir,
        machine="anomura",
        expected_os="mac",
        before=None,
        limit=10,
        diff_limit=10,
        include_minor=True,
    )
    apply_items = [item for item in timeline["items"] if item["kind"] == "apply"]
    snapshot_items = [item for item in timeline["items"] if item["kind"] == "snapshot"]
    assert_equal(snapshot_items[1]["previous_diffs"][0]["path"], "window.zoomLevel", "timeline snapshot diff")
    assert_equal(len(apply_items), 2, "timeline apply count")
    assert_equal(apply_items[0]["consistency"]["status"], "ok", "timeline apply consistency")
    assert_equal(apply_items[0]["consistency"]["keys"], ["code.settings.window.zoomLevel"], "timeline apply key")
    assert_equal(apply_items[1]["consistency"]["conflicts"], ["after"], "timeline conflict side")

    drift = drift_summary(
        log_dir,
        base_machine="anomura",
        expected_os="mac",
        before=None,
        diff_limit=10,
        apply_limit=2,
        include_minor=True,
    )
    assert_equal(len(drift["comparisons"]), 2, "drift comparison count")
    assert_equal(drift["comparisons"][0]["machine"], "isopoda", "drift machine")
    assert_equal(drift["comparisons"][0]["diffs"][0]["path"], "editor.fontSize", "drift changed path")
    assert_equal(drift["line_groups"][0]["machines"], ["isopoda", "mysida"], "drift grouped line machines")
    assert_equal(drift["base_recent_apply_logs"][0]["recipe_id"], "editor.settings-key", "drift base apply log")

    nway = nway_summary(
        log_dir,
        expected_os="mac",
        before=None,
        key_limit=10,
        include_uniform=False,
        include_minor=True,
        sort_mode="key",
        pattern_sort_mode="key-count-desc",
    )
    assert_equal(nway["machine_count"], 3, "nway machine count")
    assert_equal(nway["rows"][0]["key"], "code.settings.editor.fontSize", "nway key")
    assert_equal(nway["rows"][0]["classification"], "split", "nway classification")
    assert_equal(nway["patterns"][0]["pattern_text"], "[{isopoda, mysida}, {anomura}]", "nway pattern")


def self_test_apply_log_skeleton(tmp: Path) -> None:
    log_dir = tmp / "log" / "config"
    args = argparse.Namespace(
        machine="anomura",
        platform="mac",
        application="vscode",
        recipe_id="editor.settings-key",
        target="~/Library/Application Support/Code/User/settings.json",
        approved_text="apply window.zoomLevel",
        before="before.json",
        reference="reference.json",
        verification="verification.json",
        title="test apply",
        write=True,
        force=False,
        log_dir=log_dir,
        timestamp="2026-06-04_12-34-56",
    )
    with contextlib.redirect_stdout(io.StringIO()):
        rc = cmd_apply_log_skeleton(args)
    assert_equal(rc, 0, "apply log skeleton rc")
    path = log_dir / "config_apply_anomura_2026-06-04_12-34-56.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "- machine: anomura" in text
    assert "- applied_at: 2026-06-04T12:34:56" in text
    assert "- logged_at: 2026-06-04T12:34:56" in text
    assert "recipe_id: editor.settings-key" in text
    assert "recipe_type: TODO" in text
    assert "before.json" in text


def run_self_test() -> int:
    tests = [
        self_test_latest_and_os_filter,
        self_test_compare_ignores_capture_metadata,
        self_test_timeline_nway_and_drift,
        self_test_apply_log_skeleton,
    ]
    with tempfile.TemporaryDirectory(prefix="config-log-helper-test-") as tmpdir:
        tmp = Path(tmpdir)
        for test in tests:
            test_dir = tmp / test.__name__
            test_dir.mkdir()
            test(test_dir)
            print(f"ok {test.__name__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="inspect config snapshot/apply logs")
    parser.add_argument("--self-test", action="store_true", help="run non-destructive temporary-file tests")

    subparsers = parser.add_subparsers(dest="command")

    latest = subparsers.add_parser("latest", help="print the latest matching valid snapshot path")
    add_common_log_args(latest)
    latest.add_argument("--json", action="store_true", help="print structured metadata")
    latest.set_defaults(func=cmd_latest)

    list_cmd = subparsers.add_parser("list", help="list config snapshot/apply log entries")
    add_common_log_args(list_cmd)
    list_cmd.add_argument("--kind", choices=["snapshot", "apply", "all"], default="all")
    list_cmd.add_argument("--limit", type=int, help="show only the last N matching entries")
    list_cmd.add_argument("--valid-only", action="store_true", help="hide invalid snapshot files")
    list_cmd.add_argument("--json", action="store_true", help="print structured metadata")
    list_cmd.set_defaults(func=cmd_list)

    compare = subparsers.add_parser("compare-summary", help="summarize semantic differences between snapshots")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("--limit", type=int, default=80, help="maximum diff rows to show")
    compare.add_argument("--json", action="store_true", help="print structured diff")
    compare.set_defaults(func=cmd_compare_summary)

    timeline = subparsers.add_parser("timeline", help="show raw chronological snapshots/apply logs with apply checks")
    add_common_log_args(timeline)
    timeline.add_argument("--limit", type=int, default=20, help="number of recent log entries to show")
    timeline.add_argument("--diff-limit", type=int, default=3, help="maximum previous-snapshot diff items per snapshot line")
    timeline.add_argument("--include-minor", action="store_true", help="include extension/version noise in snapshot line diffs")
    timeline.add_argument("--all-machines", action="store_true", help="show one chronological timeline across all machines")
    timeline.add_argument("--json", action="store_true", help="print structured timeline")
    timeline.set_defaults(func=cmd_timeline)

    nway = subparsers.add_parser("nway", help="aggregate latest snapshots by key across machines")
    nway.add_argument("--log-dir", type=Path, default=default_log_dir())
    nway.add_argument("--expected-os", choices=["mac", "win", "linux", "unknown"])
    nway.add_argument("--before", help="YYYY-MM-DD_HH-MM-SS or YYYY-MM-DDTHH:MM:SS")
    nway.add_argument("--key-limit", type=int, default=80, help="maximum changed keys to show")
    nway.add_argument("--patterns", action="store_true", help="show machine split patterns instead of key/value rows")
    nway.add_argument("--pattern-key-limit", type=int, default=12, help="maximum keys to list under each split pattern")
    nway.add_argument(
        "--pattern-sort",
        choices=["key-count-desc", "key-count-asc", "importance"],
        default="key-count-desc",
        help="sort split patterns for display",
    )
    nway.add_argument("--sort", choices=["importance", "key"], default="importance", help="sort changed keys for display")
    nway.add_argument("--include-uniform", action="store_true", help="include keys with the same value on every machine")
    nway.add_argument("--include-minor", action="store_true", help="include extension/version noise")
    nway.add_argument("--json", action="store_true", help="print structured N-way aggregation")
    nway.set_defaults(func=cmd_nway)

    drift = subparsers.add_parser("drift", help="compare a base machine with latest snapshots from other machines")
    drift.add_argument("--log-dir", type=Path, default=default_log_dir())
    drift.add_argument("--base-machine")
    drift.add_argument("--expected-os", choices=["mac", "win", "linux", "unknown"])
    drift.add_argument("--before", help="YYYY-MM-DD_HH-MM-SS or YYYY-MM-DDTHH:MM:SS")
    drift.add_argument("--diff-limit", type=int, default=12, help="maximum diff rows per machine")
    drift.add_argument("--group-lines", action="store_true", help="group identical displayed diff lines across machines")
    drift.add_argument("--group-limit", type=int, default=40, help="maximum grouped diff lines to show")
    drift.add_argument("--apply-limit", type=int, default=2, help="recent apply logs to show per machine")
    drift.add_argument("--include-minor", action="store_true", help="include extension/version noise")
    drift.add_argument("--json", action="store_true", help="print structured summary")
    drift.set_defaults(func=cmd_drift)

    skeleton = subparsers.add_parser("apply-log-skeleton", help="create or print a config apply log skeleton")
    skeleton.add_argument("--log-dir", type=Path, default=default_log_dir())
    skeleton.add_argument("--machine", default=default_machine())
    skeleton.add_argument("--platform")
    skeleton.add_argument("--application")
    skeleton.add_argument("--recipe-id")
    skeleton.add_argument("--recipe-type", choices=["config", "patch"])
    skeleton.add_argument("--target")
    skeleton.add_argument("--approved-text")
    skeleton.add_argument("--before")
    skeleton.add_argument("--reference")
    skeleton.add_argument("--verification")
    skeleton.add_argument("--title")
    skeleton.add_argument("--timestamp", help="YYYY-MM-DD_HH-MM-SS; defaults to current time")
    skeleton.add_argument("--applied-at", help="YYYY-MM-DDTHH:MM:SS; defaults to log timestamp")
    skeleton.add_argument("--write", action="store_true", help="write under log/config instead of stdout")
    skeleton.add_argument("--force", action="store_true", help="overwrite an existing skeleton path")
    skeleton.set_defaults(func=cmd_apply_log_skeleton)

    return parser


def add_common_log_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--log-dir", type=Path, default=default_log_dir())
    parser.add_argument("--machine")
    parser.add_argument("--expected-os", choices=["mac", "win", "linux", "unknown"])
    parser.add_argument("--before", help="YYYY-MM-DD_HH-MM-SS or YYYY-MM-DDTHH:MM:SS")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        if args.command:
            parser.error("--self-test cannot be combined with a subcommand")
        return run_self_test()
    if not args.command:
        parser.error("choose a subcommand or --self-test")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
