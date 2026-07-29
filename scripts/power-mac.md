# `power-mac.py`

A small, safe front-end over macOS power management (`pmset` + `caffeinate`).
It bundles the commands you reach for around travel and long-running jobs, so
you (or an agent) do not re-derive them each time. **macOS only.**

The headline case: run the Mac **with the lid closed and no external display**
on battery (e.g. an agent working while the machine is in a bag). macOS calls
lid-closing "Clamshell Sleep", and only `pmset disablesleep 1` suppresses it —
power assertions and `caffeinate` do not.

## Command groups

### Read-only (no authentication — an agent can run these directly)

```bash
python3 scripts/power-mac.py status      # source, battery %, adapter W, lid-closed flag, clamshell
python3 scripts/power-mac.py settings    # pmset custom (Battery|AC) + battery health + who prevents sleep
python3 scripts/power-mac.py history      # recent Sleep/Wake/DarkWake/Clamshell/Display events
python3 scripts/power-mac.py history --tail 40
python3 scripts/power-mac.py report --since 10:00   # sleep/wake timeline + battery drift over a window
python3 scripts/power-mac.py report --hours 2
```

`report` shows the battery drift over the window and, when the endpoints hide a
dip (e.g. a recharge after the drain), also the trough — so "how much did it
drain on battery" is visible even if it later charged back. It reads charge
samples via `log show`, so it works while the machine stayed fully awake, which
`pmset -g log` only annotates on sleeps/wakes.

### Privileged (root — you authenticate in Apple's own dialog)

`pmset` writes need root. These subcommands **never handle your password**.
Without `--apply` they only print the exact command and the old→new change:

```bash
python3 scripts/power-mac.py clamshell on     # prints the command; nothing changes
```

With `--apply` they fire the command through the macOS authentication dialog:

```bash
python3 scripts/power-mac.py clamshell on --apply    # macOS asks for your password
python3 scripts/power-mac.py clamshell off --apply   # restore normal lid-closed sleep
```

Under the hood, `--apply` runs:

```
osascript -e 'do shell script "/usr/bin/pmset ..." with administrator privileges'
```

macOS shows its standard auth dialog; you authenticate there and the password
stays inside the OS. Every value the tool passes to that root shell is checked
against a fixed whitelist first, so nothing arbitrary reaches root.

Generic whitelisted `pmset` passthrough and named presets:

```bash
python3 scripts/power-mac.py set displaysleep 2 --scope b --apply
python3 scripts/power-mac.py set powernap 0 --apply
python3 scripts/power-mac.py preset travel-clamshell --apply   # = clamshell on
python3 scripts/power-mac.py preset restore-defaults --apply   # = clamshell off
```

`--scope` is `a` (all, default), `b` (battery), or `c` (charger). Whitelisted
keys: `displaysleep`, `disksleep`, `sleep`, `powernap`, `standby`,
`tcpkeepalive`, `womp`, `lessbright`, `ttyskeepawake`, `acwake`, `lidwake`,
`halfdim`, `lowpowermode`, `hibernatemode`, `disablesleep`. Values are range-
or enum-checked per key; anything else is refused before it reaches root.

### keep-awake (no authentication — `caffeinate` wrapper)

Complements clamshell. `caffeinate` blocks **idle** sleep only (lid open); it
**cannot** keep a lid-closed Mac awake — use `clamshell on` for that.

```bash
python3 scripts/power-mac.py keep-awake --for 2h          # stay awake 2 hours
python3 scripts/power-mac.py keep-awake --while-pid 12345 # until that PID exits
python3 scripts/power-mac.py keep-awake --while make all  # for the lifetime of a command
```

## The lid-closed flag: what to remember

- `clamshell on` sets `pmset -b disablesleep 1`. Despite the `-b`, the flag is
  **system-wide** (it also stops idle sleep on AC) until turned off.
- It is a **runtime** flag: a **reboot clears it** automatically. It does not
  show up in `pmset -g custom`; check it with `power-mac.py status` (or
  `ioreg -r -c IOPMrootDomain -d 1 | grep -i SleepDisabled`).
- While set, the Mac will not idle-sleep either — in a bag it keeps draining.
  Run `clamshell off` (or reboot) when done.
- A **critically low battery hibernates regardless** of this flag.
- Set it (or verify `status`) **before** unplugging the external display: once
  the lid is shut, the screen is off and you cannot see whether it took.

## Safety notes

This is an unofficial local convenience tool. The privileged path runs `pmset`
as root via the macOS auth dialog; the read-only and `keep-awake` paths need no
elevation. Run `status` / a no-`--apply` privileged command first to preview.
