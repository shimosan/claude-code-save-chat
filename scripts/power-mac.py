#!/usr/bin/env python3
"""macOS power (pmset/caffeinate) front-end for agents and humans.

A thin, safe UI over Apple's power-management CLIs. It groups the commands you
reach for around travel and long-running jobs:

  read-only (no auth, an agent can run these directly):
    status     current power source, battery %, charging, adapter watts,
               SleepDisabled flag, clamshell (lid-closed) state
    settings   pmset -g custom split into Battery/AC, plus the live sleep
               assertions (who is preventing sleep right now) and battery
               health (cycle count / condition / max capacity)
    history    recent Sleep/Wake/DarkWake/Clamshell/Display events
    report     Sleep/Wake timeline + battery-charge drift over a time window

  privileged (needs root; the password is entered by YOU in Apple's own
  dialog -- this tool never sees or handles it):
    clamshell on|off   allow/disallow running with the lid closed and NO
                       external display on battery (pmset -b disablesleep)
    set KEY VALUE      whitelisted passthrough to `pmset` (displaysleep,
                       sleep, powernap, standby, hibernatemode, ...)
    preset NAME        a named group of `set`s (travel-clamshell,
                       restore-defaults)

  no-auth keep-awake (complements clamshell; caffeinate CANNOT keep a
  lid-closed Mac awake, only an idle one):
    keep-awake         wrap `caffeinate` for a duration / until a PID exits /
                       for the lifetime of a command

Why the two auth paths matter
-----------------------------
`pmset` writes need root. Rather than typing a password into a terminal (or
into an agent, which must never happen), the privileged subcommands, when run
with --apply, fire the command through:

    osascript -e 'do shell script "/usr/bin/pmset ..." with administrator privileges'

macOS shows its standard authentication dialog; you authenticate there. The
password stays inside the OS. Every value this tool passes to that root shell
is validated against a fixed whitelist first, so nothing arbitrary reaches root.

Without --apply, privileged subcommands only PRINT the exact command (both the
`sudo pmset` form and the osascript form) and the old->new change, so you can
review or run it yourself.

Clamshell vs caffeinate (learned the hard way)
----------------------------------------------
- Closing the lid triggers "Clamshell Sleep". Only `pmset disablesleep 1`
  suppresses it; power assertions do not. That is what `clamshell on` sets.
- `caffeinate` only blocks *idle* sleep (lid open). It is the right tool for
  "don't idle-sleep while this job runs", never for lid-closed operation.
- A critically low battery hibernates regardless of any of this.

Usage:
  python3 power-mac.py status
  python3 power-mac.py report --since 10:00
  python3 power-mac.py settings
  python3 power-mac.py clamshell on            # prints the command to run
  python3 power-mac.py clamshell on --apply    # fires the macOS auth dialog
  python3 power-mac.py set displaysleep 2 --scope b --apply
  python3 power-mac.py preset travel-clamshell --apply
  python3 power-mac.py keep-awake --for 2h
  python3 power-mac.py keep-awake --while-pid 12345

This is an unofficial local convenience tool. Use at your own risk.
"""
import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys

PMSET = "/usr/bin/pmset"
OSASCRIPT = "/usr/bin/osascript"
CAFFEINATE = "/usr/bin/caffeinate"

# --- privileged `set` whitelist ------------------------------------------------
# Each key maps to a validator for its value. Only keys/values that pass are
# ever assembled into the root shell command. INT(lo, hi) allows an integer in
# [lo, hi]; ENUM(...) allows one of the listed literal tokens.


def INT(lo, hi):
    def check(v):
        if not re.fullmatch(r"\d{1,5}", v):
            return False
        return lo <= int(v) <= hi
    return check


def ENUM(*allowed):
    allowed = set(allowed)
    return lambda v: v in allowed


