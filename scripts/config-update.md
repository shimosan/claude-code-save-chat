# Config Update

Agent-facing public protocol for reviewing, proposing, and applying approved configuration changes from config snapshots.

This file is bootstrap knowledge for Claude Code, Codex, and thin skills such as `config-manager`. It must not contain private machine names, personal email addresses, real home paths, snapshot contents, or user-specific policy. Private knowledge lives in `local/`; append-only run history belongs in `log/config/`.

This is the workflow authority. A thin skill should read this file and follow it; it should not duplicate local policy, private recipes, or apply rules.

## Roles

- `scripts/config-snapshot-mac.py` / `scripts/config-snapshot-win.py`: input side. They record live state into normalized snapshots.
- `scripts/config-log-helper.py`: log helper. It reads `log/config/`, compares snapshots, summarizes timelines/drift/N-way state, and creates apply log skeletons. It must not edit live configuration.
- `scripts/config-apply-recipes.md`: public apply recipes. It describes concrete operations for approved changes.
- `local/config-policy.md`: private non-code policy and user decisions.
- `local/config-local-recipes.md`: optional private code-like apply recipes extracted from repeated successful applies.
- `local/machines.md`: optional private machine inventory.
- `log/config/`: private raw history, including snapshots and apply logs.

`config-update.md` owns how these inputs are read, how proposals are formed, and when local knowledge should be updated. The thin skill only routes user intent into this protocol.

## Safety Invariants

- Never edit live configuration before explicit user approval for the concrete change.
- In `review-only`, snapshot/log reads are allowed; live config writes are forbidden.
- Before file or directory changes, create a backup when feasible.
- Destructive operations need separate explicit approval even inside apply mode. Destructive operations include deleting settings, uninstalling extensions, replacing directories, restoring backups, and overwriting non-identical files.
- Operate on the current machine only. Other machines are updated by running the workflow on those machines.
- Do not use private notes, private logs, or `local/` contents as public examples.
- If policy, recipes, snapshots, or user intent conflict, stop and explain the conflict.

## OS And Snapshot Selection

Choose the snapshot script from the current OS. Do not ask the user to specify mac vs win unless detection fails.

```text
macOS / Darwin -> scripts/config-snapshot-mac.py
Windows        -> scripts/config-snapshot-win.py
other OS       -> stop; no snapshot script exists yet
```

If a snapshot script reports an OS mismatch, discard that run and rerun the correct script. A wrong-OS snapshot must not be used for comparison or apply decisions.

When loading historical snapshots, compare the snapshot top-level `os` field with the expected OS when known. If it conflicts, ignore that snapshot for decisions and explain why. Do not delete invalid historical snapshots unless the user explicitly asks for cleanup.

Run snapshot scripts directly or through a non-login, non-interactive shell when the agent tool allows it. Snapshot collection does not need shell startup files to be sourced by the runner.

For Codex `exec_command`, prefer:

```json
{ "login": false }
```

If a shell-startup warning appears but the snapshot exits successfully, writes the expected file, and the JSON contains the expected sources, treat the warning as diagnostic noise unless it points to missing snapshot data.

## Claude Config Layout In Snapshots

This library now stores its managed host/folder information in the unified `~/.claude/CLAUDE.md` layout. It no longer uses `~/.claude/CLAUDE.local.md` for that purpose, but users may still keep or create that file for their own independent Claude Code usage.

Snapshot scripts record this state as:

- `claude.md`: unified `~/.claude/CLAUDE.md` presence, managed-block marker presence, and parsed host-info values.
- `claude.legacy_local`: `~/.claude/CLAUDE.local.md` presence and parsed host-info-like values, for migration diagnostics and un-migrated library setups only.
- `claude`: Claude CLI version and installed slash command names.

Use `claude.md.value.host_info.hostname` as the preferred machine label source. Fall back to `claude.legacy_local` only for machines whose library-managed host/folder information has not yet been migrated to the unified layout. A migrated library setup should normally have `claude.md.value.has_library_island = true` (historical snapshot field name for the managed-block marker); `claude.legacy_local.value.present` may be true for unrelated user-managed content and is not, by itself, an error.

