# Config Apply Recipes

Agent-facing reference for applying approved configuration changes on the current machine.

This file is public bootstrap knowledge. It must not contain private machine names, personal email addresses, real home paths, snapshot contents, or user-specific policy. Private policy lives in `local/`; snapshots and apply logs live in `log/config/`.

The workflow and approval protocol live in [`config-update.md`](config-update.md). This file is the apply side: paths, commands, and file operations.

## Core Rules

- Apply only after explicit user approval.
- Apply only on the current machine.
- Use keys and values selected by `config-update.md` as opaque data. Do not split, rename, normalize, or reinterpret a setting key because of its spelling.
- Prefer copying an observed value from a source snapshot or current file over inventing an application schema.
- Patch only the approved target key, file, directory, command, or block.
- Preserve comments and unrelated content in JSONC and shell profile files.
- Create a backup before writing live config files or replacing live config directories.
- Ask for separate explicit approval before destructive operations such as deleting/replacing directories, uninstalling extensions, removing settings, or restoring from backup.
- Workspace `.vscode/settings.json` is out of scope. These recipes target global/User editor settings only.
- If a safe patch cannot be performed, stop and propose a narrower manual edit or a dedicated helper.

## Snapshot Lookup

Use these snapshot paths before re-discovering shapes:

```text
VS Code User settings        code.settings.value[<settings-key>]
Cursor User settings         cursor.settings.value[<settings-key>]
VS Code extensions           code.extensions.value
Cursor extensions            cursor.extensions.value
VS Code locale               code.locale.value
Cursor locale                cursor.locale.value
Git global config            git.value[<git-key>]
Codex skills                 codex.value.skills
Copilot prompts              copilot.value.prompts
Markdown Preview CSS         crossnote.value["style.less"]
zsh venv helpers             zsh.value.venv_defs
PowerShell venv helpers      powershell.value.venv_defs
Git Bash venv helpers        gitbash.value.venv_defs
```

`values.old` usually comes from the current snapshot. `values.new` usually comes from a source snapshot, private policy in `local/`, or the user's explicit text.

## Default Target Paths

These paths mirror the snapshot scripts. `local/snapshot-paths.json` or explicit user approval may override them.

```python
DEFAULT_PATHS = {
    ("mac", "vscode_user_settings"): "~/Library/Application Support/Code/User/settings.json",
    ("mac", "cursor_user_settings"): "~/Library/Application Support/Cursor/User/settings.json",
    ("mac", "vscode_argv"): "~/.vscode/argv.json",
    ("mac", "cursor_argv"): "~/.cursor/argv.json",
    ("mac", "copilot_prompts"): "~/Library/Application Support/Code/User/prompts",
    ("mac", "crossnote_style"): "~/.local/state/crossnote/style.less",
    ("mac", "codex_skills"): "~/.codex/skills",
    ("mac", "zshrc"): "~/.zshrc",

    ("win", "vscode_user_settings"): r"%APPDATA%\Code\User\settings.json",
    ("win", "cursor_user_settings"): r"%APPDATA%\Cursor\User\settings.json",
    ("win", "vscode_argv"): r"%USERPROFILE%\.vscode\argv.json",
    ("win", "cursor_argv"): r"%USERPROFILE%\.cursor\argv.json",
    ("win", "copilot_prompts"): r"%APPDATA%\Code\User\prompts",
    ("win", "crossnote_style"): r"%USERPROFILE%\.crossnote\style.less",
    ("win", "codex_skills"): r"%USERPROFILE%\.codex\skills",
    ("win", "gitbashrc"): r"%USERPROFILE%\.bashrc",
}
```

## Common Helpers

These snippets are reference code for agents. They are not a mandatory library API.

