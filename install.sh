#!/usr/bin/env bash
# install.sh - copy an adapter into the consuming project, then run the onboarding wizard
# Usage: ./install.sh <adapter-name> [target-dir] [--new-project NAME] [--yes] [--reconfigure]
#   adapter-name:       claude-code | cursor | windsurf | opencode | openclient | hermes | standalone-python
#   target-dir:         where your project lives (default: current dir)
#   --new-project NAME  create a fresh dir NAME, git init it, write a starter
#                       .gitignore + README, then install into it. Shortcut
#                       for "I just want to start something from zero."
#   --yes               accept all wizard defaults without prompting (safe for CI)
#   --reconfigure       re-run the wizard even if PREFERENCES.md is already filled
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

# ── Flag parsing ──────────────────────────────────────────────────────────
# Pull --new-project NAME out of $@ before we compute positional args, because
# it changes what "target dir" means (spawns one rather than using an existing
# one). Leaves the other flags for the wizard layer downstream.
ADAPTER=""
NEW_PROJECT=""
POSITIONAL=()
WIZARD_FLAGS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --new-project)
      NEW_PROJECT="${2:-}"
      if [[ -z "$NEW_PROJECT" ]]; then
        echo "error: --new-project needs a name" >&2
        exit 2
      fi
      shift 2
      ;;
    --new-project=*)
      NEW_PROJECT="${1#--new-project=}"
      shift
      ;;
    --yes|-y)        WIZARD_FLAGS="$WIZARD_FLAGS --yes";        shift ;;
    --reconfigure)   WIZARD_FLAGS="$WIZARD_FLAGS --reconfigure"; shift ;;
    --force)         WIZARD_FLAGS="$WIZARD_FLAGS --force";       shift ;;
    --help|-h)
      sed -n '2,11p' "$0" | sed 's/^# //'
      exit 0
      ;;
    --*|-*)
      echo "warning: unknown flag $1 (passing through to wizard)" >&2
      shift
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
ADAPTER="${POSITIONAL[0]:-}"
# TARGET defaults: PWD, or the spawned --new-project dir (resolved below).
TARGET_POS="${POSITIONAL[1]:-}"

if [[ -z "$ADAPTER" ]]; then
  echo "usage: $0 <adapter-name> [target-dir] [--new-project NAME]" >&2
  echo "adapters: claude-code cursor windsurf opencode openclient hermes standalone-python" >&2
  exit 2
fi

SRC="$HERE/adapters/$ADAPTER"
if [[ ! -d "$SRC" ]]; then
  echo "error: adapter '$ADAPTER' not found at $SRC" >&2
  exit 1
fi

