#!/usr/bin/env python3
"""chat-list core — claude-code と codex の会話履歴を横断で列挙・閲覧する決定的ツール.

LLM 推論ゼロ・読み取り専用。slash 皮 (dotclaude/commands/chat-list.md) から呼ばれる。
皮は「自然言語 → 確定セレクタ (cwd / 会話 id) の解決」と「dump 前の確認」を担い、
本 script は確定値だけを受けて機械的に動く。

データ源 (2026-06-18 実測):
- claude: ~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl
    開始 = 最初の timestamp / id = ファイル名 stem / 由来 = entrypoint /
    名前 = 最後の customTitle → 無ければ aiTitle / cwd = 各行の cwd フィールド
- codex : ~/.codex/sqlite/state_5.sqlite の threads テーブル (cwd/title/created_at/rollout_path)
    本体 = rollout_path の jsonl。subagent (source に subagent) / archived は既定で除外。

mtime は Dropbox 同期で揃い当てにならないので使わない (開始時刻は中身の timestamp)。
"""
import argparse
import contextlib
import datetime
import io
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import unicodedata

HOME = os.path.expanduser("~")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_DB = os.path.join(HOME, ".codex", "sqlite", "state_5.sqlite")

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


def make_cwd_pred(target, mode):
    """mode: exact | basename | substring。default は exact または basename 一致 (rename/正規化に強い)."""
    t = norm(target)
    tb = base(target)
    if mode == "exact":
        return lambda c: norm(c) == t
    if mode == "basename":
        return lambda c: base(c) == tb
    if mode == "substring":
        return lambda c: t in norm(c)
    return lambda c: norm(c) == t or base(c) == tb  # default


def make_multi_pred(targets, ws_match):
    """複数の WS 指定 (--ws 反復 / カンマ区切り) の OR。各値は '/' 始まりで厳密 path、他は部分一致."""
    preds = []
    for tv in targets:
        if tv.startswith("/"):
            mode = "exact" if ws_match == "default" else ws_match
        else:
            mode = "substring" if ws_match == "default" else ws_match
        preds.append(make_cwd_pred(tv, mode))
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
def _scan_claude_meta(path):
    """1 jsonl から (start, end, customTitle, aiTitle, entrypoint, cwd) を抽出.
    start=最初の timestamp, end=最後の timestamp (最終活動)。substring で json.loads を間引く."""
    start = end = ct = at = ep = cwd = None
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return None
    with f:
        for line in f:
            if not any(k in line for k in ('"timestamp"', '"customTitle"', '"aiTitle"', '"entrypoint"', '"cwd"')):
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("timestamp"):
                if start is None:
                    start = o["timestamp"]
                end = o["timestamp"]
            if o.get("customTitle"):
                ct = o["customTitle"]
            if o.get("aiTitle"):
                at = o["aiTitle"]
            if ep is None and o.get("entrypoint"):
                ep = o["entrypoint"]
            if cwd is None and o.get("cwd"):
                cwd = o["cwd"]
    return start, end, ct, at, ep, cwd


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


def iter_claude_sessions(pred=None):
    """pred(cwd)->bool で絞る。pred=None なら全件。
    encoded dir 直下の `*.jsonl` だけが top-level セッション。subagent の sidechain は
    `<dir>/<sessionId>/subagents/agent-*.jsonl` と入れ子なので os.listdir(1 階層) では拾わない."""
    if not os.path.isdir(CLAUDE_PROJECTS):
        return
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
            start, end, ct, at, ep, cwd = meta
            if pred is not None and (cwd is None or not pred(cwd)):
                continue
            fp = os.path.join(d, fn)
            yield {
                "id": fn[:-6],
                "harness": "claude",
                "origin": (ep or "?").replace("claude-", ""),
                "start": to_dt(start),
                "updated": to_dt(end),
                "title": ct or at or "",
                "cwd": cwd,
                "path": fp,
                "bytes": _filesize(fp),
                "archived": False,
            }


