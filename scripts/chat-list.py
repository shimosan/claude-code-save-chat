#!/usr/bin/env python3
"""chat-list core — claude-code と codex の会話履歴を横断で列挙・閲覧する決定的ツール.

LLM 推論ゼロ・読み取り専用。slash 皮 (dotclaude/commands/chat-list.md) から呼ばれる。
皮は「自然言語 → 確定セレクタ (cwd / 会話 id) の解決」と「dump 前の確認」を担い、
本 script は確定値だけを受けて機械的に動く。

データ源 (2026-06-18〜19 実測):
- claude: ~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl
    開始 = 最初の timestamp / id = ファイル名 stem / 由来 = entrypoint /
    名前 = 最後の customTitle → 無ければ aiTitle / cwd = 各行の cwd フィールド
- codex : ~/.codex/sqlite/state_5.sqlite の threads テーブル (cwd/title/created_at/rollout_path)
    本体 = rollout_path の jsonl。subagent (source に subagent) / archived は既定で除外。
- cursor: <Cursor>/User/globalStorage/state.vscdb の cursorDiskKV (composerData:<id> ヘッダ +
    bubbleId:<id>:<bid> 本文)。live なので /tmp コピーしてから開く。cwd=workspaceIdentifier.uri.fsPath。
    本文をレコードに _msgs として持つ (virtual path ゆえ後から再読込できない)。多端末 cwd 混在に注意。
- copilot: 同じ GitHub Copilot の 2 surface を CP に統合 (由来で区別)。
    - CP/panel|editor… = VS Code 拡張: <Code>/User/workspaceStorage/<hash>/chatSessions/<id>.{json,jsonl}
      (v3。.jsonl は kind:0 base + kind:1/2 パッチの追記ログ → 復元)。cwd=workspace.json の folder URI。
    - CP/cli = Copilot CLI/coding agent: ~/.copilot/session-store.db の sessions で列挙、本文は
      ~/.copilot/session-state/<id>/events.jsonl (user.message/assistant.message の data.content)。
      cwd は使い捨て worktree ゆえ repository があれば 'gh:<owner/repo>' を WS にする。
  ※ エディタ系パスは _editor_user_dir() で OS 分岐 (mac/Win/Linux)。

mtime は Dropbox 同期で揃い当てにならないので使わない (開始時刻は中身の timestamp)。
"""
import argparse
import base64
import contextlib
import datetime
import glob
import io
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
import urllib.parse

HOME = os.path.expanduser("~")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_DB = os.path.join(HOME, ".codex", "sqlite", "state_5.sqlite")


def _editor_user_dir(app):
    """VS Code (=Copilot) / Cursor の User 設定ディレクトリ (OS 別)。schema は OS 共通。"""
    if sys.platform == "darwin":
        return os.path.join(HOME, "Library", "Application Support", app, "User")
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming")), app, "User")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), app, "User")


# copilot = VS Code (Code)、cursor = Cursor。chat 履歴の格納先。
CODE_WS = os.path.join(_editor_user_dir("Code"), "workspaceStorage")
CODE_EMPTYWIN = os.path.join(_editor_user_dir("Code"), "globalStorage", "emptyWindowChatSessions")
CURSOR_DB = os.path.join(_editor_user_dir("Cursor"), "globalStorage", "state.vscdb")
CODE_DB = os.path.join(_editor_user_dir("Code"), "globalStorage", "state.vscdb")
# Copilot CLI / coding agent (VS Code 拡張とは別 surface、同じ GitHub Copilot)。OS 共通 ~/.copilot。
COPILOT_CLI_DB = os.path.join(HOME, ".copilot", "session-store.db")
COPILOT_CLI_STATE = os.path.join(HOME, ".copilot", "session-state")
COPILOT_CLI_DATA_DB = os.path.join(HOME, ".copilot", "data.db")  # desktop app: workspaces.archived_at

UTC = datetime.timezone.utc


# オフセット(分) -> 短い略称。Windows の %Z は冗長 ('東京 (標準時)') なので、
# 略称が取れない時のフォールバック表示に使う。未知のオフセットは 'UTC±N' にする。
_TZ_ABBR = {9 * 60: "JST", 0: "UTC", -5 * 60: "EST", -8 * 60: "PST"}