# Boolean-ish pmset keys take 0/1; timers take minutes; a few take small enums.
SET_KEYS = {
    "displaysleep": INT(0, 600),
    "disksleep": INT(0, 600),
    "sleep": INT(0, 600),
    "powernap": ENUM("0", "1"),
    "standby": ENUM("0", "1"),
    "tcpkeepalive": ENUM("0", "1"),
    "womp": ENUM("0", "1"),
    "lessbright": ENUM("0", "1"),
    "ttyskeepawake": ENUM("0", "1"),
    "acwake": ENUM("0", "1"),
    "lidwake": ENUM("0", "1"),
    "halfdim": ENUM("0", "1"),
    "lowpowermode": ENUM("0", "1"),
    "hibernatemode": ENUM("0", "3", "25"),
    "disablesleep": ENUM("0", "1"),
}

SCOPE_FLAG = {"a": "-a", "b": "-b", "c": "-c"}
SCOPE_NAME = {"a": "all", "b": "battery", "c": "charger"}

# Named presets: ordered list of (scope, key, value) triples.
PRESETS = {
    # Run lid-closed with no external display on battery. Reversible.
    "travel-clamshell": [("b", "disablesleep", "1")],
    # Undo the above.
    "restore-defaults": [("b", "disablesleep", "0")],
}


def die(msg, code=2):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def require_macos():
    if sys.platform != "darwin":
        die("this tool only runs on macOS (darwin).")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# --- read-only helpers ---------------------------------------------------------


def pmset_g(*args):
    r = run([PMSET, "-g", *args])
    return r.stdout


def parse_custom():
    """Return {'battery': {k: v}, 'ac': {k: v}} from `pmset -g custom`."""
    out = pmset_g("custom")
    result = {"battery": {}, "ac": {}}
    cur = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Battery Power"):
            cur = "battery"
            continue
        if s.startswith("AC Power"):
            cur = "ac"
            continue
        if cur is None or not s:
            continue
        # pmset prints "<key words> <value>"; the value is always the last
        # token (a number or a path), so split off the trailing token.
        parts = s.rsplit(None, 1)
        if len(parts) == 2:
            result[cur][parts[0]] = parts[1]
    return result


def battery_line():
    out = pmset_g("batt")
    src = "AC" if "AC Power" in out else "Battery"
    pct = None
    charging = None
    m = re.search(r"(\d+)%", out)
    if m:
        pct = int(m.group(1))
    if "; charging" in out:
        charging = "charging"
    elif "; discharging" in out:
        charging = "discharging"
    elif "; charged" in out:
        charging = "charged"
    elif "not charging" in out:
        charging = "not charging"
    return src, pct, charging


def sleep_disabled():
    r = run(["/usr/sbin/ioreg", "-r", "-c", "IOPMrootDomain", "-d", "1"])
    return "\"SleepDisabled\" = Yes" in r.stdout


def adapter_watts():
    out = pmset_g("adapter")
    m = re.search(r"Wattage\s*=\s*(\d+)", out)
    return int(m.group(1)) if m else None


def is_clamshell():
    """True if the built-in display is not present (lid closed w/ external)."""
    r = run(["/usr/sbin/system_profiler", "SPDisplaysDataType"])
    # The internal panel reports as "Color LCD"/"Liquid Retina ..."; when the
    # lid is closed in clamshell it drops out of the display list entirely.
    return "Color LCD" not in r.stdout and "Built-In" not in r.stdout


def battery_health():
    r = run(["/usr/sbin/system_profiler", "SPPowerDataType"])
    out = r.stdout
    fields = {}
    for key, label in [
        ("Cycle Count", "cycles"),
        ("Condition", "condition"),
        ("Maximum Capacity", "max_capacity"),
    ]:
        m = re.search(re.escape(key) + r":\s*(.+)", out)
        if m:
            fields[label] = m.group(1).strip()
    return fields


def cmd_status(_args):
    require_macos()
    src, pct, charging = battery_line()
    watts = adapter_watts()
    disabled = sleep_disabled()
    clam = is_clamshell()
    print("Power source     : %s" % src)
    print("Battery          : %s%%%s" % (
        pct if pct is not None else "?",
        (" (%s)" % charging) if charging else ""))
    if src == "AC" and watts:
        print("Adapter          : %dW" % watts)
    print("Lid-closed sleep : %s" % (
        "DISABLED (will stay awake with lid shut)" if disabled
        else "enabled (lid shut -> sleep)"))
    print("Clamshell now    : %s" % ("yes (internal display off)" if clam else "no"))