```python
from pathlib import Path
from datetime import datetime
import filecmp
import json
import os
import shutil
import subprocess


def ts():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def expand(path):
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def path_for(platform, key, overrides=None):
    if overrides and key in overrides:
        return expand(overrides[key])
    return expand(DEFAULT_PATHS[(platform, key)])


def read_text(path, encoding="utf-8-sig"):
    return expand(path).read_text(encoding=encoding)


def write_text(path, text, encoding="utf-8"):
    path = expand(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)


def backup_file(path):
    src = expand(path)
    dst = src.with_name(src.name + f".bak.{ts()}")
    shutil.copy2(src, dst)
    return dst


def backup_dir(path):
    src = expand(path)
    dst = src.with_name(src.name + f".bak.{ts()}")
    shutil.copytree(src, dst)
    return dst


def run_checked(args):
    subprocess.run(args, check=True)


def run_text(args):
    r = subprocess.run(args, check=True, capture_output=True, text=True)
    return r.stdout.strip()


def files_identical(a, b):
    a, b = expand(a), expand(b)
    return a.exists() and b.exists() and filecmp.cmp(a, b, shallow=False)


def directories_equivalent(a, b):
    a, b = expand(a), expand(b)
    if not a.exists() or not b.exists():
        return False
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(directories_equivalent(a / name, b / name) for name in cmp.common_dirs)


def is_workspace_settings(path):
    path = expand(path)
    return path.name == "settings.json" and ".vscode" in path.parts


def snapshot_get(snapshot, source, *keys):
    cur = snapshot[source]["value"]
    for key in keys:
        cur = cur[key]
    return cur


def snapshot_get_optional(snapshot, source, *keys, default=None):
    try:
        return snapshot_get(snapshot, source, *keys)
    except (KeyError, TypeError):
        return default


def json_literal(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def run_jsonc_patch(path, updates, *, create=False, backup=True, dry_run=False):
    args = [
        "python3",
        "scripts/jsonc-patch-keys.py",
        str(path),
        "--dry-run" if dry_run else "--write",
    ]
    if backup:
        args.append("--backup")
    if create:
        args.append("--create")
    for key, value in updates.items():
        args += ["--set", key, json_literal(value)]
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip() or None


def replace_marked_block(text, marker_name, block_text):
    start = f"# >>> {marker_name}"
    end = f"# <<< {marker_name}"
    block = f"{start}\n{block_text.rstrip()}\n{end}\n"
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        return before.rstrip() + "\n\n" + block + after.lstrip()
    return text.rstrip() + "\n\n" + block
```

## Recipe: `git.user-name`

Purpose: set global Git author name.

```python
old = snapshot_get_optional(current_snapshot, "git", "user.name")
new = approved_values["user.name"]

run_checked(["git", "config", "--global", "user.name", new])

verified = run_text(["git", "config", "--global", "user.name"])
assert verified == new
```

Rollback:

```python
run_checked(["git", "config", "--global", "user.name", old])
```

Log: old value, new value, command, verification snapshot.

## Recipe: `git.user-email`

Purpose: set global Git author email.

```python
old = snapshot_get_optional(current_snapshot, "git", "user.email")
new = approved_values["user.email"]

run_checked(["git", "config", "--global", "user.email", new])

verified = run_text(["git", "config", "--global", "user.email"])
assert verified == new
```

Rollback:

```python
run_checked(["git", "config", "--global", "user.email", old])
```

Log: old value, new value, whether privacy was involved, verification snapshot.

## Recipe: `editor.settings-key`

Purpose: patch one or more VS Code/Cursor User `settings.json` keys.

Inputs:

```python
application = "vscode"        # or "cursor"
platform = "mac"              # or "win"
approved_updates = {          # exact key strings selected by config-update.md
    "editor.fontSize": 14,
    "window.zoomLevel": 0,
}
```

Resolve target:

```python
path_key = f"{application}_user_settings"
settings_path = path_for(platform, path_key, path_overrides)

assert not is_workspace_settings(settings_path)
```

Read old/new values:

```python
snapshot_source = "code.settings" if application == "vscode" else "cursor.settings"

old_values = {
    key: snapshot_get(current_snapshot, snapshot_source, key)
    for key in approved_updates
    if key in current_snapshot[snapshot_source]["value"]
}

# If copying from another snapshot, approved_updates normally came from:
# approved_updates[key] = snapshot_get(source_snapshot, snapshot_source, key)
```