# ---------- codex ----------
def _codex_conn():
    if not os.path.exists(CODEX_DB):
        return None
    try:
        # pathlib.as_uri() で OS 非依存の file:// URI を作る (Windows のバックスラッシュ/ドライブ対策)
        return sqlite3.connect(pathlib.Path(CODEX_DB).as_uri() + "?mode=ro", uri=True, timeout=5)
    except sqlite3.OperationalError:
        return None


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
            out.append((role, t.strip()))
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
            out.append((pl["role"], t.strip()))
    return out


def messages_of(rec):
    if not rec["path"] or not os.path.exists(rec["path"]):
        return []
    return claude_messages(rec["path"]) if rec["harness"] == "claude" else codex_messages(rec["path"])


def text_lines(rec):
    lines = []
    for role, t in messages_of(rec):
        for i, ln in enumerate(t.split("\n")):
            lines.append((f"[{role}] " if i == 0 else "        ") + ln)
    return lines


def grep_matches(rec, term, maxn=4):
    """本文 (会話の中身) から term を含む行を抽出 (大文字小文字無視)。1 会話あたり maxn 行で打ち切り."""
    tl = term.lower()
    out = []
    for role, t in messages_of(rec):
        for ln in t.split("\n"):
            if tl in ln.lower():
                out.append(f"[{role}] {ln.strip()}")
                if len(out) >= maxn:
                    return out
    return out


