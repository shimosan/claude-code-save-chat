# Claude Code — library repo の保守ルール

この repo は Claude Code 等の設定を複数端末へ配布・同期する library。
ここは配布物そのものではなく、library を保守するための project memory。

## 構造
- `dotclaude/` — 各端末の `~/.claude/` へ deploy する同期マスター。
  - `dotclaude/CLAUDE.md` → `~/.claude/CLAUDE.md`(共有ルール + FREEZONE 共有メモリ)
  - `dotclaude/CLAUDE.local.md` → `~/.claude/CLAUDE.local.md` のひな型(端末ごとに記入)
- `commands/*.md` — `~/.claude/commands/` へ deploy する slash command。
- `codex/`, `copilot/` — 他ツール向けの一方向配布原本。
- `local/`, `notes/`, `scratch/` — gitignored なローカル領域。

## 編集の正
- 共有ルール・コマンドの編集の正は library 側(`dotclaude/`, `commands/`)。
  端末側(`~/.claude/`)を直接いじったら library へ戻す。
- load/save の手順と diff/merge ポリシーは `dotclaude/CLAUDE.md` の「同期 (load / save)」を参照。
- `dotclaude/CLAUDE.md` は subfolder ゆえ自動ロードされない。これは意図的 —
  編集対象(同期マスター)が自身を制御しないようにするため。
- 詳細は README.md。
