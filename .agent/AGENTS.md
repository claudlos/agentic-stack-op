# Agent Infrastructure

This folder is the portable brain. Any harness (Claude Code, Cursor, Windsurf,
OpenCode, OpenClient, Hermes, standalone Python) can mount it and get the
same memory, skills, and protocols.

## Memory (read in this order)
- `memory/personal/PREFERENCES.md` - stable user conventions
- `memory/working/WORKSPACE.md` - current task state
- `memory/working/REVIEW_QUEUE.md` - pending candidate lessons AND skills
  flagged for rewrite (see Evolve loop below)
- `memory/working/COVERAGE.md` - guide/sensor %, harness mix, dead skills
  (auto-refreshed by auto_dream.py - see `docs/meta-harness.md`)
- `memory/semantic/DECISIONS.md` - past architectural choices
- `memory/semantic/LESSONS.md` - distilled patterns (rendered from `lessons.jsonl`)
- `memory/episodic/AGENT_LEARNINGS.jsonl` - raw experience log with
  structured trace fields (tool, tool_args, tool_output, duration_ms,
  exit_code, source.harness, source.model)

## Review Queue (host-agent responsibility)

Candidate lessons are clustered + staged automatically by `memory/auto_dream.py`.
The host agent — you — does the actual review using the CLI tools below.

Check `memory/working/REVIEW_QUEUE.md` at session start. If pending > 10 or
oldest staged > 7 days, review before substantive work.

Workflow:
1. `python .agent/tools/list_candidates.py` — pending candidates, sorted by priority
2. For each: decide accept / reject / defer based on claim, evidence_ids,
   cluster_size, and any contradictions with existing LESSONS.md
3. `python .agent/tools/graduate.py <id> --rationale "..."` to accept
4. `python .agent/tools/reject.py <id> --reason "..."` to reject
5. `python .agent/tools/reopen.py <id>` to requeue a previously-rejected item
6. Review in a **batch**, not one-by-one — cross-candidate contradictions
   only surface when you see multiple at once.

The heuristic prefilter in `memory/validate.py` has already dropped obvious
junk (too-short claims, exact duplicates). Everything staged needs real
judgment. Rationale is required for graduation — rubber-stamped promotions
are the exact failure mode this layer prevents.

## Skills
- `skills/_index.md` - read first for discovery
- `skills/_manifest.jsonl` - machine-readable skill metadata
- `skills/<name>/evals/eval.json` - what a rewrite MUST preserve (scored
  by `tools/evolve.py`). See `docs/meta-harness.md`.
- Load a full `SKILL.md` only when its triggers match the current task
- Every skill has a self-rewrite hook; invoke it after failures

## Evolve loop (rewrite-flagged skills)

When REVIEW_QUEUE.md lists skills under "Skills flagged for rewrite":
1. `python .agent/tools/evolve.py prepare <skill>` - get the rewrite brief
   (current SKILL.md + recent failure episodes + dynamic failure keywords).
2. Write your rewrite to `skills/<skill>/candidate-SKILL.md`.
3. `python .agent/tools/evolve.py compare <skill> --candidate <path>` -
   side-by-side scoring across all axes.
4. `python .agent/tools/evolve.py accept <skill> --candidate <path>` -
   refuses regressions; archives the previous version to `_history/`.

The score is deterministic. No LLM in the loop. Full details in
`docs/meta-harness.md`.

## Protocols
- `protocols/permissions.json` - **source of truth** for deny/approval.
- `protocols/permissions.md` - rendered view; read before any tool call.
- `protocols/permissions.schema.json` - shape validation (CI gate).
- `protocols/tool_schemas/` - typed interfaces for external tools
- `protocols/delegation.md` - rules for sub-agent handoff

## Tools index (.agent/tools/)
- `memory_reflect.py` - log an episodic entry (positional, flag, or
  `--stdin` JSON for hook integration).
- `list_candidates.py` / `graduate.py` / `reject.py` / `reopen.py` -
  review queue CLI. Graduation requires `--rationale`.
- `evolve.py` - score/compare/prepare/accept for skill rewrites.
- `coverage.py` - harness-coverage metric -> `memory/working/COVERAGE.md`.
- `hermes_sync.py` - mirror accepted lessons into Hermes's MEMORY.md /
  USER.md between HTML sentinels. Idempotent.
- `permissions_render.py` - regenerate permissions.md + deny artefacts
  from permissions.json. `--check` is the CI drift guard.
- `render_claude_settings.py` - merge permissions.json deny patterns
  into a target `.claude/settings.json` at install time.
- `validate_schemas.py` - stdlib validator for permissions.json + every
  skill eval.json. CI gate.
- `skill_loader.py` - trigger-matched progressive skill loading.

## Rules
1. Check memory before decisions you have been corrected on before.
2. If `REVIEW_QUEUE.md` shows backlog past threshold OR any skill
   flagged for rewrite, handle it before the new task.
3. Log every significant action to `memory/episodic/AGENT_LEARNINGS.jsonl`
   via `.agent/tools/memory_reflect.py`. Pass `--tool` / `--tool-args` /
   `--exit-code` when available so the trace is replayable by evolve.py.
4. Update `memory/working/WORKSPACE.md` as you work; archive on completion.
5. Never hand-edit `memory/semantic/LESSONS.md` - it's rendered from
   `lessons.jsonl`. Use `graduate.py` / `reject.py` instead.
6. Follow `protocols/permissions.json` (rendered to `permissions.md`).
   Blocked means blocked. Never hand-edit the rendered markdown.
7. When a self-rewrite hook fires, run the evolve loop above. Score
   must not regress.
8. The harness is dumb on purpose. Reasoning lives in skills + the host
   agent. `evolve.py` scores; it does not write rewrites.