# ---------- 収集 + フィルタ ----------
def _filesize(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def collect(args, pred):
    recs = []
    if args.tool in (None, "claude"):
        recs += list(iter_claude_sessions(pred))
    if args.tool in (None, "codex"):
        recs += list(iter_codex_sessions(pred, args.include_subagents, args.include_archived))
    # 重複排除: 同一セッションが複数 dir に物理コピーされている場合がある
    # (フォルダ rename / Dropbox 同期)。(harness, 完全 id) で束ね、最も完全な (大きい) コピーを残す。
    best = {}
    for r in recs:
        key = (r["harness"], r["id"])
        sz = r["bytes"]
        if key not in best or sz > best[key][0]:
            best[key] = (sz, r)
    recs = [v[1] for v in best.values()]
    if args.since:
        since = datetime.datetime.strptime(args.since, "%Y-%m-%d").astimezone()
        recs = [r for r in recs if r["start"] and r["start"] >= since]
    if args.title:
        g = args.title.lower()
        recs = [r for r in recs if g in r["title"].lower()]
    if args.grep:  # 本文の全文検索 (中身を読むので遅め)。一致した会話だけ残し、一致行を添える。
        kept = []
        for r in recs:
            m = grep_matches(r, args.grep)
            if m:
                r["_match"] = m
                kept.append(r)
        recs = kept
    recs.sort(key=lambda r: (r["start"] is None, r["start"]))
    return recs


def origin_label(rec):
    return ("CC/" if rec["harness"] == "claude" else "CX/") + rec["origin"]


_MIN_DT = datetime.datetime.min.replace(tzinfo=UTC)


def _sort_recs(recs, how, reverse=False):
    """会話一覧の並べ替え。既定 time=開始時刻、time/mtime とも新しい順 (最新が上)。--reverse で反転。
    キー: time=開始 / mtime=最終活動 / size=サイズ / name=タイトル。count は会話一覧には無効 → time."""
    how = how if how in ("mtime", "size", "name") else "time"
    if how == "mtime":
        keyf, desc = (lambda r: r["updated"] or r["start"] or _MIN_DT), True
    elif how == "size":
        keyf, desc = (lambda r: r["bytes"]), True
    elif how == "name":
        keyf, desc = (lambda r: r["title"].lower()), False
    else:  # time = 開始 (新しい順が既定)
        keyf, desc = (lambda r: r["start"] or _MIN_DT), True
    recs.sort(key=keyf, reverse=desc ^ reverse)
    return recs


def _list_sort_label(how, reverse):
    how = how if how in ("mtime", "size", "name") else "time"
    base = {"time": "開始時刻", "mtime": "最終活動", "size": "サイズ", "name": "タイトル"}[how]
    desc = (how in ("time", "mtime", "size")) ^ reverse
    if how in ("time", "mtime"):
        return base + ("↓ 新しい順" if desc else "↑ 古い順")
    return base + ("↓" if desc else "↑")


# ---------- 出力: 一覧 ----------
def _ws_key(r):
    return ws_key(r["cwd"])


def cmd_list(args, pred):
    recs = collect(args, pred)
    if args.limit:
        recs = recs[-args.limit:]
    recs = _sort_recs(recs, args.sort, args.reverse)
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
    if args.format == "json":
        # start / updated は datetime。default で ISO 文字列化する (片方漏れると TypeError)。
        print(json.dumps([{**r, "ws": letters[_ws_key(r)]} for r in recs],
                         ensure_ascii=False, indent=1, default=_json_default))
        return
    cc = sum(1 for r in recs if r["harness"] == "claude")
    cx = sum(1 for r in recs if r["harness"] == "codex")
    print("# chat-list  対象 WS:")
    if order:
        for k, cwd in order:
            print(f"#   {letters[k]}  {(ws_path(cwd) or '(不明)').replace(_HOME_DISP, '~')}  ({counts[k]}本)")
    else:
        print("#   (該当なし)")
    print(f"# 計 {len(recs)} 本 (claude {cc} + codex {cx})  ソート: {_list_sort_label(args.sort, args.reverse)}")
    if args.include_archived:
        print("# 由来末尾 * = archived (codex)")
    print()
    print(pad("#", 4) + pad(f"開始({TZLABEL})", 17) + pad("由来", 15) + pad("ID", 10)
          + rpad("サイズ", 6) + "  " + "タイトル")
    for i, r in enumerate(recs, 1):
        origin = f"{letters[_ws_key(r)]} {origin_label(r)}" + ("*" if r["archived"] else "")
        print(pad(str(i), 4) + pad(loc_str(r["start"]), 17) + pad(origin, 15)
              + pad(r["id"][:8], 10) + rpad(human_size(r["bytes"]), 6) + "  " + r["title"][:50])
        if r.get("_match"):  # --grep の一致行を優先表示
            for ln in r["_match"]:
                print(f"      ┊ {ln[:96]}")
        elif args.head or args.tail:
            lines = text_lines(r)
            sel = lines[: args.head] if args.head else lines[-args.tail:]
            for ln in sel:
                print(f"      ┊ {ln[:96]}")


# ---------- 出力: WS 一覧 ----------
def cmd_workspaces(args, pred=None):
    # census は一覧と同じ列挙 (per-session cwd + (harness,id) dedup) で作る → 表示と整合。
    # archived も常に数え (active=cx / archived=cxa)、subagent だけ除外。
    recs = []
    if args.tool in (None, "claude"):
        recs += list(iter_claude_sessions(None))
    if args.tool in (None, "codex"):
        recs += list(iter_codex_sessions(None, args.include_subagents, include_archived=True))
    best = {}
    for r in recs:
        key = (r["harness"], r["id"])
        sz = _filesize(r["path"])
        if key not in best or sz > best[key][0]:
            best[key] = (sz, r)

    agg = {}  # ws_key(cwd) -> dict(cc, cx, cxa, first, last, disp)
    for r in (v[1] for v in best.values()):
        if not r["cwd"]:
            continue
        if pred is not None and not pred(r["cwd"]):
            continue
        k = ws_key(r["cwd"])
        a = agg.setdefault(k, {"cc": 0, "cx": 0, "cxa": 0, "bytes": 0, "first": None,
                               "last": None, "disp": ws_path(r["cwd"])})
        a["cc" if r["harness"] == "claude" else ("cxa" if r["archived"] else "cx")] += 1
        a["bytes"] += max(r["bytes"], 0)  # WS の合計バイト数 (--sort size / サイズ列)
        if r["start"]:  # first = 初回活動 (最古の開始)
            a["first"] = min(a["first"] or r["start"], r["start"])
        upd = r["updated"] or r["start"]
        if upd:  # last = 最終活動 (最新の更新)
            a["last"] = max(a["last"] or upd, upd)

    # 並べ替え (会話一覧と統一: 既定 time=初回活動、time/mtime とも新しい順、--reverse で反転)。
    # time=初回活動(first) / mtime=最終活動(last) / size=合計バイト / count=本数 / name=path。
    items = list(agg.items())
    how = args.sort if args.sort in ("mtime", "size", "count", "name") else "time"
    if how == "mtime":
        keyf, desc = (lambda kv: kv[1]["last"] or _MIN_DT), True
    elif how == "size":
        keyf, desc = (lambda kv: kv[1]["bytes"]), True
    elif how == "count":
        keyf, desc = (lambda kv: kv[1]["cc"] + kv[1]["cx"] + kv[1]["cxa"]), True
    elif how == "name":
        keyf, desc = (lambda kv: kv[0]), False
    else:  # time = 初回活動 (first, 新しい順が既定)
        keyf, desc = (lambda kv: kv[1]["first"] or _MIN_DT), True
    items.sort(key=keyf, reverse=desc ^ args.reverse)
    if args.format == "json":
        print(json.dumps([{"i": i, "cwd": v["disp"],
                           **{kk: (vv.isoformat() if isinstance(vv, datetime.datetime) else vv)
                              for kk, vv in v.items() if kk != "disp"}}
                          for i, (k, v) in enumerate(items, 1)],
                         ensure_ascii=False, indent=1))
        return
    print(f"# chat-list --workspaces  ({len(items)} WS)   計=CC+CX(active)  CC=claude  CX=codex  "
          "*=archived(codex)  サイズ=会話合計バイト")
    print("# 行頭 # は表示ごとの通し番号 (不安定キー)。確定は WS の path。\n")

    def cols(c0, c1, c2, c3, c4):  # 固定幅・右寄せの数値カラム
        return rpad(c0, 3) + " " + rpad(c1, 4) + " " + rpad(c2, 4) + " " + rpad(c3, 4) + " " + rpad(c4, 4) + "  "

    print(cols("#", "計", "CC", "CX", "*") + rpad("サイズ", 6) + "  " + pad(f"期間({TZLABEL})", 24) + "WS")
    for i, (k, a) in enumerate(items, 1):
        period = f"{loc_str(a['first'])[:10]}〜{loc_str(a['last'])[:10]}"
        print(cols(str(i), str(a["cc"] + a["cx"]), str(a["cc"]), str(a["cx"]), str(a["cxa"]))
              + rpad(human_size(a["bytes"]), 6) + "  " + pad(period, 24) + a["disp"].replace(_HOME_DISP, "~"))


# ---------- 出力: dump ----------
def find_by_id(cid, include_subagents=True, include_archived=True):
    hits = []
    for r in iter_claude_sessions(None):
        if r["id"] == cid or r["id"].startswith(cid):
            hits.append(r)
    for r in iter_codex_sessions(None, include_subagents, include_archived):
        if r["id"] == cid or r["id"].startswith(cid):
            hits.append(r)
    return hits


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
    if args.raw:
        body = open(rec["path"], encoding="utf-8").read() if rec["path"] and os.path.exists(rec["path"]) else ""
    else:
        body = "\n\n".join(f"### {role}\n{t}" for role, t in messages_of(rec))
    header = (f"# {rec['title']}\n# id={rec['id']} {origin_label(rec)} 開始={loc_str(rec['start'])}\n"
              f"# cwd={ws_path(rec['cwd'])}\n# path={rec['path']}\n\n")
    out = header + body
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"[chat-list] {rec['id'][:8]} を書き出し: {args.out}  ({len(out)} 字)")
    else:
        sys.stdout.write(out + "\n")


