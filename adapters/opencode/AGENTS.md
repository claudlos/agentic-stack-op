# AGENTS.md — OpenCode adapter for agentic-stack

OpenCode natively reads `AGENTS.md` from the project root. This file points
it at the portable brain in `.agent/`.

## Before any action
1. Read `.agent/AGENTS.md` (the map).
2. Read `.agent/memory/personal/PREFERENCES.md`.
3. Read `.agent/memory/semantic/LESSONS.md`.
4. Read `.agent/protocols/permissions.md` (rendered from `permissions.json`).

## Skills
- Use `.agent/skills/_index.md` for discovery.
- Load `.agent/skills/<name>/SKILL.md` only when the skill's triggers match.

## Memory
- Update `.agent/memory/working/WORKSPACE.md` as you work.
- After significant actions, run
  `python .agent/tools/memory_reflect.py --skill <s> --action <a> --outcome <o> --harness opencode --tool <name>`.
- Never delete memory entries. Archive only.

## Constraints
- Never force push to `main`, `production`, or `staging`.
- Never modify `.agent/protocols/permissions.json` or `permissions.md`.