Apply:

```python
settings_path = expand(settings_path)

backup_path = run_jsonc_patch(settings_path, approved_updates, create=True, backup=True)
```

Verify:

```python
# Re-read directly with the same JSONC semantics used by the snapshot script,
# then record a verification snapshot and check code.settings/cursor.settings.
```

Rollback:

```python
if old_values:
    run_jsonc_patch(settings_path, old_values, create=False, backup=True)
elif backup_path:
    shutil.copy2(backup_path, settings_path)
```

Notes:

- This recipe is for global/User settings only.
- Multiple keys are allowed when approved together.
- There is no stable general VS Code/Cursor CLI for setting arbitrary User settings; edit User `settings.json`.

## Recipe: `editor.extension-install`

Purpose: install or update a VS Code/Cursor extension.

```python
application = "vscode"  # or "cursor"
cli = "code" if application == "vscode" else "cursor"
extension = approved_extension_id  # usually "publisher.name"; sometimes "publisher.name@version"

before = run_text([cli, "--list-extensions", "--show-versions"])
run_checked([cli, "--install-extension", extension])
after = run_text([cli, "--list-extensions", "--show-versions"])
```

Rollback, only if explicitly approved:

```python
run_checked([cli, "--uninstall-extension", extension.split("@", 1)[0]])
```

Log: extension id, before/after version lines, command, verification snapshot.

Notes:

- Exact version pinning is marketplace-dependent.
- Extension auto-update can reintroduce drift.

## Recipe: `editor.locale`

Purpose: set VS Code/Cursor UI locale via the editor argv/config file.

```python
application = "vscode"  # or "cursor"
platform = "mac"        # or "win"
locale = approved_locale

argv_path = path_for(platform, f"{application}_argv", path_overrides)

backup_path = run_jsonc_patch(argv_path, {"locale": locale}, create=True, backup=True)
```

Verify:

```python
after = read_text(argv_path)
# Then record a verification snapshot and check code.locale.value or cursor.locale.value.
```

Rollback:

```python
if old_locale is not None:
    run_jsonc_patch(argv_path, {"locale": old_locale}, create=False, backup=True)
elif backup_path:
    shutil.copy2(backup_path, argv_path)
```

Notes: editor reload/restart is usually required.

## Recipe: `codex.skill-directory`

Purpose: deploy or update one Codex skill directory.

```python
skill_name = approved_skill_name
source = expand(approved_source_skill_dir)
dest_root = path_for(platform, "codex_skills", path_overrides)
dest = dest_root / skill_name

assert (source / "SKILL.md").is_file()

if not dest.exists():
    shutil.copytree(source, dest)
    backup = None
elif directories_equivalent(source, dest):
    backup = None
else:
    backup = backup_dir(dest)
    shutil.rmtree(dest)
    shutil.copytree(source, dest)
```

Verify:

```python
assert (dest / "SKILL.md").is_file()
# Then record a verification snapshot and check codex.value.skills.
```

Rollback:

```python
if backup:
    shutil.rmtree(dest)
    shutil.copytree(backup, dest)
```

Log: source, destination, backup path, verification snapshot.

## Recipe: `copilot.prompt-file`

Purpose: deploy or update one Copilot prompt file.

```python
prompt_name = approved_prompt_name
source = expand(approved_source_prompt_file)
dest_dir = path_for(platform, "copilot_prompts", path_overrides)
dest = dest_dir / f"{prompt_name}.prompt.md"

assert source.is_file()
dest.parent.mkdir(parents=True, exist_ok=True)

if not dest.exists():
    backup = None
    shutil.copy2(source, dest)
elif files_identical(source, dest):
    backup = None
else:
    backup = backup_file(dest)
    shutil.copy2(source, dest)
```

Verify:

```python
assert dest.is_file()
# Then record a verification snapshot and check copilot.value.prompts.
```

Rollback:

```python
if backup:
    shutil.copy2(backup, dest)
```

Log: source, destination, backup path, verification snapshot.