When comparing drift, do not treat a present `claude.legacy_local` on a migrated machine as an active source of truth for this library unless the current `claude.md` host-info is missing. If it contains only unrelated user-managed content, ignore it for library drift decisions.

## Modes

The agent must state the active mode before doing work.

### `review-only`

Use this for rehearsal, preflight, overview, comparison, proposal, and user discussion.

Allowed:

- read snapshots, apply logs, `local/` knowledge, notes, and config files
- run the appropriate snapshot script with `--log`
- create config snapshot logs under `log/config/`
- run `config-log-helper.py` read-only commands
- choose candidate public/private apply recipes and describe what they would do
- surface low-risk apply candidates when recent apply logs show the same
  operation pattern, while still requiring approval before any live write
- propose concise additions to `local/config-policy.md` or `local/config-local-recipes.md`

Forbidden:

- edit VS Code / Cursor User `settings.json`
- edit editor argv/config files
- run extension install/uninstall commands
- copy skills, prompts, CSS, shell profile blocks, or other assets into live user locations
- run any apply recipe command that changes live configuration
- write a completed `config_apply_<machine>_*.md`
- edit `local/config-policy.md` or `local/config-local-recipes.md` without explicit approval

### `apply`

Use this only after the user explicitly approves a concrete change.

Every apply-mode update should follow:

1. Record or reuse a current snapshot according to Snapshot Discipline.
2. Interpret the user's intent.
3. Read relevant snapshots, recent apply logs, and local knowledge. Use past
   applies as planning context even when they are not the direct source value.
4. Compare current state with the chosen reference.
5. Propose a concrete change with old/new values and target.
6. Get explicit user approval.
7. Apply the selected public or private recipe.
8. Verify directly and, when useful, record a verification snapshot.
9. Record a private config apply log in `log/config/` by default.
10. If the run reveals a stable convention, propose a concise `local/` knowledge update.

## Local Knowledge

Local knowledge is private and ignored by git. It is read and maintained by this protocol, not by thin skills.

### Files

Use these filenames:

- `local/machines.md`: machine inventory. Keep host names, OS, hardware, role, and short constraints here.
- `local/config-policy.md`: private non-code policy. Use for durable decisions, intentional differences, invariants, and warnings.
- `local/config-local-recipes.md`: optional private code-like recipes. Use for repeatable apply steps that are too user-specific for public `config-apply-recipes.md`.

If a file is missing, continue without it. Do not create missing local files unless the user approves the exact initial content.

### Read Order

At the start of review/apply work, read these when available:

1. `local/machines.md`
2. `local/config-policy.md`
3. `local/config-local-recipes.md`
4. relevant `log/config/` snapshots and apply logs

Use `local/machines.md` as inventory only. Do not duplicate machine profiles inside `config-policy.md`; put setting decisions in policy and basic machine facts in machines.

### `local/config-policy.md`

This file holds non-code policy: decisions, constraints, and intentional differences. It should stay concise.

Suggested shape:

```markdown
# Config Policy

## Global Invariants

- Rules that usually hold across machines.

## Intentional Differences

- Settings that may differ by machine, OS, role, display size, workplace constraints, or user preference.

## Domain Policies

### editor.display

### editor.extensions

### git

### shell

## User Decisions

- YYYY-MM-DD: scope, decision, reason.

## Avoid Or Confirm

- Changes that need extra confirmation before applying.
```

Do not put raw apply history, full snapshot values, long machine biographies, secrets, or one-off observations here. Leave one-off events in `log/config/`.

### `local/config-local-recipes.md`

This file holds private code-like recipes. It extends public apply recipes but does not replace the public safety protocol.

Suggested shape:

```markdown
# Config Local Recipes

## Recipe: <private-recipe-id>

Purpose:
When to use:
Inputs:
Preview:
Apply:
Verify:
Notes:
```

Use this only when a repeated successful apply pattern is too private, path-specific, or user-specific for `scripts/config-apply-recipes.md`.

### Updating Local Knowledge

`config-update.md` owns local knowledge update proposals.

When the agent sees a stable convention, intentional difference, or repeatable private recipe, it may propose an exact addition or edit to `local/config-policy.md` or `local/config-local-recipes.md`.