def cmd_settings(_args):
    require_macos()
    cust = parse_custom()
    print("== pmset settings (Battery | AC) ==")
    keys = sorted(set(cust["battery"]) | set(cust["ac"]))
    width = max((len(k) for k in keys), default=0)
    for k in keys:
        b = cust["battery"].get(k, "-")
        a = cust["ac"].get(k, "-")
        print("  %-*s  %-10s | %s" % (width, k, b, a))
    print("\n== battery health ==")
    for k, v in battery_health().items():
        print("  %-13s %s" % (k + ":", v))
    print("\n== sleep assertions (who is preventing sleep now) ==")
    out = pmset_g("assertions")
    shown = False
    for line in out.splitlines():
        if re.search(r"pid \d+\(", line):
            print("  " + line.strip())
            shown = True
    if not shown:
        print("  (none)")


# --- log parsing (history / report) --------------------------------------------

LOG_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})")
CHARGE = re.compile(r"Charge:(\d+)%")


def pmset_log_lines():
    return pmset_g("log").splitlines()


def _event_kind(line):
    if "Clamshell Sleep" in line:
        return "Clamshell"
    if "Display is turned on" in line:
        return "Display-on"
    if "Display is turned off" in line:
        return "Display-off"
    if re.search(r"\bDarkWake\b", line):
        return "DarkWake"
    if re.search(r"\bWake\b", line) and "FullWake" in line:
        return "Wake"
    if re.search(r"^\S+ \S+ \S+\s+Sleep\b", line) or "Entering Sleep state" in line:
        return "Sleep"
    return None


def _iter_events(window_start=None):
    for line in pmset_log_lines():
        m = LOG_TS.match(line)
        if not m:
            continue
        ts = _dt.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")
        if window_start and ts < window_start:
            continue
        kind = _event_kind(line)
        if not kind:
            continue
        cm = CHARGE.search(line)
        charge = int(cm.group(1)) if cm else None
        yield ts, kind, charge


def cmd_history(args):
    require_macos()
    events = list(_iter_events())
    tail = args.tail if args.tail else 25
    for ts, kind, charge in events[-tail:]:
        c = (" %d%%" % charge) if charge is not None else ""
        print("%s  %-11s%s" % (ts.strftime("%Y-%m-%d %H:%M:%S"), kind, c))


def _resolve_window(args):
    now = _dt.datetime.now()
    if args.since:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", args.since)
        if not m:
            die("--since must look like HH:MM")
        start = now.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                            second=0, microsecond=0)
        if start > now:
            start -= _dt.timedelta(days=1)
        return start
    hours = args.hours if args.hours else 3
    return now - _dt.timedelta(hours=hours)


def _charge_samples(start):
    """Battery %% samples in the window via `log show` (works while awake too).

    Returns a de-duplicated list of (datetime, pct, source). Slower than pmset
    -g log (spawns the unified-log reader), but it captures charge while the
    machine is fully awake, which pmset -g log only annotates on sleep/wakes.
    """
    r = run(["/usr/bin/log", "show", "--style", "compact",
             "--start", start.strftime("%Y-%m-%d %H:%M:%S"),
             "--predicate", 'eventMessage CONTAINS "Battery capacity change"'])
    samples = []
    last = None
    pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Capacity:(\d+) Source:(\w+)")
    for line in r.stdout.splitlines():
        m = pat.match(line)
        if not m:
            continue
        ts = _dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        pct, src = int(m.group(2)), m.group(3)
        if last == (pct, src):
            continue
        last = (pct, src)
        samples.append((ts, pct, src))
    return samples


