#!/bin/bash
# Disable Codex's injected Git fsmonitor config on macOS by setting CODEX_APPLY_GIT_CFG=0.
set -euo pipefail

LABEL="org.codex-library.codex-git-config-env"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
VALUE=0

usage() {
  cat <<'EOF'
usage:
  bash scripts/patch-codex-git-fsmonitor-env.sh status [repo]
  bash scripts/patch-codex-git-fsmonitor-env.sh apply
  bash scripts/patch-codex-git-fsmonitor-env.sh remove
  bash scripts/patch-codex-git-fsmonitor-env.sh blocker-apply [repo]
  bash scripts/patch-codex-git-fsmonitor-env.sh blocker-remove [repo]

This is an unofficial local patch. Use at your own risk.
EOF
}

require_macos() {
  if [ "$(uname -s)" != "Darwin" ]; then
    echo "ERROR: this command is macOS-only." >&2
    exit 1
  fi
}

status() {
  local repo="${1:-}"
  require_macos

  echo "== launchctl getenv =="
  local val
  val="$(launchctl getenv CODEX_APPLY_GIT_CFG 2>/dev/null || true)"
  echo "  CODEX_APPLY_GIT_CFG=${val:-(unset)}"

  echo "== LaunchAgent =="
  [ -f "$PLIST" ] && echo "  plist: present ($PLIST)" || echo "  plist: absent"
  if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    echo "  agent: loaded"
  else
    echo "  agent: not loaded"
  fi

  echo "== running Codex processes =="
  local found=0
  local p
  for p in $(pgrep -f 'codex app-server|Codex.app/Contents/Resources/codex' 2>/dev/null || true); do
    found=1
    local inherited
    inherited="$(ps eww -p "$p" 2>/dev/null | tr ' ' '\n' | grep '^CODEX_APPLY_GIT_CFG=' || true)"
    echo "  PID $p: ${inherited:-(CODEX_APPLY_GIT_CFG not inherited; restart required)}"
  done
  [ "$found" = 0 ] && echo "  no running Codex processes found"

  echo "== fsmonitor daemon =="
  pgrep -fl 'fsmonitor--daemon run' 2>/dev/null || echo "  daemon: none"

  if [ -n "$repo" ] && [ -d "$repo/.git" ]; then
    echo "== $repo artifacts =="
    local found_artifacts
    found_artifacts="$(find "$repo/.git" -maxdepth 2 -name 'fsmonitor--daemon*' -print 2>/dev/null || true)"
    [ -n "$found_artifacts" ] && echo "$found_artifacts" || echo "  artifact: none"
  fi
}

apply_env() {
  require_macos
  launchctl setenv CODEX_APPLY_GIT_CFG "$VALUE"
  echo "[apply] launchctl setenv CODEX_APPLY_GIT_CFG=$VALUE"

  mkdir -p "$HOME/Library/LaunchAgents"
  /usr/bin/plutil -create xml1 "$PLIST"
  /usr/bin/plutil -replace Label -string "$LABEL" "$PLIST"
  /usr/bin/plutil -replace ProgramArguments -json "[\"/bin/launchctl\",\"setenv\",\"CODEX_APPLY_GIT_CFG\",\"$VALUE\"]" "$PLIST"
  /usr/bin/plutil -replace RunAtLoad -bool true "$PLIST"
  echo "[apply] wrote $PLIST"

  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
    echo "[apply] bootstrapped LaunchAgent"
  else
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load -w "$PLIST"
    echo "[apply] loaded LaunchAgent (legacy load -w)"
  fi

  echo "[apply] restart Cursor and Codex Desktop app so they inherit the environment."
}

remove_env() {
  require_macos
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null \
    || launchctl unload "$PLIST" 2>/dev/null \
    || true
  rm -f "$PLIST"
  echo "[remove] removed LaunchAgent: $PLIST"
  launchctl unsetenv CODEX_APPLY_GIT_CFG
  echo "[remove] launchctl unsetenv CODEX_APPLY_GIT_CFG"
  echo "[remove] restart Cursor and Codex Desktop app to return to default behavior."
}

blocker_apply() {
  local repo="${1:-$PWD}"
  cd "$repo"
  [ -d .git ] || { echo "ERROR: '$repo' is not a git repository with a .git directory" >&2; exit 1; }
  git -c core.fsmonitor=true fsmonitor--daemon stop 2>/dev/null || true
  sleep 1
  chflags nouchg .git/fsmonitor--daemon.ipc 2>/dev/null || true
  rm -rf .git/fsmonitor--daemon .git/fsmonitor--daemon.ipc
  mkdir -p .git/fsmonitor--daemon.ipc
  : > .git/fsmonitor--daemon.ipc/.keep
  echo "[blocker] applied: $repo/.git/fsmonitor--daemon.ipc is now a non-empty directory"
}

blocker_remove() {
  local repo="${1:-$PWD}"
  cd "$repo"
  [ -d .git ] || { echo "ERROR: '$repo' is not a git repository with a .git directory" >&2; exit 1; }
  rm -rf .git/fsmonitor--daemon.ipc
  echo "[blocker] removed: $repo"
}

cmd="${1:-}"
shift || true
case "$cmd" in
  status) status "$@" ;;
  apply) apply_env "$@" ;;
  remove) remove_env "$@" ;;
  blocker-apply) blocker_apply "$@" ;;
  blocker-remove) blocker_remove "$@" ;;
  -h|--help|help|"") usage ;;
  *) usage >&2; exit 2 ;;
esac