# ── --new-project bootstrap ────────────────────────────────────────────────
# If the user asked for a spawn, create the dir, git init it, and seed the
# most basic files a human + Claude would expect to find when they open it.
# We do this BEFORE the adapter copy so the rest of the script sees a normal
# target dir and doesn't need to care how it was born.
if [[ -n "$NEW_PROJECT" ]]; then
  # Resolve relative names against PWD so `install.sh claude-code --new-project foo`
  # lands `foo/` next to where you called from, not next to install.sh.
  if [[ "$NEW_PROJECT" = /* ]] || [[ "$NEW_PROJECT" =~ ^[A-Za-z]: ]]; then
    TARGET="$NEW_PROJECT"
  else
    TARGET="$PWD/$NEW_PROJECT"
  fi

  if [[ -n "$TARGET_POS" ]]; then
    echo "warning: ignoring positional target-dir '$TARGET_POS' because --new-project was given" >&2
  fi

  # Refuse to overwrite a non-empty directory - the whole point of
  # --new-project is "I'm starting from zero." If someone meant to retarget
  # an existing dir they should drop --new-project.
  if [[ -e "$TARGET" ]] && [[ -n "$(ls -A "$TARGET" 2>/dev/null || true)" ]]; then
    echo "error: $TARGET already exists and is non-empty; refusing to bootstrap over it" >&2
    echo "       drop --new-project and pass the path as target-dir if that's what you want" >&2
    exit 1
  fi

  mkdir -p "$TARGET"

  # git init quietly so the output stays clean; swallow failure if git is
  # absent (rare but possible on minimal CI containers).
  if command -v git >/dev/null 2>&1; then
    git -C "$TARGET" init -q
    echo "  + git init"
  else
    echo "  - git not on PATH; skipping git init" >&2
  fi

  # Minimal .gitignore - just the stuff that shouldn't land in any project,
  # agnostic of language. Project-specific ignores are the user's job.
  if [[ ! -f "$TARGET/.gitignore" ]]; then
    cat > "$TARGET/.gitignore" <<'GITIGNORE'
# env / secrets
.env
.env.local
*.key

# python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/

# editor
.DS_Store
.idea/
.vscode/
*.swp

# runtime logs (auto_dream writes here)
.agent/memory/dream.log
*.log

# keep the brain, ignore generated artefacts inside it
.agent/memory/.index/
.agent/memory/.index/**
.agent/memory/working/REVIEW_QUEUE.md
.agent/memory/working/COVERAGE.md
.agent/memory/working/coverage.json
.agent/**/__pycache__/
.agent/**/*.py[cod]
GITIGNORE
    echo "  + .gitignore"
  fi

  # Starter README so `git status` after install isn't a wall of unexplained
  # files. Mentions agentic-stack-op so anyone who clones the project later
  # knows where the .agent/ dir came from.
  if [[ ! -f "$TARGET/README.md" ]]; then
    cat > "$TARGET/README.md" <<README
# $(basename "$TARGET")

Bootstrapped with [agentic-stack-op](https://github.com/claudlos/agentic-stack-op)
using the \`$ADAPTER\` adapter.

The portable brain is in \`.agent/\`. Your AI harness reads it at the start of
every session.

## Next steps

- Edit \`.agent/memory/personal/PREFERENCES.md\` to describe how you work
  (the onboarding wizard just populated it with defaults).
- Run your AI harness in this directory; it will read \`.agent/AGENTS.md\`
  on startup and follow the protocol there.
- Nightly: \`python .agent/memory/auto_dream.py\` to stage candidate
  lessons and refresh the review queue.
README
    echo "  + README.md"
  fi
elif [[ -n "$TARGET_POS" ]]; then
  TARGET="$TARGET_POS"
else
  TARGET="$PWD"
fi

echo "installing '$ADAPTER' into $TARGET"

# Copy .agent/ brain only if the target does not already have one
if [[ ! -d "$TARGET/.agent" ]]; then
  cp -R "$HERE/.agent" "$TARGET/.agent"
  echo "  + .agent/ (portable brain)"
fi

# Pick the python binary the hooks will actually use on this box. We don't
# just trust `command -v` - on Windows under git-bash, `python3` resolves to
# the Microsoft Store app-execution alias, which exists as a stub but prints
# "Python was not found" when invoked. Probe with --version so a non-working
# stub doesn't get baked into settings.json.
_check_py() {
  command -v "$1" >/dev/null 2>&1 && "$1" --version >/dev/null 2>&1
}
if _check_py python3; then
  PY_BIN="python3"
elif _check_py python; then
  PY_BIN="python"
else
  PY_BIN="python3"
  echo "warning: no working python interpreter on PATH; hooks will fail until you install one." >&2
fi

case "$ADAPTER" in
  claude-code)
    cp "$SRC/CLAUDE.md" "$TARGET/CLAUDE.md"
    mkdir -p "$TARGET/.claude"
    cp "$SRC/settings.json" "$TARGET/.claude/settings.json"
    # Substitute the detected python binary into hook commands. sed on
    # BSD/mac requires an explicit empty suffix for -i; pass -e so both
    # GNU and BSD take the same invocation.
    sed -i.bak -e "s|\"command\": \"python |\"command\": \"$PY_BIN |g" \
      "$TARGET/.claude/settings.json"
    rm -f "$TARGET/.claude/settings.json.bak"
    # Render permissions.json deny patterns into settings.json so the
    # Claude Code permission engine and the pre_tool_call hook read the
    # same source of truth. Silent failure is acceptable here - the hook
    # still enforces JSON policy even if the UI block list is stale.
    if [ -f "$TARGET/.agent/protocols/permissions.json" ]; then
      "$PY_BIN" "$TARGET/.agent/tools/render_claude_settings.py" \
        "$TARGET/.claude/settings.json" \
        "$TARGET/.agent/protocols/permissions.json" >/dev/null || \
        echo "warning: failed to merge permissions into settings.json" >&2
    fi
    ;;
  cursor)
    mkdir -p "$TARGET/.cursor/rules"
    cp "$SRC/.cursor/rules/agentic-stack.mdc" "$TARGET/.cursor/rules/agentic-stack.mdc"
    ;;
  windsurf)
    cp "$SRC/.windsurfrules" "$TARGET/.windsurfrules"
    ;;
  opencode)
    cp "$SRC/AGENTS.md" "$TARGET/AGENTS.md"
    cp "$SRC/opencode.json" "$TARGET/opencode.json"
    ;;
  openclient)
    cp "$SRC/config.md" "$TARGET/.openclient-system.md"
    ;;
  hermes)
    cp "$SRC/AGENTS.md" "$TARGET/AGENTS.md"
    ;;
  standalone-python)
    cp "$SRC/run.py" "$TARGET/run.py"
    ;;
  *)
    echo "error: unknown adapter '$ADAPTER'" >&2
    exit 1
    ;;
esac

echo "done."

# ── Onboarding wizard ──────────────────────────────────────────────────────
ONBOARD_PY="$HERE/onboard.py"
if [[ ! -f "$ONBOARD_PY" ]]; then
  echo "tip: customize $TARGET/$( echo '.agent/memory/personal/PREFERENCES.md' ) with your conventions."
  exit 0
fi
if ! _check_py "$PY_BIN"; then
  echo "tip: no working python interpreter - edit .agent/memory/personal/PREFERENCES.md manually."
  exit 0
fi

# exec replaces this shell; no return needed
exec "$PY_BIN" "$ONBOARD_PY" "$TARGET" $WIZARD_FLAGS
