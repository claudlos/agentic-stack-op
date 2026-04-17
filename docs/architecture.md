# Architecture

Three modules, one principle: the harness is dumb, the knowledge is in files.
The meta-harness layer added in v0.6.0 makes the knowledge itself measurable.

## Modules

### Memory - four layers
- **working/** - live task state. Volatile. Archived after 2 days. Also
  holds `REVIEW_QUEUE.md` (pending candidates + rewrite-flagged skills)
  and `COVERAGE.md` (guide/sensor metrics, harness mix, dead skills).
- **episodic/** - what happened in prior runs. JSONL, scored by salience.
  Entries carry structured trace fields (`tool`, `tool_args`,
  `tool_output`, `duration_ms`, `exit_code`) plus provenance
  (`source.harness`, `source.model`, `source.run_id`, `source.commit_sha`).
- **semantic/** - distilled patterns that outlive episodes. `lessons.jsonl`
  is the source of truth; `LESSONS.md` is rendered from it.
- **personal/** - user-specific preferences. Never merged into semantic.

### Skills - progressive disclosure
- `_index.md` and `_manifest.jsonl` always in context (tiny).
- A full `SKILL.md` loads only when its triggers match the current task.
- Every skill has a self-rewrite hook at the bottom.
- `skills/<name>/evals/eval.json` declares what a rewrite must preserve
  so `tools/evolve.py` can score candidate rewrites deterministically.
- `skills/<name>/_history/` holds archived versions after accepted rewrites.

### Protocols - contracts with external systems
- `permissions.json` - **source of truth** for deny/approval policy.
- `permissions.md` - rendered view for agent context (auto-generated).
- `.claude-deny.json` - rendered deny patterns for adapter installers.
- `permissions.schema.json` - JSON Schema catching typos in the source.
- `tool_schemas/` - typed interfaces for every external tool.
- `delegation.md` - rules for sub-agent handoff.

### Host-agent tools (.agent/tools/)
- `memory_reflect.py` - write an episodic entry (positional, flag, or
  Claude-Code-style `--stdin` JSON payload).
- `list_candidates.py` / `graduate.py` / `reject.py` / `reopen.py` -
  the review-queue CLI.
- `evolve.py` - score skills against eval + live failure history;
  refuses rewrite regressions. See `meta-harness.md`.
- `coverage.py` - guide %, sensor %, harness mix, dead skills, rewrite
  flagged list. Runs inside auto_dream.
- `permissions_render.py` - regenerate permissions.md + deny JSON from
  the source; `--check` fails on drift (used by CI).
- `render_claude_settings.py` - installer-side merge of permission
  policy into a target `.claude/settings.json`.
- `hermes_sync.py` - sentinel-guarded mirror into Hermes's `MEMORY.md` /
  `USER.md`. Never touches `state.db`.
- `validate_schemas.py` - stdlib JSON-shape validator for
  permissions.json and every skill eval.json (CI gate).
- `skill_loader.py` - trigger-matched progressive skill loading.

## The feedback loops

1. Skills log to episodic memory after every action (structured trace).
2. `memory_reflect.py` enriches entries with harness/model/tool
   provenance via `_provenance.py`.
3. `auto_dream.py` (nightly) clusters recurring patterns into candidates,
   stages them, then refreshes `REVIEW_QUEUE.md` and `COVERAGE.md`.
4. Host agent reviews candidates via `graduate.py --rationale` /
   `reject.py --reason`. Graduated lessons append to `lessons.jsonl`;
   `LESSONS.md` re-renders.
5. `on_failure.py` flags skills for rewrite after 3+ failures in 14d.
   The flag reaches the host agent via `REVIEW_QUEUE.md` and
   `COVERAGE.md`.
6. `evolve.py prepare <skill>` emits a rewrite brief. The host writes a
   candidate file. `evolve.py compare` scores it. `evolve.py accept`
   refuses regressions and archives the previous version.
7. Constraint violations inside a skill escalate from local
   `KNOWLEDGE.md` to global `LESSONS.md`.

## Guarantees

- **Harness-agnostic brain.** `examples/switchtest/run_switchtest.py`
  asserts every adapter receives a byte-identical `.agent/` tree and
  that the same trace differs only in `source.harness` across labels.
- **No unattended reasoning.** `auto_dream.py` and `coverage.py` are
  mechanical. `evolve.py` scores but never writes rewrites. Every
  graduation requires a `--rationale`; every rewrite acceptance requires
  a non-regressing score or `--force` (which logs a loud audit note).
- **Single source of truth.** Permission policy lives in
  `permissions.json`. Installer renders the Claude Code deny list from
  it at install time. CI fails on drift.

## Why the separation matters

You can swap the harness for any of the seven adapters and lose nothing.
The brain is portable; only the glue changes. See `adapter-parity.md`
for feature-by-harness status, `meta-harness.md` for the evolve loop.

See `diagram.svg` for a visual.