Before editing `local/`, the agent must:

- show the exact proposed text or patch
- explain why it belongs in `local/` instead of `log/config/`
- ask for explicit approval

Do not promote a one-time apply to local policy. Prefer apply logs until the pattern is stable.

## Log Layout

Raw history belongs in `log/config/`, not `local/`.

Snapshot filename:

```text
log/config/config_snapshot_<machine>_YYYY-MM-DD_HH-MM-SS.json
```

Apply log filename:

```text
log/config/config_apply_<machine>_YYYY-MM-DD_HH-MM-SS.md
```

One apply log file may contain multiple related patches when they were performed as one approved agent command run.

Use `scripts/config-log-helper.py` instead of rediscovering filename conventions.

```text
python3 scripts/config-log-helper.py latest --machine <machine> --expected-os mac
python3 scripts/config-log-helper.py list --machine <machine> --kind snapshot
python3 scripts/config-log-helper.py compare-summary <before-snapshot.json> <reference-snapshot.json>
python3 scripts/config-log-helper.py timeline --machine <machine> --expected-os mac
python3 scripts/config-log-helper.py timeline --all-machines
python3 scripts/config-log-helper.py nway --expected-os mac
python3 scripts/config-log-helper.py nway --expected-os mac --patterns
python3 scripts/config-log-helper.py drift --base-machine <machine> --expected-os mac
python3 scripts/config-log-helper.py drift --base-machine <machine> --expected-os mac --group-lines
python3 scripts/config-log-helper.py apply-log-skeleton --machine <machine> --recipe-id <recipe-id>
```

`timeline`, `nway`, and `drift` are raw summaries. They are useful inputs for agent explanation, not a substitute for judgment.

- `timeline`: chronological snapshots/apply logs. Snapshot rows show diff from the previous same-machine/same-OS snapshot, independent of apply logs.
- `drift`: base-machine latest snapshot vs latest snapshots from other machines. Direction is `base -> compared machine`: `+` means present only on compared machine, `-` means present only on base, `~ old -> new` means base value to compared value.
- `drift --group-lines`: groups identical displayed diff lines and lists target machines sharing each line.
- `nway`: fleet-level latest snapshot aggregation by flattened key and canonical value.
- `nway --patterns`: groups keys by machine split pattern and discards values.

None of these commands decides which side is correct or newer. Use timestamps, apply logs, local policy, and user intent.

### Apply Candidate Suggestions

Apply suggestions are allowed in `review-only`, but they should be grounded rather
than speculative. When a task may lead to apply, check recent apply logs for the
current machine and related machines before finalizing the plan. Prefer suggesting
a near-apply candidate when recent apply logs show the same kind of operation, the
source and target values are clear, and a public or private recipe already covers
the change.

When showing such candidates:

- label them as suggestions, not planned actions
- include the recent apply log or timestamp that makes the suggestion plausible
- show target, old value, new value, recipe, and risk class
- keep low-confidence, high-risk, destructive, identity/privacy, or provisioning
  changes in a separate review-only bucket
- do not apply until the user explicitly approves the concrete change

If there is no relevant recent apply history, keep the output to review and ask
which differences the user wants to pursue.

This rule also covers maintenance patches whose need recurs after software
updates. For example, if recent apply logs show that a local webview patch was
reapplied after extension updates, and current status shows the patch missing,
it is reasonable to suggest rerunning the patcher as a medium-risk candidate.

### Helper Output Passthrough

If the user asks for helper output "raw", "as-is", "そのまま", "生", or a plain list, show the helper stdout in a near-verbatim form. Do not replace it with only an agent summary. A short preface stating the command and a short note about limitations are fine, but the raw helper output should remain the main content.

If the helper output is too long for the response, show the beginning and the exact command that produced it, then offer a narrower helper command or filter. Do not silently collapse it into a high-level summary when the user requested raw output.

## Snapshot Discipline

Prefer simple auditable history over minimizing file count, but avoid repeated snapshot calls inside one command run.

Normal workflow:

