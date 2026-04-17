# Writing Skills

The skill is the unit of learned behavior. Good ones compound; bad ones
rot. Rules below keep you honest.

## Anatomy of a skill
```
skills/<name>/
├── SKILL.md            # instructions, YAML frontmatter + body
├── KNOWLEDGE.md        # (optional) accumulated local lessons
├── evals/
│   └── eval.json       # what a rewrite MUST preserve (read by evolve.py)
└── _history/           # (auto) archived versions after accepted rewrites
    ├── SKILL.<ts>.md
    └── SKILL.<ts>.note.md
```

## Frontmatter
```yaml
---
name: deploy-checklist
version: 2026-01-01
triggers: ["deploy", "ship", "release"]
tools: [bash]
preconditions: ["all tests passing"]
constraints: ["requires human approval for production"]
---
```

Every field matters. The manifest generator reads them; the pre-call hook
enforces `constraints`.

## Destinations and fences, not driving directions

**Bad (micromanagement):**
> 1. Run `npm test`. 2. Grep for "passed". 3. Run `git add -A`. 4. ...

**Good (structure):**
> Verify tests pass before committing. Stage specific files (no `-A`).
> Write messages that explain the *why*, not the *what*.

Why: the first form rots when tooling changes. The second form stays true
across refactors.

## Every skill ends with a self-rewrite hook
```markdown
## Self-rewrite hook
After every 5 uses OR on any failure:
1. Read the last N skill-specific episodic entries.
2. If a new failure mode has appeared, append to `KNOWLEDGE.md`.
3. If a constraint was violated, escalate to `semantic/LESSONS.md`.
4. Commit: `skill-update: <name>, <one-line reason>`.
```

## Registering a new skill
1. Add an entry to `skills/_index.md` (human-readable).
2. Append a line to `skills/_manifest.jsonl` (machine-readable).
3. Log the decision in `memory/semantic/DECISIONS.md`.
4. Write `skills/<name>/evals/eval.json` before shipping - see below.

## Evals: what a rewrite must preserve

Every skill ships with an eval file that `.agent/tools/evolve.py` uses to
score candidate rewrites. Without it, a "rewrite" can silently drop a
required section or a safety constraint and nothing notices.

Schema: `skills/_eval.schema.json`. Minimum useful shape:

```json
{
  "$schema": "../../_eval.schema.json",
  "required_sections": ["## The loop", "## Anti-patterns"],
  "required_frontmatter": ["name", "triggers", "constraints"],
  "forbidden_patterns": ["--no-verify", "rm -rf /"],
  "preserved_constraints": ["reproduce before fixing"],
  "trigger_coverage": [["debug", "investigate", "bug"]],
  "length_bounds": {"min_chars": 400, "max_chars": 8000}
}
```

Pick `preserved_constraints` narrowly: the 1-3 things you would be angry
to lose in a rewrite. `forbidden_patterns` is for dangerous substrings
that must never reappear. Dynamic failure keywords from
`AGENT_LEARNINGS.jsonl` are layered on top automatically - you don't
enumerate them, they come from real failures in the last 14 days.

`python .agent/tools/evolve.py score <name>` prints each axis and the
total. Negative axes in your new skill mean the eval disagrees with what
you wrote - fix one or the other before shipping.

## Anti-patterns
- Skills that duplicate each other's triggers (progressive disclosure breaks).
- Skills with procedural step-by-step commands (bitter lesson — the model
  gets better, your scripts don't).
- Skills that modify `protocols/permissions.md` (only humans edit that file).
