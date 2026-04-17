# Adapter parity matrix

What each adapter actually wires up, not what the philosophy promises. The
headline "one brain, many harnesses" only holds if each harness can read
and write the same brain; this table tracks where we are vs. where we're
going.

## Legend

- **yes** - first-class, wired by the installer.
- **manual** - supported but requires operator action (export an env var,
  run a command periodically, etc.).
- **no** - not supported yet. PRs welcome.
- **n/a** - doesn't apply to this harness.

## Feature matrix

| Feature | Claude Code | Cursor | Windsurf | OpenCode | OpenClient | Hermes | Standalone Python |
|---|---|---|---|---|---|---|---|
| Reads `.agent/AGENTS.md` on startup | yes | yes | yes | yes | yes | yes | yes |
| Progressive skill loading | yes | yes | yes | yes | yes | yes | yes |
| **Pre-tool-call permission gate** | yes (settings.json deny) | no | no | yes (opencode.json) | no | no | yes (hook) |
| **Post-tool-use memory hook** | yes (PostToolUse) | manual | manual | no | no | manual | yes (hook) |
| Dream cycle on session end | yes (Stop hook) | manual | manual | manual | manual | manual | yes |
| Permission denies from `permissions.json` | yes (rendered) | n/a | n/a | partial (hand-edit) | n/a | n/a | yes |
| **Harness provenance auto-detected** | yes (CLAUDECODE=1) | manual (export CURSOR) | manual (export WINDSURF) | manual (export OPENCODE) | manual | manual (export HERMES_SESSION_ID) | yes (env or default) |
| Structured trace fields in episodic | yes (--stdin) | manual (--tool flags) | manual (--tool flags) | manual | manual | manual | yes |
| **Bridge into harness-native memory** | n/a | n/a | n/a | n/a | n/a | yes (hermes_sync.py) | n/a |
| Windows-native installer | yes | yes | yes | yes | yes | yes | yes |

## The "manual" gap

Cursor, Windsurf, OpenClient, and (for post-tool hooks) Hermes don't
expose a pre/post-tool-call hook API as of 2026-04. The agent still runs;
it just can't auto-log every action. Two workarounds:

1. **Trigger-based logging.** Have the agent itself call
   `memory_reflect.py` at the end of each skill invocation. Works because
   progressive skill loading puts the command in front of the model.

2. **Watcher daemon.** For harnesses that write chat transcripts (Cursor
   writes to `.cursor/composer-sessions/`), a small watcher can tail the
   file and synthesize episodic entries. Out of scope for now but well-
   defined.

## Provenance export one-liners

Drop these in your shell profile once so the auto-detect in
`.agent/harness/hooks/_provenance.py` tags every episode correctly:

```bash
# Cursor
export AGENT_HARNESS=cursor CURSOR=1

# Windsurf
export AGENT_HARNESS=windsurf WINDSURF=1

# Hermes
export AGENT_HARNESS=hermes

# OpenCode
export AGENT_HARNESS=opencode OPENCODE=1

# OpenClient
export AGENT_HARNESS=openclient OPENCLIENT=1
```

Claude Code and the standalone Python conductor set `AGENT_HARNESS`
automatically.

## What we'd need to reach full parity

- Cursor/Windsurf hook API (upstream, not our call).
- An OpenCode post-tool hook spec (their config supports `permissions`
  today but no execution hook).
- Hermes pre/post-tool hook registration (they have a plugin system
  under development; the bridge anticipates it).

Until those land, the matrix is honest about what `brew install
agentic-stack` actually buys you per harness.