def cmd_report(args):
    require_macos()
    start = _resolve_window(args)
    events = list(_iter_events(window_start=start))
    print("== power activity since %s ==" % start.strftime("%Y-%m-%d %H:%M"))
    if not events:
        print("  (no sleep/wake/display events in window)")
    real_sleep = 0
    for ts, kind, charge in events:
        c = (" %d%%" % charge) if charge is not None else ""
        note = ""
        if kind == "Sleep":
            real_sleep += 1
        if kind == "Clamshell":
            note = "  <- lid-closed sleep"
        print("  %s  %-11s%s%s" % (ts.strftime("%H:%M:%S"), kind, c, note))
    print("")
    samples = _charge_samples(start)
    if len(samples) >= 2:
        (t0, c0, _), (t1, c1, _) = samples[0], samples[-1]
        span = t1 - t0
        pcts = [p for _, p, _ in samples]
        lo, hi = min(pcts), max(pcts)
        line = "  battery: %d%% -> %d%% over %s" % (c0, c1, _fmt_span(span))
        # Surface the trough/peak when the endpoints hide it (e.g. a recharge
        # after the drain), so the on-battery dip is not lost.
        extra = []
        if lo < min(c0, c1):
            extra.append("dipped to %d%%" % lo)
        if hi > max(c0, c1):
            extra.append("rose to %d%%" % hi)
        if extra:
            line += " (" + ", ".join(extra) + ")"
        else:
            mins = span.total_seconds() / 60.0
            rate = ((c0 - c1) / (mins / 60.0)) if mins > 0 else 0.0
            line += " (%+d pts, ~%.1f %%/h)" % (c1 - c0, rate)
        print(line)
    else:
        print("  battery: no capacity samples in window")
    print("  real Sleep events in window: %d%s" % (
        real_sleep,
        "  (0 = stayed awake the whole time)" if real_sleep == 0 else ""))


def _fmt_span(td):
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return "%dh%02dm" % (h, m)
    return "%dm" % m


# --- privileged actions --------------------------------------------------------


def _pmset_cmd_str(scope, key, value):
    return "%s %s %s %s" % (PMSET, SCOPE_FLAG[scope], key, value)


def _old_value(scope, key):
    # disablesleep is a runtime flag, not listed in `pmset -g custom`; read the
    # live kernel state instead of showing "?".
    if key == "disablesleep":
        return "1" if sleep_disabled() else "0"
    cust = parse_custom()
    if scope == "c":
        return cust["ac"].get(key, "?")
    if scope == "b":
        return cust["battery"].get(key, "?")
    # scope "a": show both
    return "battery=%s / ac=%s" % (
        cust["battery"].get(key, "?"), cust["ac"].get(key, "?"))


def _fire_admin(cmd_str):
    """Run cmd_str as root via the macOS auth dialog. Password stays in the OS."""
    escaped = cmd_str.replace("\\", "\\\\").replace('"', '\\"')
    apple = 'do shell script "%s" with administrator privileges' % escaped
    print("Requesting authorization via macOS dialog...")
    r = subprocess.run([OSASCRIPT, "-e", apple])
    if r.returncode != 0:
        die("authorization was cancelled or failed (pmset not changed).", 1)
    print("Applied.")


def _apply_or_show(scope, key, value, apply):
    old = _old_value(scope, key)
    cmd = _pmset_cmd_str(scope, key, value)
    print("  %-13s %s: %s -> %s" % (key, SCOPE_NAME[scope], old, value))
    if apply:
        _fire_admin(cmd)
    else:
        print("  run in Terminal:  sudo %s %s %s %s"
              % ("pmset", SCOPE_FLAG[scope], key, value))
        print("  or fire the macOS auth dialog:  re-run with --apply")


def _validate(key, value):
    if key not in SET_KEYS:
        die("key '%s' is not in the whitelist (%s)"
            % (key, ", ".join(sorted(SET_KEYS))))
    if not SET_KEYS[key](value):
        die("value '%s' is not allowed for key '%s'" % (value, key))


def cmd_clamshell(args):
    require_macos()
    value = "1" if args.state == "on" else "0"
    if args.state == "on":
        print("Enabling lid-closed operation (stays awake with the lid shut).")
        print("Note: also stops idle sleep until turned off; remember to run")
        print("      `clamshell off` (or reboot) afterwards to save battery.")
    else:
        print("Restoring normal lid-closed sleep.")
    _apply_or_show("b", "disablesleep", value, args.apply)


def cmd_set(args):
    require_macos()
    _validate(args.key, args.value)
    _apply_or_show(args.scope, args.key, args.value, args.apply)


