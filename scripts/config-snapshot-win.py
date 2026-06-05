#!/usr/bin/env python3
"""config-snapshot (win) — 端末の live 設定状態を JSON で stdout に出力する。

mac 版 (config-snapshot-mac.py) の Windows 対応。構造・key は mac 版と同形だが、
パス (APPDATA / .crossnote)・コマンド (where, powershell)・shell (powershell + gitbash) が異なる。
mac 専用 source (brew / karabiner / fonts) は持たない。
設定取得は read-only（`--scratch` / `--log` 指定時だけ snapshot JSON を書く）。
各 source key = { "mtime": <backing file mtime or null>, "value": <取得内容> }。
mtime が無意味な source (コマンドで取るもの) は null（実質は top-level captured_at が時刻）。
settings.json / argv.json は JSONC (// コメント可) を許容してパースする。
取れるものは raw に取得し、取捨・解釈は後段に回す（捨てると回復できないため）。
注意: 出力には git user.email や各種設定値など、個人情報を含みうる。scratch/ と log/ は gitignore 対象だが、
共有・公開前には内容を確認すること。

パスは built-in DEFAULTS。`<repo>\\local\\snapshot-paths.json` があれば部分上書きマージ
（gitignore 領域。無ければ DEFAULTS で動くので外部ユーザーも実行可）。`--paths FILE` でも指定可。

注: 子プロセス出力は bytes 受信 + UTF-8 明示デコード (cp932 デコードクラッシュ回避)。

使い方:  python config-snapshot-win.py            # JSON を stdout に表示
         python config-snapshot-win.py --scratch  # <repo>\\scratch\\config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json に書く
         python config-snapshot-win.py --log      # <repo>\\log\\config\\config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json に書く
         python config-snapshot-win.py --paths foo.json
"""
import argparse
import datetime
import json
import os
import re
import socket
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOME = os.path.expanduser("~")
APPDATA = os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))

DEFAULTS = {
    "code_user": os.path.join(APPDATA, "Code", "User"),
    "cursor_user": os.path.join(APPDATA, "Cursor", "User"),
    "code_ext_manifest": os.path.join(HOME, ".vscode", "extensions", "extensions.json"),
    "cursor_ext_manifest": os.path.join(HOME, ".cursor", "extensions", "extensions.json"),
    "code_argv": os.path.join(HOME, ".vscode", "argv.json"),
    "cursor_argv": os.path.join(HOME, ".cursor", "argv.json"),
    "venvs": os.path.join(HOME, ".venvs"),
    "gitconfig": os.path.join(HOME, ".gitconfig"),
    "bashrc": os.path.join(HOME, ".bashrc"),
    "crossnote_style": os.path.join(HOME, ".crossnote", "style.less"),
    "jupyter_kernels": os.path.join(APPDATA, "jupyter", "kernels"),
    "claude_commands": os.path.join(HOME, ".claude", "commands"),
    "codex_skills": os.path.join(HOME, ".codex", "skills"),
    "qwen_settings": os.path.join(HOME, ".qwen", "settings.json"),
    "qwen_skills": os.path.join(HOME, ".qwen", "skills"),
    "copilot_prompts": os.path.join(APPDATA, "Code", "User", "prompts"),
    "latexmkrc": os.path.join(HOME, ".latexmkrc"),
    "claude_md": os.path.join(HOME, ".claude", "CLAUDE.md"),
    "claude_legacy_local_md": os.path.join(HOME, ".claude", "CLAUDE.local.md"),
}


def require_platform():
    if os.name != "nt":
        raise SystemExit(
            "error: config-snapshot-win.py must be run on Windows; "
            "use config-snapshot-mac.py on macOS"
        )


