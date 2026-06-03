#!/usr/bin/env node
/*
 * Patch VS Code/Cursor-like extension webviews so macOS Ctrl-F moves the caret
 * forward by one character inside contenteditable chat inputs.
 *
 * Why this exists:
 *   Claude Code and Codex render their chat UIs inside VS Code webviews. Their
 *   prompt inputs are web DOM editables, not native macOS text fields. Chromium
 *   handles some macOS/Emacs-style editing keys in contenteditable nodes, but
 *   Ctrl-F is not reliably mapped to "forward character". Native editor surfaces
 *   such as VS Code Copilot or Cursor Agent can get this behavior through the
 *   host editor stack; third-party webviews usually have to implement it.
 *
 * This is a local, reversible patch for installed extension assets. It does not
 * modify user settings or VS Code keybindings.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");

const home = os.homedir();
const marker = "codex-local-ctrlf-forward-char-shim";
const startMarker = `/* ${marker}:start */`;
const endMarker = `/* ${marker}:end */`;
const codexShimName = "ctrlf-forward-char-shim.js";

const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const patchAll = args.has("--all");
const listOnly = args.has("--list");
const statusOnly = args.has("--status");
const restore = args.has("--restore");
const help = args.has("--help") || args.has("-h");

if ([listOnly, statusOnly, restore].filter(Boolean).length > 1) {
  fail("Use only one of --list, --status, or --restore.");
}

// This code is injected into the extension webview itself. It intentionally does
// very little: only Ctrl-F, only when focus is in an editable element, and only
// one-character caret movement. The capture listener lets us handle the event
// before the app's React handlers or Chromium's incomplete default behavior.
const shim = `${startMarker}
(() => {
  function editableElement(target) {
    if (!(target instanceof Element)) return null;
    const el = target.closest('textarea,input,[contenteditable=""],[contenteditable="true"],[contenteditable="plaintext-only"]');
    if (!el) return null;
    if (el instanceof HTMLInputElement) {
      const type = (el.type || "text").toLowerCase();
      return /^(text|search|url|tel|password|email|number)$/.test(type) ? el : null;
    }
    return el;
  }

  function moveInputForward(el) {
    if (typeof el.selectionStart !== "number" || typeof el.selectionEnd !== "number") return false;
    const next = Math.min(el.value.length, Math.max(el.selectionStart, el.selectionEnd) + 1);
    el.setSelectionRange(next, next);
    return true;
  }

  function moveContentEditableForward() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    if (typeof sel.modify === "function") {
      // Selection.modify is supported by Chromium/WebKit and understands
      // bidi-aware "forward" movement better than manually walking text nodes.
      sel.modify("move", "forward", "character");
      return true;
    }
    return false;
  }

  document.addEventListener("keydown", (event) => {
    if (!event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    if ((event.key || "").toLowerCase() !== "f") return;
    const el = editableElement(event.target);
    if (!el) return;
    const moved = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
      ? moveInputForward(el)
      : moveContentEditableForward();
    if (moved) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
})();
${endMarker}
`;

// Most VS Code-family editors install extensions into versioned directories
// under one of these roots. Server roots are included so the same script can be
// used over Remote SSH/code-server-like environments when run on that host.
const defaultExtensionRoots = [
  ".vscode/extensions",
  ".vscode-insiders/extensions",
  ".cursor/extensions",
  ".windsurf/extensions",
  ".vscodium/extensions",
  ".vscode-server/extensions",
  ".vscode-server-insiders/extensions",
  ".cursor-server/extensions",
].map((rel) => path.join(home, rel));

const extensionRoots = [
  ...defaultExtensionRoots,
  // Extra roots make the script useful for forks and unusual installations
  // without requiring source edits.
  ...String(process.env.CTRL_F_FIX_EXTENSION_ROOTS || "")
    .split(path.delimiter)
    .map((root) => root.trim())
    .filter(Boolean)
    .map((root) => expandHome(root)),
].filter((root, index, roots) => roots.indexOf(root) === index);

const specs = [
  {
    label: "Claude Code",
    id: "anthropic.claude-code",
    publisher: "anthropic",
    name: "claude-code",
    target: "webview/index.js",
    kind: "append-js",
  },
  {
    label: "Codex",
    id: "openai.chatgpt",
    publisher: "openai",
    name: "chatgpt",
    target: "webview/index.html",
    kind: "html-shim",
  },
];

if (help) {
  console.log(`Usage: node scripts/patch-vscode-webview-ctrlf.js [options]

Options:
  --list       Show detected extension installs.
  --status     Show whether detected installs are patched.
  --restore    Remove this local patch from detected installs.
  --dry-run    Print what would change without writing files.
  --all        Patch/status/restore all non-obsolete installs, not just latest.
  --help       Show this help.

Environment:
  CTRL_F_FIX_EXTENSION_ROOTS
    Additional extension roots separated by '${path.delimiter}', for example
    "$HOME/.local/share/code-server/extensions".

After patching or restoring, run "Developer: Reload Window" in the editor.
`);
  process.exit(0);
}

function expandHome(value) {
  return value === "~" || value.startsWith("~/") ? path.join(home, value.slice(2)) : value;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function readText(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch {
    return null;
  }
}

function readObsolete(root) {
  // VS Code leaves old extension directories behind and records them in
  // .obsolete. Avoid patching stale versions that are no longer active.
  const data = readJson(path.join(root, ".obsolete"));
  return data && typeof data === "object" ? data : {};
}

function versionParts(version) {
  return String(version || "")
    .split(/[.-]/)
    .map((part) => (/^\d+$/.test(part) ? Number(part) : part.toLowerCase()));
}

function compareVersions(a, b) {
  // Extension versions here are simple numeric dotted versions in practice, but
  // this parser tolerates suffixes so forks do not sort completely wrong.
  const left = versionParts(a);
  const right = versionParts(b);
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i += 1) {
    const x = left[i] ?? 0;
    const y = right[i] ?? 0;
    if (x === y) continue;
    if (typeof x === "number" && typeof y === "number") return x - y;
    return String(x).localeCompare(String(y));
  }
  return 0;
}

function installedExtensions(root, spec) {
  if (!fs.existsSync(root)) return [];
  const obsolete = readObsolete(root);
  return fs
    .readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .filter((entry) => entry.name.startsWith(`${spec.id}-`))
    .filter((entry) => !obsolete[entry.name])
    .map((entry) => {
      const dir = path.join(root, entry.name);
      const pkg = readJson(path.join(dir, "package.json"));
      const target = path.join(dir, spec.target);
      return { root, dir, entryName: entry.name, pkg, target };
    })
    .filter(({ pkg, target }) => {
      // Directory name matching is only a fast prefilter. package.json is the
      // authoritative check that we are touching the expected extension.
      if (!pkg || !fs.existsSync(target)) return false;
      return (
        String(pkg.publisher || "").toLowerCase() === spec.publisher &&
        String(pkg.name || "").toLowerCase() === spec.name
      );
    })
    .map((candidate) => ({
      ...candidate,
      version: String(candidate.pkg.version || ""),
      mtimeMs: fs.statSync(candidate.dir).mtimeMs,
    }))
    .sort((a, b) => compareVersions(b.version, a.version) || b.mtimeMs - a.mtimeMs);
}

function backup(file) {
  // Backups sit next to the patched file so restore is possible even if the
  // script is moved later. The script's --restore removes only our injected
  // block, but full-file backups are useful for manual recovery.
  const stamp = new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14);
  let backupPath = `${file}.bak-${stamp}`;
  for (let i = 2; fs.existsSync(backupPath); i += 1) {
    backupPath = `${file}.bak-${stamp}-${i}`;
  }
  fs.copyFileSync(file, backupPath);
  return backupPath;
}

function removeInjectedBlock(text) {
  // Current patches have explicit start/end markers. The fallback handles the
  // first local version, which used only a single marker at the start.
  const blockPattern = new RegExp(`\\n?\\/\\* ${escapeRegExp(marker)}:start \\*\\/[\\s\\S]*?\\/\\* ${escapeRegExp(marker)}:end \\*\\/?\\n?`, "g");
  let next = text.replace(blockPattern, "\n");

  // Backward compatibility for the first local version, which only had one marker.
  const oldStart = text.indexOf(`/* ${marker} */`);
  if (oldStart !== -1 && next === text) {
    next = text.slice(0, oldStart).trimEnd() + "\n";
  }
  return next;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isClaudePatched(candidate) {
  const text = readText(candidate.target);
  return Boolean(text && text.includes(marker));
}

function patchClaude(candidate) {
  // Claude Code currently ships as a single webview/index.js bundle. Appending a
  // capture-phase listener at the end is less fragile than trying to edit a
  // minified React component by name.
  const text = readText(candidate.target);
  if (text === null) return result(candidate, "missing");
  const next = `${removeInjectedBlock(text).trimEnd()}\n\n${shim}`;
  if (next === text) return result(candidate, "already patched");
  if (dryRun) return result(candidate, text.includes(marker) ? "would update patch" : "would patch");
  const backupPath = backup(candidate.target);
  fs.writeFileSync(candidate.target, next);
  return result(candidate, text.includes(marker) ? "updated patch" : "patched", backupPath);
}

function restoreClaude(candidate) {
  const text = readText(candidate.target);
  if (text === null) return result(candidate, "missing");
  if (!text.includes(marker)) return result(candidate, "not patched");
  const next = removeInjectedBlock(text).trimEnd() + "\n";
  if (dryRun) return result(candidate, "would restore");
  const backupPath = backup(candidate.target);
  fs.writeFileSync(candidate.target, next);
  return result(candidate, "restored", backupPath);
}

function codexShimPath(candidate) {
  return path.join(path.dirname(candidate.target), codexShimName);
}

function isCodexPatched(candidate) {
  const text = readText(candidate.target);
  const shimText = readText(codexShimPath(candidate));
  return Boolean(text && text.includes(codexShimName) && shimText && shimText.includes(marker));
}

function patchCodex(candidate) {
  // Codex/OpenAI's extension uses an index.html that loads hashed module assets.
  // Rather than modifying a large hashed bundle, add a tiny stable shim file and
  // load it before the app entry module.
  const html = readText(candidate.target);
  if (html === null) return result(candidate, "missing");
  const shimFile = codexShimPath(candidate);
  const oldShim = readText(shimFile);
  const needsShim = oldShim !== shim;

  let next = html;
  if (!next.includes(codexShimName)) {
    next = next.replace(
      /(<script type="module" crossorigin src="\.\/assets\/index-[^"]+\.js"><\/script>)/,
      `<script type="module" crossorigin src="./${codexShimName}"></script>\n    $1`,
    );
    if (next === html) {
      return result(candidate, "unsupported html");
    }
  }

  if (next === html && !needsShim) return result(candidate, "already patched");
  if (dryRun) return result(candidate, html.includes(codexShimName) ? "would update shim" : "would patch");

  let backupPath = next === html ? null : backup(candidate.target);
  if (next !== html) fs.writeFileSync(candidate.target, next);
  if (needsShim && fs.existsSync(shimFile)) {
    backupPath = backupPath || backup(shimFile);
  }
  fs.writeFileSync(shimFile, shim);
  return result(candidate, html.includes(codexShimName) ? "updated shim" : "patched", backupPath);
}

function restoreCodex(candidate) {
  // Restore only our script tag and shim file. User backups and unrelated
  // extension files are left untouched.
  const html = readText(candidate.target);
  if (html === null) return result(candidate, "missing");
  const hadScript = html.includes(codexShimName);
  const shimFile = codexShimPath(candidate);
  const hadShim = fs.existsSync(shimFile) && (readText(shimFile) || "").includes(marker);
  if (!hadScript && !hadShim) return result(candidate, "not patched");

  const scriptPattern = new RegExp(`\\n?\\s*<script type="module" crossorigin src="\\.\\/${escapeRegExp(codexShimName)}"><\\/script>\\n?`);
  const next = html.replace(scriptPattern, "\n");

  if (dryRun) return result(candidate, "would restore");
  const backupPath = hadScript ? backup(candidate.target) : null;
  if (hadScript) fs.writeFileSync(candidate.target, next);
  if (hadShim) fs.unlinkSync(shimFile);
  return result(candidate, "restored", backupPath);
}

function result(candidate, status, backupPath = null) {
  return { file: candidate.target, status, backup: backupPath };
}

function selectedCandidates() {
  const selected = [];
  for (const root of extensionRoots) {
    for (const spec of specs) {
      const candidates = installedExtensions(root, spec);
      // Default to the latest non-obsolete install per editor root. --all is
      // useful for diagnostics or manually preparing multiple installed builds.
      for (const candidate of patchAll ? candidates : candidates.slice(0, 1)) {
        selected.push({ spec, candidate });
      }
    }
  }
  return selected;
}

function printDetection() {
  let count = 0;
  for (const root of extensionRoots) {
    if (!fs.existsSync(root)) continue;
    for (const spec of specs) {
      const candidates = installedExtensions(root, spec);
      if (candidates.length === 0) continue;
      count += candidates.length;
      for (const candidate of candidates) {
        console.log(`${path.basename(path.dirname(root))} ${spec.label} ${candidate.version}: ${candidate.dir}`);
      }
    }
  }
  if (count === 0) console.log("No installed Claude Code or Codex extensions found.");
}

function patchStatus(spec, candidate) {
  if (spec.kind === "append-js") return isClaudePatched(candidate);
  return isCodexPatched(candidate);
}

if (listOnly) {
  printDetection();
  process.exit(0);
}

const selected = selectedCandidates();
if (selected.length === 0) {
  fail("No installed Claude Code or Codex VS Code/Cursor extensions found.");
}

for (const { spec, candidate } of selected) {
  let operationResult;
  if (statusOnly) {
    operationResult = result(candidate, patchStatus(spec, candidate) ? "patched" : "not patched");
  } else if (restore) {
    operationResult = spec.kind === "append-js" ? restoreClaude(candidate) : restoreCodex(candidate);
  } else {
    operationResult = spec.kind === "append-js" ? patchClaude(candidate) : patchCodex(candidate);
  }

  console.log(
    `${operationResult.status}: ${spec.label} ${candidate.version} ${operationResult.file}` +
      `${operationResult.backup ? ` (backup: ${operationResult.backup})` : ""}`,
  );
}