def cmd_preset(args):
    require_macos()
    if args.name not in PRESETS:
        die("unknown preset '%s' (have: %s)"
            % (args.name, ", ".join(sorted(PRESETS))))
    steps = PRESETS[args.name]
    print("Preset '%s' -> %d change(s):" % (args.name, len(steps)))
    for scope, key, value in steps:
        _validate(key, value)
        _apply_or_show(scope, key, value, args.apply)


# --- caffeinate (no auth) ------------------------------------------------------


def _parse_duration(s):
    m = re.fullmatch(r"(\d+)([smh])", s)
    if not m:
        die("--for must look like 30m, 2h, 90s")
    n = int(m.group(1))
    return n * {"s": 1, "m": 60, "h": 3600}[m.group(2)]


def _exec_caffeinate(cmd):
    # execv replaces the process without flushing Python's buffers; off a tty
    # stdout is block-buffered, so the notes printed above would be lost.
    sys.stdout.flush()
    os.execv(CAFFEINATE, cmd)


def cmd_keep_awake(args):
    require_macos()
    if not shutil.which("caffeinate") and not os.path.exists(CAFFEINATE):
        die("caffeinate not found.")
    base = [CAFFEINATE, "-dimsu"]  # display, idle, disk, system, user-active
    if args.while_cmd:
        print("Keeping awake while running: %s" % " ".join(args.while_cmd))
        print("(idle sleep only -- a closed lid still sleeps; use `clamshell on` for that)")
        _exec_caffeinate(base + args.while_cmd)
    if args.while_pid:
        print("Keeping awake until PID %d exits (idle sleep only)." % args.while_pid)
        _exec_caffeinate(base + ["-w", str(args.while_pid)])
    if args.for_:
        secs = _parse_duration(args.for_)
        print("Keeping awake for %s (idle sleep only). Ctrl-C to stop early." % args.for_)
        _exec_caffeinate(base + ["-t", str(secs)])
    die("pick one of --for / --while-pid / --while")


def build_parser():
    p = argparse.ArgumentParser(
        prog="power-mac.py",
        description="macOS power (pmset/caffeinate) front-end.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="current power/battery/clamshell state").set_defaults(func=cmd_status)
    sub.add_parser("settings", help="pmset custom + health + assertions").set_defaults(func=cmd_settings)

    ph = sub.add_parser("history", help="recent sleep/wake events")
    ph.add_argument("--tail", type=int, default=0, help="show last N events (default 25)")
    ph.set_defaults(func=cmd_history)

    pr = sub.add_parser("report", help="sleep/wake + battery drift over a window")
    pr.add_argument("--since", help="window start today, HH:MM")
    pr.add_argument("--hours", type=int, help="window length in hours (default 3)")
    pr.set_defaults(func=cmd_report)

    pc = sub.add_parser("clamshell", help="allow/disallow lid-closed operation")
    pc.add_argument("state", choices=["on", "off"])
    pc.add_argument("--apply", action="store_true", help="fire the macOS auth dialog")
    pc.set_defaults(func=cmd_clamshell)

    ps = sub.add_parser("set", help="whitelisted pmset key=value")
    ps.add_argument("key")
    ps.add_argument("value")
    ps.add_argument("--scope", choices=["a", "b", "c"], default="a",
                    help="a=all (default), b=battery, c=charger")
    ps.add_argument("--apply", action="store_true", help="fire the macOS auth dialog")
    ps.set_defaults(func=cmd_set)

    pp = sub.add_parser("preset", help="apply a named group of settings")
    pp.add_argument("name", help="one of: " + ", ".join(sorted(PRESETS)))
    pp.add_argument("--apply", action="store_true", help="fire the macOS auth dialog")
    pp.set_defaults(func=cmd_preset)

    pk = sub.add_parser("keep-awake", help="caffeinate wrapper (idle sleep only)")
    g = pk.add_mutually_exclusive_group()
    g.add_argument("--for", dest="for_", metavar="DURATION", help="e.g. 30m, 2h")
    g.add_argument("--while-pid", dest="while_pid", type=int, metavar="PID")
    g.add_argument("--while", dest="while_cmd", nargs=argparse.REMAINDER,
                   help="keep awake for the lifetime of this command")
    pk.set_defaults(func=cmd_keep_awake)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