## Recipe: `markdown.mpe-css`

Purpose: deploy Markdown Preview Enhanced global CSS/Less.

```python
source = expand(approved_source_style_less)
dest = path_for(platform, "crossnote_style", path_overrides)

assert source.is_file()
dest.parent.mkdir(parents=True, exist_ok=True)

if not dest.exists():
    backup = None
elif files_identical(source, dest):
    backup = None
else:
    backup = backup_file(dest)

shutil.copy2(source, dest)
```

Optional Windows setting when approved:

```python
if approved_mpe_config_path_setting:
    settings_path = path_for(platform, f"{approved_editor_application}_user_settings", path_overrides)
    run_jsonc_patch(
        settings_path,
        {"markdown-preview-enhanced.configPath": approved_mpe_config_path_setting},
        create=True,
        backup=True,
    )
```

Verify:

```python
assert dest.is_file()
# Then record a verification snapshot and check crossnote.value["style.less"].
```

Rollback:

```python
if backup:
    shutil.copy2(backup, dest)
```

Log: source, destination, backup path, verification snapshot.

## Recipe: `webview.ctrlf-patch`

Purpose: apply the local macOS webview Control-F forward-character patch.

Preview:

```python
run_checked(["node", "scripts/patch-vscode-webview-ctrlf.js", "--dry-run"])
```

Apply:

```python
args = ["node", "scripts/patch-vscode-webview-ctrlf.js"]
if approved_all_installs:
    args.append("--all")
run_checked(args)
```

Verify:

```python
run_checked(["node", "scripts/patch-vscode-webview-ctrlf.js", "--status"])
```

Rollback, only if approved:

```python
run_checked(["node", "scripts/patch-vscode-webview-ctrlf.js", "--restore"])
```

Log: detected installs, command output, editor reload/test result.

Notes: this modifies installed extension assets; extension updates may remove the patch.

## Recipe: `shell.venv-alias`

Purpose: add or update shell helpers that activate named virtual environments.

Resolve profile:

```python
if platform == "mac" and shell == "zsh":
    profile = path_for("mac", "zshrc", path_overrides)
elif platform == "win" and shell == "powershell":
    profile = expand(run_text(["powershell", "-NoProfile", "-Command", "$PROFILE"]))
elif platform == "win" and shell == "gitbash":
    profile = path_for("win", "gitbashrc", path_overrides)
else:
    raise ValueError(f"unsupported shell target: {platform=} {shell=}")
```

Apply:

```python
text = read_text(profile) if expand(profile).exists() else ""
backup = backup_file(profile) if expand(profile).exists() else None

new_text = replace_marked_block(
    text,
    marker_name=approved_block_name,
    block_text=approved_shell_block,
)
write_text(profile, new_text)
```

Verify:

```python
after = read_text(profile)
assert approved_block_name in after
# Then record a verification snapshot and check zsh/powershell/gitbash venv_defs.
```

Rollback:

```python
if backup:
    shutil.copy2(backup, profile)
```

Log: shell, profile path, block name, backup path, verification snapshot.

Notes: shell syntax is platform-specific. Do not apply a zsh block to PowerShell or Git Bash.

## Apply Log Skeleton

Use one file per approved command run:

```text
log/config/config_apply_<machine>_YYYY-MM-DD_HH-MM-SS.md
```

Minimal body:

```markdown
# Config Apply: <short title>

- mode: apply
- machine: <machine>
- applied_at: <YYYY-MM-DDTHH:MM:SS>
- logged_at: <YYYY-MM-DDTHH:MM:SS>
- recipe_id: <recipe-id>
- application: <vscode|cursor|git|shell|...>
- platform: <mac|win|...>
- target: `<path-or-command>`
- approved request: `<exact user approval text>`

## Snapshots

- before: `log/config/config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json`
- reference: `log/config/config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json`
- verification: `log/config/config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json`

## Values

- old:
- new:

## Change

TODO

## Backup

TODO

## Verification

TODO

## Notes

- Any drift, limitation, reload requirement, or manual test result.
```
