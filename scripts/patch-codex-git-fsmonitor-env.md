# `patch-codex-git-fsmonitor-env.sh`

Set `CODEX_APPLY_GIT_CFG=0` for the macOS GUI session so Codex does not inject Git fsmonitor config into its internal Git commands.

Note: this is an experimental local patch. The `CODEX_APPLY_GIT_CFG` behavior may change in future Codex releases; after Codex updates, re-check with `status`. Repositories with active Git hooks should be reviewed before use.

## Problem

When Codex runs inside Cursor or Codex Desktop app against Git repositories under Dropbox, its internal Git commands may create `.git/fsmonitor--daemon*` artifacts. Those artifacts can produce Dropbox sync noise.

## What It Changes

The default `apply` path:

- runs `launchctl setenv CODEX_APPLY_GIT_CFG=0`
- installs a user LaunchAgent at `~/Library/LaunchAgents/org.codex-library.codex-git-config-env.plist`
- loads that LaunchAgent for future logins

It does not edit shell rc files or repository config.

## Usage

Check current status:

```bash
bash scripts/patch-codex-git-fsmonitor-env.sh status
```

Apply on this Mac:

```bash
bash scripts/patch-codex-git-fsmonitor-env.sh apply
```

Then fully quit and restart Cursor and Codex Desktop app.

Remove the LaunchAgent and GUI-session environment variable:

```bash
bash scripts/patch-codex-git-fsmonitor-env.sh remove
```

Check a specific repository for existing artifacts:

```bash
bash scripts/patch-codex-git-fsmonitor-env.sh status /path/to/repo
```

## Fallback Blocker

For a specific repository where the environment approach cannot be used, create a non-empty `.git/fsmonitor--daemon.ipc` directory so the daemon cannot bind its socket:

```bash
bash scripts/patch-codex-git-fsmonitor-env.sh blocker-apply /path/to/repo
bash scripts/patch-codex-git-fsmonitor-env.sh blocker-remove /path/to/repo
```

The blocker is a fallback. Do not use it when the environment approach is sufficient.