# ---------- CLI ----------
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="chat-list",
        description="claude+codex 会話履歴の横断リスト (読み取り専用)",
        epilog=(
            "記号・列の見方:\n"
            "  由来列 = '<WSラベル> CC|CX/<起動元>'  (CC=Claude Code, CX=Codex)\n"
            "  由来末尾の '*'      = archived (codex のみ)\n"
            "  WSラベル A/B/C…     = 一覧冒頭 / --workspaces の対象 WS 凡例に対応\n"
            "  サイズ列            = 会話本体ファイルのバイト数 (--format json は正確な bytes)\n"
            "  '#'                 = 表示ごとに振り直す通し番号 (不安定。確定は id か WS path)\n"
            "  並び               = 既定 time=開始時刻・新しい順 (最新が上, 両モードとも開始基準)。\n"
            "                        mtime=最終活動 / size / count / name。--reverse で反転"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # --ws と --all-ws は排他 (--all-ws ≡ --ws * = 全 WS)
    gws = p.add_mutually_exclusive_group()
    gws.add_argument("--ws", action="append", metavar="VALUE",
                     help="WS 限定子 (どのモードでも有効)。'/'始まり=絶対パス(厳密) / 他=cwd 部分一致。"
                          "反復・カンマ区切りで複数可。未指定なら一覧は現在 cwd、--workspaces は全 WS")
    gws.add_argument("--all-ws", action="store_true",
                     help="全 WS (= --ws * 相当)。--ws とは排他")
    p.add_argument("--ws-match", choices=["default", "exact", "basename", "substring"], default="default",
                   help="--ws / 既定 cwd のマッチ方式 (default = 厳密 or basename 一致)")
    p.add_argument("--workspaces", action="store_true", help="WS 一覧 (各 WS のチャット数概要)")
    p.add_argument("--dump", metavar="ID", help="指定 id の会話全文を出力")
    p.add_argument("--out", metavar="FILE", help="--dump の書き出し先 (既定 stdout)")
    p.add_argument("--open", nargs="?", const="cursor", metavar="EDITOR",
                   help="出力を Cursor/VSCode の untitled バッファで開く (= '| EDITOR -')。"
                        "既定 cursor、'--open code' で VSCode。どのモードでも可")
    p.add_argument("--raw", action="store_true", help="--dump で生 jsonl を出す (既定は読めるテキスト)")
    p.add_argument("--head", type=int, metavar="N", help="各会話の先頭 N 行を併記")
    p.add_argument("--tail", type=int, metavar="N", help="各会話の末尾 N 行を併記")
    p.add_argument("--tool", choices=["claude", "codex"], help="ツールで絞る")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="この日付以降 (ローカル時刻)")
    p.add_argument("--title", metavar="TEXT", help="タイトルの部分一致で絞る (高速。全文検索ではない)")
    p.add_argument("--grep", metavar="TEXT", help="本文 (会話の中身) を全文検索して絞り、一致行も表示 (本文を読むので遅め)")
    p.add_argument("--include-subagents", action="store_true", help="codex の subagent スレッドも含める")
    p.add_argument("--include-archived", action="store_true", help="archived も含める")
    p.add_argument("--limit", type=int, help="会話一覧を末尾 N 件に絞る (--workspaces には効かない)")
    p.add_argument("--sort", choices=["time", "mtime", "size", "count", "name"], default="time",
                   help="並び替えキー (既定 time)。time=開始 / mtime=最終活動 (会話内の最後の timestamp。"
                        "OS の file mtime ではない) / size=バイト数 (会話一覧=会話ごと, --workspaces=合計) / "
                        "count=本数 (--workspaces 専用) / name。time/mtime/size/count は新しい/大きい順、name=昇順。"
                        "--workspaces では time=初回活動・mtime=最終活動。--reverse で反転")
    p.add_argument("--reverse", "-r", action="store_true", help="並び順を反転 (全モード・全キー共通)")
    p.add_argument("--format", choices=["table", "json"], default="table")
    args = p.parse_args(argv)

    # mode で無効な sort キーは黙ってフォールバックせずエラーにする
    if args.sort == "count" and not args.workspaces:
        p.error("--sort count は --workspaces 専用です (会話一覧では time / mtime / size / name)")

    # --ws はどのモードでも効く限定子。無ければ: list は現在 cwd / workspaces は全 WS が既定。
    def resolve_pred(default_to_cwd):
        if args.ws:
            targets = [x for v in args.ws for x in v.split(",") if x]
            return make_multi_pred(targets, args.ws_match)
        if args.all_ws:
            return None
        return make_cwd_pred(os.getcwd(), args.ws_match) if default_to_cwd else None

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
