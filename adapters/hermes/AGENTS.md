# AGENTS.md — Hermes Agent adapter for agentic-stack

Hermes Agent (Nous Research) reads `AGENTS.md` as workspace-level context.
This file points it at the portable brain in `.agent/`.

## Startup (read in order)
1. `.agent/AGENTS.md` - the map
2. `.agent/memory/personal/PREFERENCES.md` - user conventions
3. `.agent/memory/semantic/LESSONS.md` - distilled lessons
4. `.agent/protocols/permissions.md` - hard rules (rendered from permissions.json)

## Skills
Hermes supports the agentskills.io standard. Our skills under
`.agent/skills/<name>/SKILL.md` follow the same frontmatter-plus-body
shape. Use `/skills` in Hermes to browse them; load `SKILL.md` only
when triggers match the current task (progressive disclosure).

## Memory discipline
- Update `.agent/memory/working/WORKSPACE.md` as you work.
- After significant actions, run
  `python .agent/tools/memory_reflect.py --skill <name> --action <a> --outcome <o>`
  (add `--harness hermes` if `AGENT_HARNESS` isn't set in your shell).
- Never delete memory entries; archive only.

## Bridging into Hermes's own memory layer
Hermes has its own `MEMORY.md` / `USER.md` / `SOUL.md` + a SQLite `state.db`.
Run the bridge to mirror graduated lessons and preferences into Hermes's
files (idempotent, sentinel-guarded, never touches `state.db`):

```bash
python .agent/tools/hermes_sync.py plan          # dry run
python .agent/tools/hermes_sync.py apply         # write
# override the target with HERMES_HOME or --hermes-root PATH
```

Run this after every `graduate.py` so Hermes-native tools see the same
lessons the agentic-stack review queue just accepted.

## Harness provenance
Export `AGENT_HARNESS=hermes` in the shell Hermes runs under so entries
logged via `memory_reflect.py` get tagged correctly. This lets cluster
analysis surface Hermes-specific failure patterns vs. cross-harness ones.

## Hard rules
- No force push to `main`, `production`, `staging`.
- No modification of `.agent/protocols/permissions.json` or `permissions.md`.