def iso(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def mtime(path):
    try:
        return iso(os.path.getmtime(os.path.expanduser(path)))
    except OSError:
        return None


def read_text(path):
    try:
        # utf-8-sig: 先頭 BOM があれば除去 (PowerShell profile 等は BOM 付きで保存される)
        with open(os.path.expanduser(path), encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return None


def run(args):
    """コマンドを実行し stdout を返す。失敗時 None。
    bytes 受信 + UTF-8 明示デコードでロケール (cp932) デコードクラッシュを回避。"""
    try:
        cmd = subprocess.list2cmdline(args) if isinstance(args, list) else args
        r = subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.SubprocessError):
        return None


def first_line(s):
    return s.splitlines()[0] if s else None


def which(name):
    return first_line(run(["where.exe", name]))


def venv_defs(text):
    # venv を activate している行を拾う。venv 名や年に依存せず activation の機構で grep:
    #   .venvs パス参照 / activate スクリプト (Activate.ps1, bin|Scripts/activate)。
    #   過検出は許容し、取捨・解釈は後段に回す。
    return [ln for ln in lines(text) if re.search(r"\.venvs|activate", ln, re.IGNORECASE)]


def strip_jsonc(s):
    """// と /* */ コメント (文字列内は除く) と trailing comma を除去。"""
    out = []
    i, n = 0, len(s)
    in_str = esc = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and s[i + 1] == "/":
            i += 2
            while i < n and s[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return strip_trailing_commas("".join(out))


def strip_trailing_commas(s):
    """JSON 文字列内は触らず、object/array 末尾の trailing comma だけ除去する。"""
    out = []
    i, n = 0, len(s)
    in_str = esc = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and s[j].isspace():
                j += 1
            if j < n and s[j] in "]}":
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def load_jsonc(path):
    t = read_text(path)
    if t is None:
        return None
    try:
        return json.loads(strip_jsonc(t))
    except ValueError:
        return None


def lines(text):
    return [ln for ln in (text or "").splitlines() if ln.strip()]


def listdir(path, pred=None):
    try:
        names = sorted(os.listdir(os.path.expanduser(path)))
    except OSError:
        return None
    base = os.path.expanduser(path)
    return [n for n in names if (pred is None or pred(os.path.join(base, n)))]


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_paths(override):
    """DEFAULTS に override ファイル (任意) を部分上書きマージ。無ければ DEFAULTS。"""
    p = dict(DEFAULTS)
    src = override or os.path.join(repo_root(), "local", "snapshot-paths.json")
    try:
        with open(os.path.expanduser(src), encoding="utf-8") as f:
            p.update(json.load(f))
    except (OSError, ValueError):
        pass
    return p


def strip_inline_code(value):
    return (value or "").strip().replace("`", "").strip()


def is_placeholder(value):
    value = strip_inline_code(value)
    return not value or (value.startswith("<") and value.endswith(">"))


def claude_host_info(text):
    """Unified CLAUDE.md / legacy CLAUDE.local.md から端末設定を軽く抽出する。

    raw 本文は snapshot に入れず、config-manager が比較しやすい host-info だけを保持する。
    """
    info = {}
    if not text:
        return info
    for key in ("vault_path", "library_path", "ai_note_folder", "public_note_folders", "private_note_folders"):
        m = re.search(rf"-\s*`{re.escape(key)}`\s*:\s*(.+)", text)
        if m:
            value = strip_inline_code(m.group(1).split("  ")[0].strip())
            if not is_placeholder(value):
                info[key] = value
    m = re.search(r"ホスト名[:：]\s*(\S+)", text)
    if m:
        value = strip_inline_code(m.group(1))
        if not is_placeholder(value):
            info["hostname"] = value
    return info


def machine_label(P):
    for key in ("claude_md", "claude_legacy_local_md"):
        info = claude_host_info(read_text(P[key]))
        if info.get("hostname"):
            return info["hostname"]
    return socket.gethostname().split(".")[0]


def editor(cli, ext_manifest, user_dir, argv):
    ext = run([cli, "--list-extensions", "--show-versions"])
    settings_path = os.path.join(os.path.expanduser(user_dir), "settings.json")
    argv_json = load_jsonc(argv) or {}
    return {
        f"{cli}.extensions": {"mtime": mtime(ext_manifest),
                              "value": lines(ext) if ext is not None else None},
        f"{cli}.settings": {"mtime": mtime(settings_path),
                            "value": load_jsonc(settings_path)},
        f"{cli}.locale": {"mtime": mtime(argv), "value": argv_json.get("locale")},
    }


def main(P):
    def px(key):
        return os.path.expanduser(P[key])

    snap = {"machine": machine_label(P), "os": "win", "captured_at": now()}

    # --- editors ---
    snap.update(editor("code", P["code_ext_manifest"], P["code_user"], P["code_argv"]))
    snap.update(editor("cursor", P["cursor_ext_manifest"], P["cursor_user"], P["cursor_argv"]))

    # --- python family ---
    pyver = run(["python", "--version"])
    snap["python3"] = {"mtime": None,
                       "value": {"version": pyver.split()[-1] if pyver else None, "path": which("python")}}
    snap["pyenv"] = {"mtime": None,
                     "value": {"global": run(["pyenv", "global"]),
                               "versions": lines(run(["pyenv", "versions", "--bare"]))}}
    snap["venvs"] = {"mtime": mtime(P["venvs"]), "value": listdir(P["venvs"], os.path.isdir)}
    snap["conda"] = {"mtime": None,
                     "value": {"which": which("conda"),
                               "dirs": [d for d in ("miniforge3", "anaconda3", "miniconda3", ".conda")
                                        if os.path.isdir(os.path.join(HOME, d))]}}
    snap["uv"] = {"mtime": None, "value": run(["uv", "--version"])}

    # --- node ---
    snap["node"] = {"mtime": None, "value": {"node": run(["node", "--version"]),
                                             "npm": run(["npm", "--version"])}}

    # --- R ---
    snap["R"] = {"mtime": None, "value": {"which": which("R"),
                                          "version": first_line(run(["R", "--version"]))}}

    # --- jupyter (kernel はディレクトリ実体。win は %APPDATA%\jupyter\kernels) ---
    snap["jupyter"] = {"mtime": mtime(P["jupyter_kernels"]),
                       "value": {"kernels": listdir(P["jupyter_kernels"], os.path.isdir)}}

    # --- git (global 全設定) ---
    cfg = {}
    for ln in lines(run(["git", "config", "--global", "--list"])):
        k, _, v = ln.partition("=")
        cfg[k] = v
    snap["git"] = {"mtime": mtime(P["gitconfig"]), "value": cfg}

    # --- shell (powershell + gitbash) ---
    profile = run(["powershell", "-NoProfile", "-Command", "$PROFILE"])
    psver = run(["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"])
    snap["powershell"] = {"mtime": mtime(profile) if profile else None,
                          "value": {"version": psver, "profile": profile,
                                    "venv_defs": venv_defs(read_text(profile)) if profile else []}}
    snap["gitbash"] = {"mtime": mtime(P["bashrc"]), "value": {"venv_defs": venv_defs(read_text(P["bashrc"]))}}

    # --- texlive ---
    tl = {b: which(b) for b in ("latexmk", "uplatex", "platex", "dvipdfmx", "tlmgr")}
    tl["latexmkrc"] = os.path.isfile(px("latexmkrc"))
    snap["texlive"] = {"mtime": None, "value": tl}

    # --- ollama ---
    snap["ollama"] = {"mtime": None,
                      "value": {"version": run(["ollama", "--version"]),
                                "models": lines(run(["ollama", "list"]))}}

    # --- markdown preview (MPE 配色本体。win は ~/.crossnote) ---
    snap["crossnote"] = {"mtime": mtime(P["crossnote_style"]),
                         "value": {"style.less": os.path.isfile(px("crossnote_style"))}}

    # --- claude / codex / copilot 配布物 ---
    cmds = listdir(P["claude_commands"], lambda p: p.endswith(".md"))
    claude_md = read_text(P["claude_md"])
    legacy_local = read_text(P["claude_legacy_local_md"])
    snap["claude"] = {"mtime": mtime(P["claude_commands"]),
                      "value": {"version": run(["claude", "--version"]),
                                "commands": [c[:-3] for c in cmds] if cmds is not None else None}}
    snap["claude.md"] = {"mtime": mtime(P["claude_md"]),
                         "value": {"present": claude_md is not None,
                                   "host_info": claude_host_info(claude_md),
                                   "has_library_island": bool(
                                       claude_md
                                       and "claude-library:begin" in claude_md
                                       and "claude-library:end" in claude_md
                                   )}}
    snap["claude.legacy_local"] = {"mtime": mtime(P["claude_legacy_local_md"]),
                                   "value": {"present": legacy_local is not None,
                                             "host_info": claude_host_info(legacy_local)}}
    snap["codex"] = {"mtime": mtime(P["codex_skills"]),
                     "value": {"skills": listdir(P["codex_skills"], os.path.isdir)}}
    snap["qwen"] = {"mtime": mtime(P["qwen_settings"]),
                    "value": {"version": run(["qwen", "--version"]),
                              "settings": load_jsonc(P["qwen_settings"]),
                              "skills": listdir(P["qwen_skills"], os.path.isdir)}}
    pl = listdir(P["copilot_prompts"], lambda p: p.endswith(".prompt.md"))
    snap["copilot"] = {"mtime": mtime(P["copilot_prompts"]),
                       "value": {"prompts": [p[:-len(".prompt.md")] for p in pl] if pl is not None else None}}

    return snap


def snapshot_filename(snap):
    timestamp = snap["captured_at"].replace("T", "_").replace(":", "-")
    return f"config_snapshot_{snap['machine']}_{timestamp}.json"


def scratch_path(snap):
    return os.path.join(repo_root(), "scratch", snapshot_filename(snap))


def log_path(snap):
    return os.path.join(repo_root(), "log", "config", snapshot_filename(snap))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="config snapshot (win)")
    out = ap.add_mutually_exclusive_group()
    out.add_argument("--scratch", action="store_true",
                     help="stdout でなく <repo>\\scratch\\config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json に書く")
    out.add_argument("--log", action="store_true",
                     help="stdout でなく <repo>\\log\\config\\config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json に書く")
    ap.add_argument("--paths", help="path 上書き JSON (既定: <repo>\\local\\snapshot-paths.json)")
    args = ap.parse_args()

    require_platform()

    snap = main(resolve_paths(args.paths))
    text = json.dumps(snap, indent=2, ensure_ascii=False)
    if args.scratch or args.log:
        path = scratch_path(snap) if args.scratch else log_path(snap)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(path)
    else:
        print(text)
