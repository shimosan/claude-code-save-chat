# Claude Code — library repo の保守ルール

この repo は Claude Code / Codex / Copilot 等の設定を複数端末へ配布・同期する library。
ここは配布物そのものではなく、library を保守するための project memory。

## 構造
- `dotclaude/` — 各端末の `~/.claude/` へ deploy する Claude Code 原本。
  - `dotclaude/CLAUDE.md` → `~/.claude/CLAUDE.md`(共有ルール + FREEZONE 共有メモリ)
  - `dotclaude/CLAUDE.local.md` → `~/.claude/CLAUDE.local.md` のひな型(端末ごとに記入)
- `commands/*.md` — `~/.claude/commands/` へ deploy する slash command。
- `dotcodex/` — 各端末の `~/.codex/` へ deploy する Codex 原本。
  - `dotcodex/AGENTS.md` → `~/.codex/AGENTS.md`(Claude Code 側ルール参照 adapter)
  - `dotcodex/skills/*/SKILL.md` → `~/.codex/skills/*/SKILL.md`
- `copilot/` — VS Code + GitHub Copilot 向け prompt 原本。
- `local/`, `notes/`, `scratch/` — gitignored なローカル領域。

## 編集の正
- 共有ルール・コマンド・skill の編集の正は library 側(`dotclaude/`, `commands/`, `dotcodex/`, `copilot/`)。
  端末側(`~/.claude/`, `~/.codex/`, VS Code User prompts 等)を直接いじったら library へ戻す。
- load/save の手順と diff/merge ポリシーは `dotclaude/CLAUDE.md` の「同期 (load / save)」を参照。
- `dotclaude/CLAUDE.md` は subfolder ゆえ自動ロードされない。これは意図的 —
  編集対象(同期マスター)が自身を制御しないようにするため。
- `dotcodex/AGENTS.md` は配布原本。`dotcodex/` 配下で作業する時に Codex が読んでも、
  library repo の保守ルールはこの `.claude/CLAUDE.md` が正。
- 詳細は README.md。