def _tzlabel():
    """表示は端末のローカルタイムゾーン (保存値は UTC)。決め打ちはしない。
    %Z は mac/linux では 'JST' 等の短い略称だが Windows では '東京 (標準時)' のように
    冗長・非 ASCII になる。短い ASCII 略称はそのまま使い、それ以外はオフセットから
    略称 (例 +9->JST) を引き、無ければ 'UTC+9' 形式にする。"""
    now = datetime.datetime.now().astimezone()
    z = now.strftime("%Z") or ""
    if z.isascii() and 0 < len(z) <= 5 and " " not in z:
        return z
    off = now.utcoffset() or datetime.timedelta(0)
    mins = int(off.total_seconds() // 60)
    if mins in _TZ_ABBR:
        return _TZ_ABBR[mins]
    sign = "+" if mins >= 0 else "-"
    h, m = divmod(abs(mins), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


TZLABEL = _tzlabel()


# ---------- 時刻 ----------
def to_dt(start):
    """ISO8601(UTC,'Z') か epoch 秒 を aware datetime(UTC) に."""
    if start is None:
        return None
    if isinstance(start, (int, float)):
        return datetime.datetime.fromtimestamp(start, UTC)
    s = start.replace("Z", "")
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in s else "%Y-%m-%dT%H:%M:%S"
    try:
        return datetime.datetime.strptime(s, fmt).replace(tzinfo=UTC)
    except ValueError:
        return None


def loc_str(dt):
    """ローカルタイムゾーンに変換して整形 (端末依存)."""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M") if dt else "?"


def _json_default(o):
    """json.dumps の default。datetime は ISO 文字列に。"""
    return o.isoformat() if isinstance(o, datetime.datetime) else str(o)


# ---------- 表示幅 (全角を 2 と数えて桁を揃える) ----------
def vwidth(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s, w):
    return s + " " * max(0, w - vwidth(s))


def rpad(s, w):
    return " " * max(0, w - vwidth(s)) + s


def clip(s, w):
    """display 幅 w (全角=2) に収め、超えたら末尾を … で切る (列はみ出し防止)。"""
    s = s or ""
    if vwidth(s) <= w:
        return s
    out, cur = "", 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if cur + cw > w - 1:
            break
        out += ch
        cur += cw
    return out + "…"


def human_size(n):
    """バイト数を 536B / 21K / 5.1M 風に。"""
    if n is None or n < 0:
        return "?"
    n = float(n)
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            if unit == "B":
                return f"{int(n)}B"
            return f"{n:.0f}{unit}" if n >= 10 else f"{n:.1f}{unit}"
        n /= 1024


# ---------- cwd マッチ (規則ベース。NL 推測はしない) ----------
def norm(s):
    return unicodedata.normalize("NFC", s) if s else s


def base(s):
    return os.path.basename(norm(s).rstrip("/")) if s else s


def strip_ext_prefix(s):
    r"""Windows の拡張長パスプレフィックス \\?\ を除去する。
    \\?\UNC\host\share -> \\host\share、\\?\C:\x -> C:\x。
    プレフィックスを持たない文字列 (POSIX パス全般) はそのまま返す = no-op。"""
    if not s:
        return s
    if s.startswith("\\\\?\\UNC\\"):
        return "\\\\" + s[len("\\\\?\\UNC\\"):]
    if s.startswith("\\\\?\\"):
        return s[len("\\\\?\\"):]
    return s


def lower_drive(s):
    r"""Windows のドライブ文字 (先頭 'X:') を小文字に統一する。表示揺れ防止
    (claude は 'e:\…'、別セッションは 'E:\…' のように大小がまちまち)。
    'X:' で始まらない文字列 (POSIX パス全般) はそのまま返す = no-op。"""
    if s and len(s) >= 2 and s[1] == ":" and s[0].isascii() and s[0].isalpha():
        return s[0].lower() + s[1:]
    return s


def ws_path(cwd):
    """表示用の実パス: NFC 正規化 + 拡張長プレフィックス除去 + ドライブ文字小文字化。
    POSIX では strip も lower_drive も恒等なので norm(cwd) と同一。"""
    return lower_drive(strip_ext_prefix(norm(cwd))) if cwd else cwd


def ws_key(cwd):
    r"""WS グルーピング/重複判定キー。Windows ではプレフィックス除去 + case 畳み込み
    (os.path.normcase) で codex(\\?\E:\…) と claude(e:\…) を同一視する。
    POSIX では normcase も strip も恒等なので norm(cwd) に等しい (現挙動を変えない)."""
    return norm(os.path.normcase(strip_ext_prefix(cwd))) if cwd else "(不明)"


# 表示の '~' 置換用 (ws_path と同じ正規化を施した HOME)。HOME 自体は実パス生成に使うので変えない。
_HOME_DISP = ws_path(HOME)


def make_cwd_pred(target, exact=False):
    """cwd マッチ述語。既定は部分一致 (NFC 正規化)、exact=True で完全一致。"""
    t = norm(target)
    if exact:
        return lambda c: norm(c) == t
    return lambda c: t in norm(c)


def make_multi_pred(targets, exact=False):
    """複数の --path 値 (反復 / カンマ区切り) の OR。exact で各値を完全一致に。"""
    preds = [make_cwd_pred(tv, exact) for tv in targets]
    return lambda c: any(p(c) for p in preds)


def ws_letter(i):
    """0->A, 25->Z, 26->AA … (WS 凡例ラベル)."""
    s = ""
    i += 1
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------- claude ----------
_CLAUDE_KEYS = ('"timestamp"', '"customTitle"', '"aiTitle"', '"entrypoint"', '"cwd"', '"model"')
# 大きい jsonl は全読みせず head+tail だけ読む (start は先頭・end/title/model は末尾優先)。
# 587MB 級の 1 ファイルが census 全体の主コスト。閾値以下は全読み (端から端まで安全)。
_SCAN_HEAD = 256 * 1024
_SCAN_TAIL = 256 * 1024


def _scan_claude_meta(path):
    """1 jsonl から (start, end, customTitle, aiTitle, entrypoint, cwd, model) を抽出。
    start=最初の timestamp / end=最後の timestamp / model=最後の message.model (<synthetic> 除く)。
    巨大ファイルは head+tail のみ読む高速版 (中央のみに在る title/model は稀に取りこぼす)。"""
    acc = {"start": None, "end": None, "ct": None, "at": None, "ep": None, "cwd": None, "model": None}

    def feed(line):
        if not any(k in line for k in _CLAUDE_KEYS):
            return
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            return
        if o.get("timestamp"):
            if acc["start"] is None:
                acc["start"] = o["timestamp"]
            acc["end"] = o["timestamp"]
        if o.get("customTitle"):
            acc["ct"] = o["customTitle"]
        if o.get("aiTitle"):
            acc["at"] = o["aiTitle"]
        if acc["ep"] is None and o.get("entrypoint"):
            acc["ep"] = o["entrypoint"]
        if acc["cwd"] is None and o.get("cwd"):
            acc["cwd"] = o["cwd"]
        m = o.get("message")
        if isinstance(m, dict) and m.get("model") and m["model"] != "<synthetic>":
            acc["model"] = m["model"]

    try:
        size = os.path.getsize(path)
        # seek 後の mid-char クラッシュを避けるため errors='replace'
        with open(path, encoding="utf-8", errors="replace") as f:
            if size <= _SCAN_HEAD + _SCAN_TAIL:
                for line in f:
                    feed(line)
            else:
                read = 0
                for line in f:  # head
                    feed(line)
                    read += len(line)
                    if read >= _SCAN_HEAD:
                        break
                f.seek(max(0, size - _SCAN_TAIL))
                f.readline()  # seek 直後の部分行は捨てる
                for line in f:  # tail
                    feed(line)
    except OSError:
        return None
    return (acc["start"], acc["end"], acc["ct"], acc["at"], acc["ep"], acc["cwd"], acc["model"])


def _dir_cwd(d):
    """encoded dir の代表 cwd (最初に見つかった cwd フィールド)."""
    for fn in os.listdir(d):
        if not fn.endswith(".jsonl"):
            continue
        for line in open(os.path.join(d, fn), encoding="utf-8"):
            if '"cwd"' in line:
                try:
                    c = json.loads(line).get("cwd")
                except json.JSONDecodeError:
                    c = None
                if c:
                    return c
    return None


def _vscdb_hidden(db_path):
    """エディタの state.vscdb から Claude Code 拡張の hiddenSessionIds (ゴミ箱/非表示) を集合で返す。
    ItemTable の key='Anthropic.claude-code' の JSON 値内。read-only・単一キー索引引きで軽い。"""
    con = _ro_connect(db_path)
    if con is None:
        return set()
    try:
        row = con.execute("select value from ItemTable where key='Anthropic.claude-code'").fetchone()
    except sqlite3.Error:
        row = None
    finally:
        con.close()
    if not row or not row[0]:
        return set()
    try:
        return set(json.loads(row[0]).get("hiddenSessionIds") or [])
    except (json.JSONDecodeError, TypeError):
        return set()


_HIDDEN_CACHE = None


def _claude_hidden():
    """(Cursor で hidden の id 集合, VS Code で hidden の id 集合)。プロセス内 1 回だけ読む。
    hidden は per-editor (Cursor と VS Code で独立)。本体 jsonl は消えないので chat-list は印付けに使う。"""
    global _HIDDEN_CACHE
    if _HIDDEN_CACHE is None:
        _HIDDEN_CACHE = (_vscdb_hidden(CURSOR_DB), _vscdb_hidden(CODE_DB))
    return _HIDDEN_CACHE


def iter_claude_sessions(pred=None):
    """pred(cwd)->bool で絞る。pred=None なら全件。
    encoded dir 直下の `*.jsonl` だけが top-level セッション。subagent の sidechain は
    `<dir>/<sessionId>/subagents/agent-*.jsonl` と入れ子なので os.listdir(1 階層) では拾わない."""
    if not os.path.isdir(CLAUDE_PROJECTS):
        return
    cur_h, vs_h = _claude_hidden()
    for dn in os.listdir(CLAUDE_PROJECTS):
        d = os.path.join(CLAUDE_PROJECTS, dn)
        if not os.path.isdir(d):
            continue
        # dir 代表 cwd で候補を間引く (同 dir 内は基本同 cwd)
        if pred is not None:
            dc = _dir_cwd(d)
            if dc is None or not pred(dc):
                continue
        for fn in os.listdir(d):
            if not fn.endswith(".jsonl"):
                continue
            meta = _scan_claude_meta(os.path.join(d, fn))
            if meta is None:
                continue
            start, end, ct, at, ep, cwd, model = meta
            if pred is not None and (cwd is None or not pred(cwd)):
                continue
            fp = os.path.join(d, fn)
            sid = fn[:-6]
            hc, hv = sid in cur_h, sid in vs_h  # Cursor/VS Code で hidden か (per-editor)
            mark = ("*" + ("c" if hc else "") + ("v" if hv else "")) if (hc or hv) else ""
            yield {
                "id": sid,
                "harness": "claude",
                "origin": (ep or "?").replace("claude-", ""),
                "model": model,
                "start": to_dt(start),
                "updated": to_dt(end),
                "title": ct or at or "",
                "cwd": cwd,
                "path": fp,
                "bytes": _filesize(fp),
                "archived": hc or hv,   # short の * 用 (OR)
                "_archmark": mark,      # long の *c/*v/*cv 用
            }


# ---------- read-only sqlite open (WAL 堅牢化) ----------
def _ro_connect(db_path, timeout=5):
    """sqlite を read-only で開く共通入口。まず `mode=ro`、失敗したら `immutable=1` にフォールバック。
    理由: WAL モードの db を、所有アプリ終了後 (-wal/-shm 不在) に `mode=ro` で開くと
    'unable to open database file' になる。その時は WAL が本体へチェックポイント済み=本体が完全なので
    `immutable=1` (WAL を介さず本体直読み) で正しく読める。アプリ起動中は `mode=ro` が成功し WAL の
    最新を読むので、immutable は使われない (起動中に immutable を使うと未反映の本体を読む罠を避ける)。
    pathlib.as_uri() で OS 非依存の file:// URI (Windows のバックスラッシュ/ドライブ対策)。"""
    if not os.path.exists(db_path):
        return None
    uri = pathlib.Path(db_path).as_uri()
    for q in ("?mode=ro", "?immutable=1"):
        con = None
        try:
            con = sqlite3.connect(uri + q, uri=True, timeout=timeout)
            con.execute("select count(*) from sqlite_master")  # 実読み検査: mode=ro は WAL db で
            return con                                          # connect は通っても execute で 'unable to open' になる
        except sqlite3.OperationalError:
            if con is not None:
                try:
                    con.close()
                except sqlite3.Error:
                    pass
            continue
    return None


# ---------- codex ----------
def _codex_conn():
    return _ro_connect(CODEX_DB)


def iter_codex_sessions(pred=None, include_subagents=False, include_archived=False):
    con = _codex_conn()
    if con is None:
        return
    with con:
        rows = con.execute(
            "SELECT id, rollout_path, cwd, title, created_at, updated_at, source, archived FROM threads"
        ).fetchall()
    for cid, rp, cwd, title, created, updated, source, archived in rows:
        if not include_subagents and source and "subagent" in source:
            continue
        if not include_archived and archived:
            continue
        if pred is not None and (cwd is None or not pred(cwd)):
            continue
        yield {
            "id": cid,
            "harness": "codex",
            "origin": source if (source and "subagent" not in source) else "subagent",
            "start": to_dt(created),
            "updated": to_dt(updated),
            "title": title or "",
            "cwd": cwd,
            "path": rp,
            "bytes": _filesize(rp),
            "archived": bool(archived),
            "_archmark": "*" if archived else "",  # codex は editor 区別なし → 素の *
        }


# ---------- copilot / cursor 共通: epoch ミリ秒・ISO の時刻 ----------
def _ms_to_dt(ms):
    """epoch ミリ秒 -> aware datetime(UTC)。codex/claude の to_dt は秒なので別に持つ。"""
    if ms is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(ms / 1000.0, UTC)
    except (TypeError, ValueError, OSError):
        return None


def _iso_to_dt(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------- copilot (VS Code chat schema v3, workspaceStorage の json) ----------
def _code_ws_cwd(ws_hash_dir):
    """workspaceStorage/<hash> -> 実フォルダ。'folder'(単一)or 'workspace'(multi-root,.code-workspace)。"""
    try:
        d = json.load(open(os.path.join(ws_hash_dir, "workspace.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    uri = d.get("folder") or d.get("workspace")
    if not uri:
        return None
    if uri.startswith("file://"):
        return _strip_ws_file(urllib.parse.unquote(urllib.parse.urlparse(uri).path))
    if uri.startswith("vscode-remote://"):
        # 例 vscode-remote://ssh-remote%2Buchiha/home/.../x.code-workspace -> '[uchiha] /home/.../x'
        pp = urllib.parse.urlparse(uri)
        host = urllib.parse.unquote(pp.netloc)
        host = host[len("ssh-remote+"):] if host.startswith("ssh-remote+") else host
        return f"[{host}] {_strip_ws_file(urllib.parse.unquote(pp.path))}"
    return uri  # その他のスキームはそのまま


def _strip_ws_file(p):
    """multi-root の <proj>/.vscode/<name>.code-workspace を実プロジェクト dir に正規化。"""
    if p.endswith(".code-workspace"):
        parent = os.path.dirname(p)
        return os.path.dirname(parent) if os.path.basename(parent) == ".vscode" else parent
    return p


def _copilot_msgs(d):
    """VS Code chat json の requests[] -> [(role,text)]。"""
    out = []
    for req in (d.get("requests") or []):
        ts = _ms_to_dt(req.get("timestamp"))  # request 単位の epoch ms (user/assistant で共有)
        u = ((req.get("message") or {}).get("text") or "").strip()
        if u:
            out.append(("user", ts, u))
        parts = [p["value"] for p in (req.get("response") or [])
                 if isinstance(p, dict) and isinstance(p.get("value"), str)
                 and p.get("kind") in (None, "markdownContent")]
        a = "\n".join(parts).strip()
        if a:
            out.append(("assistant", ts, a))
    return out


def _copilot_load(path):
    """copilot chat session を v3 構造の dict にして返す。2 形式に対応:
    - 旧 .json : v3 単一オブジェクト (requests[], creationDate, customTitle, initialLocation…)
    - 新 .jsonl: kind:0 の base + kind:1/2 の JSON パッチ (k=パス, v=値) の追記ログ → 適用して復元。
    どちらも同じ v3 dict になるので以降の抽出は共通。"""
    try:
        if not path.endswith(".jsonl"):
            return json.load(open(path, encoding="utf-8"))
        base = {}
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("kind") == 0:
                base = o.get("v") or {}
                continue
            k = o.get("k")
            if not k:
                continue
            cur, ok = base, True
            for key in k[:-1]:  # 末尾手前までナビゲート
                if isinstance(key, int):
                    if isinstance(cur, list) and 0 <= key < len(cur):
                        cur = cur[key]
                    else:
                        ok = False
                        break
                elif isinstance(cur, dict):
                    cur = cur.setdefault(key, {})
                else:
                    ok = False
                    break
            if ok:
                try:
                    cur[k[-1]] = o.get("v")  # 末尾キー/インデックスに値を set
                except (TypeError, IndexError, KeyError):
                    pass
        return base
    except (OSError, json.JSONDecodeError):
        return None


def copilot_messages(path):
    d = _copilot_load(path)
    return _copilot_msgs(d) if d else []


def _copilot_archived_ids(ws_hash_dir):
    """その WS の state.vscdb の agentSessions.state.cache から archived の sessionId 集合。
    entry: {resource:'vscode-chat-session://local/<base64(sessionId)>', archived:true}。base64 デコードで id 化。"""
    con = _ro_connect(os.path.join(ws_hash_dir, "state.vscdb"))
    if con is None:
        return set()
    try:
        row = con.execute("select value from ItemTable where key='agentSessions.state.cache'").fetchone()
    except sqlite3.Error:
        return set()
    finally:
        con.close()
    if not row or not row[0]:
        return set()
    out = set()
    try:
        for e in json.loads(row[0]):
            if not (isinstance(e, dict) and e.get("archived")):
                continue
            b = (e.get("resource") or "").split("/local/")[-1]
            if b:
                try:
                    out.add(base64.b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "replace"))
                except (ValueError, UnicodeDecodeError):
                    pass
    except (json.JSONDecodeError, TypeError):
        pass
    return out


def iter_copilot_sessions(pred=None):
    roots = []  # (chatSessions の親, cwd, wsd)
    if os.path.isdir(CODE_WS):
        for h in os.listdir(CODE_WS):
            wsd = os.path.join(CODE_WS, h)
            roots.append((os.path.join(wsd, "chatSessions"), _code_ws_cwd(wsd), wsd))
    roots.append((CODE_EMPTYWIN, None, None))  # workspace なしの会話 (空なら自然に skip)
    for cs_dir, cwd, wsd in roots:
        if pred is not None and (cwd is None or not pred(cwd)):
            continue
        archived_ids = _copilot_archived_ids(wsd) if wsd else set()
        # 旧 .json と 新 .jsonl の両方
        for path in glob.glob(os.path.join(cs_dir, "*.json")) + glob.glob(os.path.join(cs_dir, "*.jsonl")):
            d = _copilot_load(path)
            if not d:
                continue
            reqs = d.get("requests") or []
            if not reqs:
                continue  # 空セッション
            ts = [r.get("timestamp") for r in reqs if r.get("timestamp")]
            title = d.get("customTitle") or ""
            if not title:
                for r in reqs:
                    t = ((r.get("message") or {}).get("text") or "").strip()
                    if t:
                        title = t.splitlines()[0][:80]
                        break
            model = next((r.get("modelId") for r in reqs if r.get("modelId")), None)
            stem = os.path.basename(path).rsplit(".", 1)[0]
            sid = d.get("sessionId") or stem
            yield {
                "id": sid,
                "harness": "copilot",
                "origin": d.get("initialLocation") or "",  # 由来=panel/editor/terminal 等
                "model": model,  # modelId (例 copilot/gpt-5-mini) → --long でモデル列
                "start": _ms_to_dt(min(ts) if ts else d.get("creationDate")),
                "updated": _ms_to_dt(max(ts) if ts else d.get("lastMessageDate")),
                "title": title,
                "cwd": cwd,
                "path": path,
                "bytes": _filesize(path),
                "archived": sid in archived_ids,  # agentSessions.state.cache[].archived
                "_archmark": "*" if sid in archived_ids else "",  # editor 区別なし → 素の *
            }


# ---------- copilot CLI / coding agent (~/.copilot) ----------
def _copilot_cli_events(sid):
    return os.path.join(COPILOT_CLI_STATE, sid, "events.jsonl")


def copilot_cli_messages(path):
    """events.jsonl の user.message / assistant.message の data.content -> [(role,text)]。"""
    out = []
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = o.get("type")
            if t in ("user.message", "assistant.message"):
                c = (o.get("data") or {}).get("content")
                if c and c.strip():
                    out.append(("user" if t == "user.message" else "assistant",
                                _iso_to_dt(o.get("timestamp")), c.strip()))
    except OSError:
        pass
    return out


def _copilot_cli_model(path):
    """events.jsonl head から assistant.message.data.model を拾う (--long の遅延取得)。"""
    try:
        for i, line in enumerate(open(path, encoding="utf-8", errors="replace")):
            if i > 80:
                break
            if '"model"' not in line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "assistant.message":
                m = (o.get("data") or {}).get("model")
                if m:
                    return m
    except OSError:
        return None
    return None


def _git_origin_owner_repo(cfg_path):
    """`.git/config` の origin url から 'owner/repo' を取る (github の git@/https 両対応)。"""
    try:
        txt = open(cfg_path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    in_origin, url = False, None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_origin = s.replace(" ", "").lower() == '[remote"origin"]'
        elif in_origin and s.startswith("url") and "=" in s:
            url = s.split("=", 1)[1].strip()
            break
    if not url:
        return None
    for sep in ("github.com:", "github.com/"):
        if sep in url:
            tail = url.split(sep, 1)[1]
            tail = tail[:-4] if tail.endswith(".git") else tail
            parts = tail.rstrip("/").split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
    return None


_REPO_MAP_CACHE = None


def _repo_remote_map():
    """{<owner/repo>: <ローカル repo パス>}。Copilot CLI の gh:repo を同 remote のローカルクローンへ
    対応づけ WS を統合するため。ローカル cwd (codex threads / editor / claude) を集め .git/config を読む。1 回キャッシュ。"""
    global _REPO_MAP_CACHE
    if _REPO_MAP_CACHE is not None:
        return _REPO_MAP_CACHE
    paths = set()
    con = _codex_conn()
    if con is not None:
        try:
            for (c,) in con.execute("select distinct cwd from threads"):
                if c:
                    paths.add(c)
        except sqlite3.Error:
            pass
        con.close()
    if os.path.isdir(CODE_WS):
        for h in os.listdir(CODE_WS):
            c = _code_ws_cwd(os.path.join(CODE_WS, h))
            if c and not c.startswith(("[", "gh:")):
                paths.add(c)
    if os.path.isdir(CLAUDE_PROJECTS):
        for dn in os.listdir(CLAUDE_PROJECTS):
            c = _dir_cwd(os.path.join(CLAUDE_PROJECTS, dn))
            if c:
                paths.add(c)
    m = {}
    for p in paths:
        owner_repo = _git_origin_owner_repo(os.path.join(os.path.expanduser(p), ".git", "config"))
        if owner_repo and owner_repo not in m:
            m[owner_repo] = ws_path(p)
    _REPO_MAP_CACHE = m
    return m


def _copilot_cli_archived_ids():
    """Copilot desktop app の data.db workspaces.archived_at が非 None の session_id 集合。
    archive はこのローカル DB に保存される (before/after 実験で確定)。mode=ro で WAL も見える。"""
    con = _ro_connect(COPILOT_CLI_DATA_DB)
    if con is None:
        return set()
    try:
        rows = con.execute("select session_id, archived_at from workspaces").fetchall()
    except sqlite3.Error:
        return set()
    finally:
        con.close()
    return {sid for sid, arch in rows if sid and arch}


def iter_copilot_cli_sessions(pred=None):
    """Copilot CLI / coding agent。session-store.db の sessions で列挙 (本文は events.jsonl)。
    cwd は使い捨て worktree。repository が同 remote のローカルクローンに対応すればその WS に統合、
    無ければ 'gh:<owner/repo>'、repository 自体無ければ cwd。
    archive は data.db workspaces.archived_at (session_id 紐付け)。"""
    con = _ro_connect(COPILOT_CLI_DB)
    if con is None:
        return
    repo_map = _repo_remote_map()
    archived_ids = _copilot_cli_archived_ids()
    try:
        rows = con.execute(
            "select id, cwd, repository, summary, created_at, updated_at from sessions").fetchall()
    except sqlite3.Error:
        return
    finally:
        con.close()
    for sid, cwd, repo, summary, created, updated in rows:
        if repo and repo in repo_map:
            ws = repo_map[repo]      # 同 remote のローカルクローンへ統合 (gh:repo を local path に)
        elif repo:
            ws = f"gh:{repo}"        # ローカルクローンが無い repo はそのまま gh: 表示
        else:
            ws = cwd                 # repository 不明は cwd (~/.copilot/chats/...)
        if pred is not None and (ws is None or not pred(ws)):
            continue
        ev = _copilot_cli_events(sid)
        yield {
            "id": sid,
            "harness": "copilot",
            "origin": "cli",  # 由来=cli (VS Code 拡張は panel/editor)。同じ CP harness
            "model": None,    # --long で events.jsonl から遅延取得
            "start": _iso_to_dt(created),
            "updated": _iso_to_dt(updated),
            "title": summary or "",
            "cwd": ws,
            "path": ev,
            "bytes": _filesize(ev),
            "archived": sid in archived_ids,  # data.db workspaces.archived_at
            "_archmark": "*" if sid in archived_ids else "",
            "_kind": "cli",     # messages_of / model 取得の分岐用
        }


# ---------- cursor (globalStorage/state.vscdb, cursorDiskKV) ----------
def _cursor_conn():
    """live state.vscdb を read-only で開く (_ro_connect: mode=ro→immutable=1 フォールバック)。
    Cursor 起動中は mode=ro が WAL を尊重、終了後は immutable で本体を読む。コピー不要・lock しない。"""
    return _ro_connect(CURSOR_DB)


def _cursor_cwd(comp):
    ws = comp.get("workspaceIdentifier")
    if isinstance(ws, dict) and isinstance(ws.get("uri"), dict):
        return ws["uri"].get("fsPath") or ws["uri"].get("path")
    return None


def _cursor_subagent_ids(comps):
    """親 composer の subagentComposerIds / subComposerIds に現れる id 集合 (= subagent 会話)。"""
    sub = set()
    for d in comps.values():
        for fld in ("subagentComposerIds", "subComposerIds"):
            for x in (d.get(fld) or []):
                if isinstance(x, str):
                    sub.add(x)
                elif isinstance(x, dict) and x.get("composerId"):
                    sub.add(x["composerId"])
    return sub


def iter_cursor_sessions(pred=None, include_subagents=False):
    con = _cursor_conn()
    if con is None:
        return
    try:
        comps = {}
        for k, v in con.execute("select key,value from cursorDiskKV where key like 'composerData:%'"):
            if v is None:
                continue
            try:
                dd = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                continue
            comps[dd.get("composerId") or k.split(":", 1)[1]] = dd
        subagents = _cursor_subagent_ids(comps)
        archived_ids = set()  # composer.composerHeaders の isArchived=true (= Cursor native の削除/archive)
        try:
            hrow = con.execute("select value from ItemTable where key='composer.composerHeaders'").fetchone()
            if hrow and hrow[0]:
                for c in (json.loads(hrow[0]).get("allComposers") or []):
                    if isinstance(c, dict) and c.get("isArchived") and c.get("composerId"):
                        archived_ids.add(c["composerId"])
        except (sqlite3.Error, json.JSONDecodeError, TypeError):
            pass
        bubbles = {}
        for k, v in con.execute("select key,value from cursorDiskKV where key like 'bubbleId:%'"):
            if v is None:
                continue
            parts = k.split(":")
            if len(parts) < 3:
                continue
            try:
                bubbles.setdefault(parts[1], {})[parts[2]] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                continue
    finally:
        con.close()
    for cid, comp in comps.items():
        is_sub = cid in subagents
        if is_sub and not include_subagents:
            continue  # cursor の subagent 会話は既定で除外 (codex と同方針)
        cwd = _cursor_cwd(comp)
        if pred is not None and (cwd is None or not pred(cwd)):
            continue
        headers = comp.get("fullConversationHeadersOnly") or []
        bd = bubbles.get(cid, {})
        msgs = []
        for h in headers:
            b = bd.get(h.get("bubbleId"))
            if not b:
                continue
            t = (b.get("text") or "").strip()
            if t:
                msgs.append(("user" if b.get("type") == 1 else "assistant",
                             _iso_to_dt(h.get("createdAt")), t))
        if not msgs:
            continue  # tool/diff/thinking のみ = human-visible text 無し
        start = _ms_to_dt(comp.get("createdAt"))
        hdr = [t for t in (_iso_to_dt(h.get("createdAt")) for h in headers) if t]
        if hdr:
            cand = min(hdr)
            if start is None or cand < start:
                start = cand
        mc = comp.get("modelConfig") or {}
        yield {
            "id": cid,
            "harness": "cursor",
            "origin": "subagent" if is_sub else "cursor",  # CU/cursor (surface 情報がデータに無い) / CU/subagent
            "model": (mc.get("modelName") if isinstance(mc, dict) else None),
            "start": start,
            "updated": _ms_to_dt(comp.get("lastUpdatedAt")),
            "title": comp.get("name") or msgs[0][2].splitlines()[0][:80],
            "cwd": cwd,
            "path": f"cursorDiskKV:composerData:{cid}",  # virtual (DB-backed)
            "bytes": sum(len(t) for _, _, t in msgs),  # 本文長で近似 (ファイル無し)
            "archived": cid in archived_ids,  # composer.composerHeaders.isArchived
            "_archmark": "*" if cid in archived_ids else "",  # editor 区別なし → 素の *
            "_msgs": msgs,  # virtual path ゆえ本文をレコードに同梱
            "_nevents": len(headers),  # 全 bubble 数 (tool/thinking 込み = イベント数)
        }


# ---------- 本体テキスト抽出 (head/tail/dump 用) ----------
def claude_messages(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if '"role"' not in line and '"type"' not in line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") not in ("user", "assistant"):
            continue
        m = o.get("message") or {}
        role = m.get("role") or o["type"]
        c = m.get("content")
        if isinstance(c, str):
            t = c
        elif isinstance(c, list):
            t = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        else:
            t = ""
        if t.strip():
            out.append((role, _iso_to_dt(o.get("timestamp")), t.strip()))
    return out


def codex_messages(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if '"message"' not in line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") != "response_item":
            continue
        pl = o.get("payload") or {}
        if pl.get("type") != "message" or pl.get("role") not in ("user", "assistant"):
            continue
        t = "\n".join(b.get("text", "") for b in (pl.get("content") or []) if isinstance(b, dict) and b.get("text"))
        if t.strip():
            out.append((pl["role"], _iso_to_dt(o.get("timestamp")), t.strip()))
    return out


def _codex_model(rollout_path, _maxlines=60):
    """codex rollout jsonl の head から payload.model を拾う (turn_context は先頭付近)。
    --long 表示時のみ遅延で呼ぶ (全行は読まない)。"""
    if not rollout_path or not os.path.exists(rollout_path):
        return None
    try:
        with open(rollout_path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= _maxlines:
                    break
                if '"model"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pl = o.get("payload")
                if isinstance(pl, dict) and isinstance(pl.get("model"), str):
                    return pl["model"]
    except OSError:
        return None
    return None


def messages_of(rec):
    # cursor は virtual path (DB-backed)。本文は列挙時にレコードへ同梱済み。
    if rec.get("_msgs") is not None:
        return rec["_msgs"]
    if not rec["path"] or not os.path.exists(rec["path"]):
        return []
    h = rec["harness"]
    if h == "claude":
        return claude_messages(rec["path"])
    if h == "codex":
        return codex_messages(rec["path"])
    if h == "copilot":
        return copilot_cli_messages(rec["path"]) if rec.get("_kind") == "cli" else copilot_messages(rec["path"])
    return []


def _msg_ts(ts):
    """メッセージ時刻のローカル表記 (HH:MM)。None は空。"""
    return ts.astimezone().strftime("%H:%M") if ts else ""


def text_lines(rec):
    lines = []
    for role, ts, t in messages_of(rec):
        head = f"[{role}{(' ' + _msg_ts(ts)) if ts else ''}] "
        for i, ln in enumerate(t.split("\n")):
            lines.append((head if i == 0 else " " * len(head)) + ln)
    return lines


def grep_matches(rec, term, maxn=4):
    """本文 (会話の中身) から term を含む行を抽出 (大文字小文字無視)。1 会話あたり maxn 行で打ち切り."""
    tl = term.lower()
    out = []
    for role, ts, t in messages_of(rec):
        head = f"[{role}{(' ' + _msg_ts(ts)) if ts else ''}]"
        for ln in t.split("\n"):
            if tl in ln.lower():
                out.append(f"{head} {ln.strip()}")
                if len(out) >= maxn:
                    return out
    return out


# ---------- 収集 + フィルタ ----------
def _filesize(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def _filter_recs(args, recs):
    """--title / --grep を適用 (両モード共通)。--exact なら title は完全一致。grep は本文を読むので遅い。"""
    if args.title:
        g = args.title.lower()
        recs = [r for r in recs if (g == r["title"].lower() if args.exact else g in r["title"].lower())]
    if args.grep:  # 本文の全文検索。一致した会話だけ残し、一致行を添える。
        kept = []
        for r in recs:
            m = grep_matches(r, args.grep)
            if m:
                r["_match"] = m
                kept.append(r)
        recs = kept
    return recs


def _iter_all(args, pred):
    """選択された harness の session を列挙 (--tool で絞る)。両モードの共通入口。"""
    recs = []
    if args.tool in (None, "claude"):
        recs += list(iter_claude_sessions(pred))
    if args.tool in (None, "codex"):
        recs += list(iter_codex_sessions(pred, args.include_subagents, include_archived=True))
    if args.tool in (None, "cursor"):
        recs += list(iter_cursor_sessions(pred, args.include_subagents))
    if args.tool in (None, "copilot"):
        recs += list(iter_copilot_sessions(pred))
        recs += list(iter_copilot_cli_sessions(pred))
    # 重複排除: 同一セッションが複数 dir に物理コピーされている場合 (rename / Dropbox 同期)。
    # (harness, 完全 id) で束ね、最も完全な (大きい) コピーを残す。
    best = {}
    for r in recs:
        key = (r["harness"], r["id"])
        if key not in best or r["bytes"] > best[key][0]:
            best[key] = (r["bytes"], r)
    return [v[1] for v in best.values()]


def collect(args, pred):
    recs = _filter_recs(args, _iter_all(args, pred))
    recs.sort(key=lambda r: (r["start"] is None, r["start"]))
    return recs


_HARNESS_PREFIX = {"claude": "CC/", "codex": "CX/", "cursor": "CU/", "copilot": "CP/"}


def origin_label(rec):
    return _HARNESS_PREFIX.get(rec["harness"], "?/") + rec["origin"]


_MIN_DT = datetime.datetime.min.replace(tzinfo=UTC)


def _sort_recs(recs, how, reverse=False):
    """会話一覧の並べ替え。既定 start=開始時刻、start/end とも新しい順 (最新が上)。--reverse で反転。
    キー: start=開始 / end=最終活動 / size=サイズ / name=タイトル。count は会話一覧には無効 → start."""
    how = how if how in ("end", "size", "title") else "start"
    if how == "end":
        keyf, desc = (lambda r: r["updated"] or r["start"] or _MIN_DT), True
    elif how == "size":
        keyf, desc = (lambda r: r["bytes"]), True
    elif how == "title":
        keyf, desc = (lambda r: r["title"].lower()), False
    else:  # start = 開始 (新しい順が既定)
        keyf, desc = (lambda r: r["start"] or _MIN_DT), True
    recs.sort(key=keyf, reverse=desc ^ reverse)
    return recs


def _sort_label(how, reverse):
    """English sort label, e.g. 'start (newest first)'. start/end/size/total default descending,
    title/path ascending; --reverse flips. Keys match the column headers."""
    if how == "size":
        return f"size ({'smallest' if reverse else 'largest'} first)"
    if how == "total":
        return f"total ({'fewest' if reverse else 'most'} first)"
    if how in ("title", "path"):
        return f"{how} ({'Z-A' if reverse else 'A-Z'})"
    how = "end" if how == "end" else "start"
    return f"{how} ({'oldest' if reverse else 'newest'} first)"


# ---------- 出力: 一覧 ----------
def _ws_key(r):
    return ws_key(r["cwd"])


def cmd_list(args, pred):
    recs = _sort_recs(collect(args, pred), args.sort, args.reverse)
    if args.head:
        recs = recs[:args.head]   # 先頭 N 件 (Unix head)
    if args.tail:
        recs = recs[-args.tail:]  # 末尾 N 件 (Unix tail)
    # 対象 WS に出現順で A/B/C… を振る
    order = []
    letters = {}
    counts = {}
    for r in recs:
        k = _ws_key(r)
        counts[k] = counts.get(k, 0) + 1
        if k not in letters:
            letters[k] = ws_letter(len(order))
            order.append((k, r["cwd"]))
    if args.json:
        # start / updated は datetime。default で ISO 文字列化する (片方漏れると TypeError)。
        print(json.dumps([{**r, "ws": letters[_ws_key(r)]} for r in recs],
                         ensure_ascii=False, indent=1, default=_json_default))
        return
    n = {h: sum(1 for r in recs if r["harness"] == h) for h in ("claude", "codex", "cursor", "copilot")}
    print("# chat-list  workspaces:")
    if order:
        for k, cwd in order:
            print(f"#   {letters[k]}  {(ws_path(cwd) or '(unknown)').replace(_HOME_DISP, '~')}  ({counts[k]})")
    else:
        print("#   (none)")
    na = sum(1 for r in recs if r["archived"])
    print(f"# {len(recs)} conversations (claude {n['claude']} + codex {n['codex']} + cursor {n['cursor']} "
          f"+ copilot {n['copilot']})  ·  sort: {_sort_label(args.sort, args.reverse)}")
    if na:
        if args.long:
            print(f"# '*' after origin = archived/hidden ({na}); claude *c=Cursor *v=VS Code *cv=both, others *")
        else:
            print(f"# '*' after origin = archived/hidden ({na}; --long splits claude into Cursor/VS Code)")
    print()
    # 由来列の表示文字列 (WSラベル + 由来 + archive 記号) を先に作り、列幅は実データの最大に合わせる。
    # short: 素の '*' / long: '*c/*v/*cv' (claude) ・ '*' (codex)。記号は除外ではなく印のみ。
    odisp = []
    for r in recs:
        o = f"{letters[_ws_key(r)]} {origin_label(r)}"
        o += (r.get("_archmark", "") if args.long else ("*" if r["archived"] else ""))
        odisp.append(o)
    ow = max([vwidth("origin")] + [vwidth(o) for o in odisp])
    # モデル列は --long の時だけ。幅は実際に出すモデル名の最大に合わせる (固定広幅にしない)。
    models, mw = None, 0
    if args.long:
        models = []
        for r in recs:
            m = r.get("model")
            if not m and r["harness"] == "codex":  # codex は rollout head から遅延取得
                m = _codex_model(r["path"])
            if not m and r.get("_kind") == "cli":  # copilot CLI は events.jsonl から遅延取得
                m = _copilot_cli_model(r["path"])
            models.append(m or "-")
        mw = min(34, max([vwidth("model")] + [vwidth(m) for m in models]))
    mhead = pad("model", mw + 1) if args.long else ""
    print(pad("#", 4) + pad("start", 17) + pad("origin", ow + 1) + mhead
          + pad("id", 10) + rpad("size", 6) + "  " + "title")
    for i, r in enumerate(recs, 1):
        mcol = pad(clip(models[i - 1], mw), mw + 1) if args.long else ""
        print(pad(str(i), 4) + pad(loc_str(r["start"]), 17) + pad(odisp[i - 1], ow + 1)
              + mcol + pad(r["id"][:8], 10)
              + rpad(human_size(r["bytes"]), 6) + "  " + r["title"][:50])
        if r.get("_match"):  # --grep の一致行を優先表示
            for ln in r["_match"]:
                print(f"      ┊ {ln[:96]}")
        elif args.preview is not None:  # 本文プレビュー: N=先頭 N 行 / 負値=末尾 N 行
            lines = text_lines(r)
            sel = lines[:args.preview] if args.preview >= 0 else lines[args.preview:]
            for ln in sel:
                print(f"      ┊ {ln[:96]}")


# ---------- 出力: WS 一覧 ----------
def cmd_workspaces(args, pred=None):
    # census は一覧と同じ列挙 (--tool 選択 + (harness,id) dedup + --title/--grep フィルタ) で作る → 表示と整合。
    # archived/hidden も現役として計に算入。別途その本数を arch 列 (-N) で示す。subagent は既定除外。
    cntkey = {"claude": "cc", "codex": "cx", "cursor": "cu", "copilot": "cp"}
    agg = {}  # ws_key(cwd) -> dict(cc, cx, cu, cp, arch, bytes, first, last, disp)
    for r in _filter_recs(args, _iter_all(args, None)):
        if not r["cwd"]:
            continue
        if pred is not None and not pred(r["cwd"]):
            continue
        k = ws_key(r["cwd"])
        a = agg.setdefault(k, {"cc": 0, "cx": 0, "cu": 0, "cp": 0, "arch": 0, "bytes": 0,
                               "first": None, "last": None, "disp": ws_path(r["cwd"])})
        a[cntkey[r["harness"]]] += 1   # archived/hidden も per-tool 総数に含める
        if r["archived"]:
            a["arch"] += 1             # OR で archive 印が付く本数 (計の括弧)
        a["bytes"] += max(r["bytes"], 0)
        if r["start"]:
            a["first"] = min(a["first"] or r["start"], r["start"])
        upd = r["updated"] or r["start"]
        if upd:
            a["last"] = max(a["last"] or upd, upd)

    def _total(a):
        return a["cc"] + a["cx"] + a["cu"] + a["cp"]

    # 並べ替え (会話一覧と統一: 既定 start=初回活動、start/end とも新しい順、--reverse で反転)。
    items = list(agg.items())
    how = args.sort if args.sort in ("end", "size", "total", "path") else "start"
    if how == "end":
        keyf, desc = (lambda kv: kv[1]["last"] or _MIN_DT), True
    elif how == "size":
        keyf, desc = (lambda kv: kv[1]["bytes"]), True
    elif how == "total":
        keyf, desc = (lambda kv: _total(kv[1])), True
    elif how == "path":
        keyf, desc = (lambda kv: kv[1]["disp"]), False
    else:  # start = 初回活動 (first, 新しい順が既定)
        keyf, desc = (lambda kv: kv[1]["first"] or _MIN_DT), True
    items.sort(key=keyf, reverse=desc ^ args.reverse)
    nws = len(items)
    if args.head:
        items = items[:args.head]   # 先頭 N WS (Unix head)
    if args.tail:
        items = items[-args.tail:]  # 末尾 N WS (Unix tail)
    if args.json:
        print(json.dumps([{"i": i, "cwd": v["disp"], "total": _total(v),
                           **{kk: (vv.isoformat() if isinstance(vv, datetime.datetime) else vv)
                              for kk, vv in v.items() if kk != "disp"}}
                          for i, (k, v) in enumerate(items, 1)],
                         ensure_ascii=False, indent=1))
        return
    shown = f"{len(items)} of {nws} WS" if len(items) < nws else f"{nws} WS"
    print(f"# chat-list --workspaces ({shown}), CC=claude CX=codex CU=cursor CP=copilot, "
          f"sort: {_sort_label(args.sort, args.reverse)}")
    print()

    def cols(c0, c1, c2, c3, c4, c5, c6):  # #, CC, CX, CU, CP, total, arch
        return (rpad(c0, 3) + "  " + rpad(c1, 3) + "  " + rpad(c2, 3) + "  " + rpad(c3, 3) + "  "
                + rpad(c4, 3) + "  " + rpad(c5, 5) + "  " + rpad(c6, 4) + "  ")

    print(cols("#", "CC", "CX", "CU", "CP", "total", "arch") + rpad("size", 4) + "  "
          + pad("start", 12) + pad("end", 12) + "path")
    for i, (k, a) in enumerate(items, 1):
        arch = f"-{a['arch']}" if a["arch"] else ""
        print(cols(str(i), str(a["cc"]), str(a["cx"]), str(a["cu"]), str(a["cp"]), str(_total(a)), arch)
              + rpad(human_size(a["bytes"]), 4) + "  "
              + pad(loc_str(a["first"])[:10], 12) + pad(loc_str(a["last"])[:10], 12)
              + a["disp"].replace(_HOME_DISP, "~"))


# ---------- 出力: dump ----------
def find_by_id(cid, include_subagents=True, include_archived=True):
    hits = []
    sources = [iter_claude_sessions(None),
               iter_codex_sessions(None, include_subagents, include_archived),
               iter_cursor_sessions(None, include_subagents=True),
               iter_copilot_sessions(None),
               iter_copilot_cli_sessions(None)]
    for src in sources:
        for r in src:
            if r["id"] == cid or r["id"].startswith(cid):
                hits.append(r)
    return hits


_HARNESS_NAME = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor", "copilot": "Copilot"}
_DUMP_RULE = "# " + "─" * 64   # 情報ブロック枠 + 各メッセージ前の区切り (U+2500。本文と被りにくい)


def _dur_str(a, b):
    """2 時刻の差を 1d2h3m 風に (会話の所要時間)。負/欠損は空。"""
    if not a or not b:
        return ""
    secs = int((b - a).total_seconds())
    if secs < 0:
        return ""
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m or not parts:
        parts.append(f"{m}m")
    return "".join(parts)


def _event_count(rec):
    """ソースの生イベント数 (tool 呼び出し・reasoning 等も含むので messages より多い)。取得不可は None。"""
    h = rec["harness"]
    if h == "cursor":
        return rec.get("_nevents")  # 列挙時に同梱した bubble 総数 (virtual path)
    p = rec.get("path")
    if not p or not os.path.exists(p):
        return None
    if h == "copilot" and rec.get("_kind") != "cli":   # VS Code chat (.json/.jsonl)
        d = _copilot_load(p)
        return sum(1 + len(req.get("response") or []) for req in (d.get("requests") or [])) if d else None
    try:  # jsonl 系 (claude / codex / copilot CLI): 非空行 = 1 イベント
        with open(p, encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return None


def _dump_info(rec, msgs):
    """dump 冒頭の情報ブロックの内容 (key : value 行のみ。罫線は呼び出し側で前置)。"""
    n_user = sum(1 for r, _, _ in msgs if r == "user")
    n_asst = sum(1 for r, _, _ in msgs if r == "assistant")
    mts = [ts for _, ts, _ in msgs if ts]
    first = min(mts) if mts else rec["start"]
    last = max(mts) if mts else (rec["updated"] or rec["start"])
    span = ""
    if first and last:
        lo, hi = loc_str(first), loc_str(last)
        if hi[:10] == lo[:10]:      # 同日なら右側は時刻のみ
            hi = hi[11:]
        span = f"{lo} → {hi}"
        d = _dur_str(first, last)
        if d:
            span += f"  ({d})"
    arch = "  [archived]" if rec.get("archived") else ""
    model = rec.get("model")  # codex/CLI は --long でしか入らないので dump 時に遅延取得
    if not model and rec.get("path"):
        if rec["harness"] == "codex":
            model = _codex_model(rec["path"])
        elif rec["harness"] == "copilot" and rec.get("_kind") == "cli":
            model = _copilot_cli_model(rec["path"])
    ev = _event_count(rec)
    # title は最後に置く (改行を畳んで 1 行化 — 長い/多行タイトルが上の情報を押し流さないように)
    title = " ".join((rec["title"] or "").split()) or "(untitled)"
    rows = [
        ("id", rec["id"]),
        ("origin", f"{origin_label(rec)}  ({_HARNESS_NAME.get(rec['harness'], rec['harness'])}){arch}"),
        ("model", model or "-"),
        ("messages", f"{len(msgs)}  ({n_user} user / {n_asst} assistant)"),
        ("events", str(ev) if ev is not None else "-"),
        ("span", span or "-"),
        ("size", human_size(rec["bytes"])),
        ("cwd", (ws_path(rec["cwd"]) or "(unknown)").replace(_HOME_DISP, "~")),
        ("path", (rec["path"] or "").replace(_HOME_DISP, "~")),
        ("title", title),
    ]
    kw = max(len(k) for k, _ in rows)
    return "\n".join(f"# {k.ljust(kw)} : {v}" for k, v in rows)  # 内容のみ (罫線は cmd_dump が前置)


def cmd_dump(args):
    hits = find_by_id(args.dump)
    if not hits:
        sys.exit(f"[chat-list] 会話 id '{args.dump}' に一致なし")
    if len(hits) > 1:
        print(f"[chat-list] '{args.dump}' は {len(hits)} 件に一致。確定してください:", file=sys.stderr)
        for r in hits:
            print(f"  {r['id']}  {origin_label(r)}  {loc_str(r['start'])}  {r['title'][:50]}", file=sys.stderr)
        sys.exit(2)
    rec = hits[0]
    msgs = messages_of(rec)
    if args.json:  # 構造化 JSON (メッセージ配列)。ファイルに残すならリダイレクト ' > file'
        print(json.dumps({"id": rec["id"], "harness": rec["harness"], "origin": rec["origin"],
                          "model": rec.get("model"), "start": rec["start"], "updated": rec["updated"],
                          "cwd": ws_path(rec["cwd"]), "title": rec["title"], "path": rec["path"],
                          "messages": [{"role": rl, "ts": ts, "text": t} for rl, ts, t in msgs]},
                         ensure_ascii=False, indent=1, default=_json_default))
        return
    # 全体を「罫線 + 直後に内容」のブロック列で統一 (情報ブロックも本文と同じ流れ)。ブロック間は空行 1 つ。
    # メッセージ見出しは '### <role> [i/N] <ts>' (role 先頭 = grep アンカー、ASCII)。
    n = len(msgs)
    rolew = max((len(role) for role, _, _ in msgs), default=0)
    blocks = [_dump_info(rec, msgs)] + [
        f"### {role.ljust(rolew)} [{i}/{n}] {loc_str(ts) if ts else '(no-ts)'}\n{t}"
        for i, (role, ts, t) in enumerate(msgs, 1)]
    sys.stdout.write("\n\n".join(f"{_DUMP_RULE}\n{b}" for b in blocks) + "\n")


# ---------- CLI ----------
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="chat-list",
        description="claude/codex/cursor/copilot 会話履歴の横断リスト (読み取り専用)",
        epilog=(
            "記号・列:\n"
            "  origin = '<WS> CC|CX|CU|CP/<surface>'  (CC=Claude Code, CX=Codex, CU=Cursor, CP=Copilot)\n"
            "  origin 末尾 '*'     = archived/hidden (除外せず印)。--long で claude=*c(Cursor)/*v(VS Code)/*cv、他=*。\n"
            "                        --workspaces は arch 列に -N。\n"
            "  model 列            = --long 時のみ (cursor/copilot=記録値, claude=jsonl, codex/CLI=遅延取得)\n"
            "  size                = 会話バイト数 (--json は正確な bytes)\n"
            "  '#'                 = 表示ごとの通し番号 (不安定。確定は id か path)\n"
            "  sort               = 既定 start・新しい順。end=最終活動 / size / title(一覧) / total,path(--workspaces)。\n"
            "                        --reverse で反転。--path/--title は既定 部分一致 (--exact で完全一致)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # --path と --all は排他 (--all = path 絞り無し = 全 WS)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--path", action="append", metavar="VALUE",
                   help="WS を path で限定 (両モード)。既定は部分一致、--exact で完全一致。反復・カンマ区切りで複数可。"
                        "未指定: 一覧=現在 cwd / --workspaces=全 WS")
    g.add_argument("--all", action="store_true", help="全 WS (path 絞り無し)。--path と排他")
    p.add_argument("--exact", action="store_true", help="--path / --title を完全一致に (既定は部分一致)")
    p.add_argument("--workspaces", action="store_true", help="WS 一覧 (各 WS のチャット数概要)")
    p.add_argument("--dump", metavar="ID", help="指定 id の会話全文を出力")
    p.add_argument("--open", nargs="?", const="cursor", metavar="EDITOR",
                   help="出力を Cursor/VSCode の untitled バッファで開く (= '| EDITOR -')。"
                        "既定 cursor、'--open code' で VSCode。どのモードでも可")
    p.add_argument("--json", action="store_true",
                   help="機械可読の構造化 JSON で出力 (全モード。dump はメッセージ配列)")
    p.add_argument("--long", "-l", action="store_true",
                   help="long 表形式 (一覧=model 列を追加。--workspaces は将来用・現状は追加列なし)")
    p.add_argument("--preview", nargs="?", type=int, const=10, metavar="N",
                   help="一覧で各会話の本文プレビュー: N=先頭 N 行 / --preview=-N=末尾 N 行 / 単体=既定 10 行")
    p.add_argument("--head", type=int, metavar="N", help="出力の先頭 N 件に絞る (両モード・Unix 流)")
    p.add_argument("--tail", type=int, metavar="N", help="出力の末尾 N 件に絞る (両モード・Unix 流)")
    p.add_argument("--tool", choices=["claude", "codex", "cursor", "copilot"], help="ツールで絞る (両モード)")
    p.add_argument("--title", metavar="TEXT", help="タイトルで絞る (部分一致 / --exact で完全一致。両モード)")
    p.add_argument("--grep", metavar="TEXT", help="本文を全文検索して絞る (本文を読むので遅め。両モード)")
    p.add_argument("--include-subagents", action="store_true",
                   help="subagent も含める (codex の subagent + cursor の subagentComposerIds。両モード)")
    p.add_argument("--sort", choices=["start", "end", "size", "total", "title", "path"], default="start",
                   help="並び替えキー (既定 start。列 header 名と一致)。共通: start / end (最終活動) / size。"
                        "一覧専用: title。--workspaces 専用: total (本数) / path。"
                        "start/end/size/total は新しい/大きい順、title/path は昇順。--reverse で反転")
    p.add_argument("--reverse", "-r", action="store_true", help="並び順を反転 (両モード)")
    args = p.parse_args(argv)

    # mode で無効な sort キー (その列が無いモード) はエラー
    if not args.workspaces and args.sort in ("total", "path"):
        p.error(f"--sort {args.sort} は --workspaces 専用です (一覧では start / end / size / title)")
    if args.workspaces and args.sort == "title":
        p.error("--sort title は会話一覧専用です (--workspaces では start / end / size / total / path)")

    # --path はどのモードでも効く限定子。無ければ: 一覧=現在 cwd (完全一致) / --workspaces=全 WS。
    def resolve_pred(default_to_cwd):
        if args.path:
            targets = [x for v in args.path for x in v.split(",") if x]
            return make_multi_pred(targets, args.exact)
        if args.all:
            return None
        return make_cwd_pred(os.getcwd(), exact=True) if default_to_cwd else None

    def run():
        if args.dump:
            return cmd_dump(args)
        if args.workspaces:
            return cmd_workspaces(args, resolve_pred(default_to_cwd=False))
        cmd_list(args, resolve_pred(default_to_cwd=True))

    if not args.open:
        return run()
    # 出力をエディタの untitled バッファへ ('| EDITOR -' 相当)。データは run() が作り、ここは出力先のみ。
    editor = shutil.which(args.open)
    if not editor and args.open == "cursor":  # 既定 cursor が無ければ code へ。明示名のタイポは弾く。
        editor = shutil.which("code")
    if not editor:
        sys.exit(f"[chat-list] エディタ '{args.open}' が見つかりません")
    cap = io.StringIO()
    with contextlib.redirect_stdout(cap):
        run()
    subprocess.run([editor, "-"], input=cap.getvalue(), text=True)


if __name__ == "__main__":
    main()