1. At command start, run the appropriate snapshot script with `--log`.
2. Treat the created file as the current snapshot for this command.
3. Reuse that current snapshot for all comparisons and proposals in the same command run.
4. Do not take another snapshot before applying each individual key in the same approved batch.
5. In `review-only`, stop after comparison/proposal unless the user switches to `apply`.
6. After an apply batch, run the appropriate snapshot script with `--log` when a verification snapshot is useful.
7. Treat that file as the verification snapshot.
8. If another approved apply batch follows immediately in the same agent session, reuse the previous verification snapshot as the next batch's before snapshot unless the user reports intervening changes or the agent lost confidence.
9. Do not delete or rewrite snapshot files as part of normal update workflow.

If a user starts with `review-only`, thinks briefly, then invokes the agent again to apply the reviewed proposal, the agent may reuse the recent review snapshot as the apply before snapshot when all are true:

- same machine and OS
- same reviewed proposal
- recent review snapshot
- no apply log or known manual change after that snapshot
- exact review snapshot and proposed old/new values are still identifiable

Before applying, state that the review snapshot is being reused and that a fresh before snapshot is skipped. If there is ambiguity, take a fresh snapshot.

Snapshot garbage collection is a separate maintenance task. Do not perform it during normal update.

## Intent-Driven Comparison

Do not assume every request means "make this machine match the latest state on another machine." The user's request determines the comparison set.

Examples:

- "Make this editor font match <source-machine>" means compare current editor settings with that source machine's latest relevant snapshot.
- "Undo the font change I made today" means compare current same-machine snapshot with earlier same-machine snapshots before that change.
- "Restore the editor font from last week" means search historical same-machine snapshots near that time and propose candidate values.
- "Show me what changed since the last run" means compare current with the previous meaningful same-machine snapshot and propose nothing unless the user asks to apply.
- "Bring over useful changes from other machines" means compare latest snapshots across machines, classify differences, and ask which candidates are desired.

When the user gives an approximate time, present candidate timestamps and observed values. Do not silently pick a historical value when there is ambiguity.

User-facing history terms must not depend on internal agent snapshots. "Previous setting" and "before today's change" are interpreted from timestamps, apply logs, observed values, and context.

## Applying Changes

Concrete public apply procedures live in [`config-apply-recipes.md`](config-apply-recipes.md). Private extensions may live in `local/config-local-recipes.md`.

Recipe selection:

1. Prefer public recipes when they cover the operation.
2. Consult private local recipes for user-specific paths, repeated private steps, or constraints.
3. If public and private recipes conflict, stop and explain the conflict.
4. If no recipe fits, propose a review-only plan and ask before doing anything live.

Before applying, state a short apply brief:

- selected `recipe_id`
- mode: preview, apply, or verify
- current machine and OS
- target file, setting key, command, or tool
- old value and proposed new value, when applicable
- reference snapshot, policy, or user instruction used
- backup path or backup plan
- exact user approval text

Do not apply without explicit user approval. If the apply procedure cannot be followed, stop before changing live configuration.

After applying:

1. Verify directly when possible.
2. Record a verification snapshot when useful.
3. Create a `config_apply_<machine>_*.md` apply log by default. If an apply is
   too trivial to log, state that decision and why; otherwise treat a missing
   apply log as incomplete workflow.
4. Mention any reload/restart requirement.
5. Consider whether a concise local policy or local recipe proposal is warranted.

## First Use On A Machine

If no suitable snapshots exist for the current machine:

1. Run the appropriate snapshot script with `--log`.
2. Use `config-log-helper.py latest` to confirm it is valid.
3. Read `local/machines.md` if present.
4. Continue with review-only overview unless the user explicitly requests an apply.

If `local/config-policy.md` or `local/config-local-recipes.md` is absent, do not treat that as an error. Offer to create minimal files only if the user asks to establish local policy or if a concrete approved local knowledge entry is ready.

## Thin Skill Contract

A `config-manager` skill or command should be a thin entrypoint:

- For review/apply/config questions, read this file and follow it.
- For pure overview requests, it may directly run `config-log-helper.py timeline`, `drift`, or `nway`.
- It must not define private policy, local recipes, apply rules, or local file formats itself.
- It must not edit `local/config-policy.md` or `local/config-local-recipes.md` except through this workflow and explicit user approval.
