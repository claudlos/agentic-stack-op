# Meta-harness — evolving skills under eval

The agentic-stack thesis is "one brain, many harnesses". The meta-harness
thesis is the next step: the brain itself should get better over time, and
you should be able to *measure* that it did.

## The loop

```
on_failure (3+ hits / 14d)
      |
      v
rewrite_flag on latest episode
      |
      v  host agent sees flag in REVIEW_QUEUE / running context
      |
      v
python .agent/tools/evolve.py prepare <skill>
      |
      v  host agent writes skills/<name>/candidate-SKILL.md
      |
      v
python .agent/tools/evolve.py compare <skill> --candidate <path>
      |
      v  if candidate beats current score
      |
      v
python .agent/tools/evolve.py accept <skill> --candidate <path>
      |
      v  previous SKILL.md archived to skills/<name>/_history/
```

The tool **never** writes a rewrite. That stays in the host agent's
jurisdiction, same as `graduate.py` never accepts a lesson without an
explicit rationale. The mechanical parts are mechanical; the reasoning
parts are gated.

## Eval file shape

`skills/<name>/evals/eval.json`

```json
{
  "required_sections": ["## The loop", "## Anti-patterns"],
  "required_frontmatter": ["name", "triggers", "constraints"],
  "forbidden_patterns": ["--no-verify", "rm -rf /"],
  "preserved_constraints": [
    "reproduce before fixing",
    "fix root cause, not symptoms"
  ],
  "trigger_coverage": [
    ["debug", "investigate", "bug"]
  ],
  "failure_references": [
    {"keywords": ["timezone", "tz", "utc"], "min_count": 1}
  ],
  "length_bounds": {"min_chars": 400, "max_chars": 8000}
}
```

## Scoring axes

| Axis | Points | Why it exists |
|---|---|---|
| `required_section` | +10 each | Structural preservation — rewrites that silently drop a section are regressions |
| `required_frontmatter` | +5 each | Keeps the skill loadable by `skill_loader.py` |
| `forbidden_pattern` | -20 each | Explicit "do not reintroduce this" guardrail |
| `preserved_constraint` | +15 ok / -5 missing | The constraints the operator cares most about don't drift across rewrites |
| `trigger_coverage` | +5 per group | Trigger regressions break progressive disclosure |
| `static_failure_ref` | +5 ok / -10 missing | Lessons the reviewer encoded into the eval must keep being addressed |
| `dynamic_failure_coverage` | 0-20 | The **actual** recent failures from `AGENT_LEARNINGS.jsonl` must be referenced in the rewrite, or the rewrite isn't responsive to the flag that triggered it |
| `length` | 0 / -50 / -N per 100 over | Guard against bloat and wishful rewrites |

## Why dynamic failure coverage is the point

Static evals lock in what you knew when you wrote them. Dynamic failure
coverage reads `AGENT_LEARNINGS.jsonl` at score time, extracts keywords
from the *actual* failures of the last 14 days, and requires the rewrite
to mention them. This is what makes the loop self-improving rather than
just self-preserving. A skill flagged for rewrite because of timezone
bugs cannot accept a rewrite that never mentions time.

## Refusing regressions

`evolve.py accept` exits non-zero when the candidate delta is ≤0, unless
`--force` is passed. `--force` writes a loud audit note alongside the
archived previous version so the bypass is visible in `git log` and under
`skills/<name>/_history/`. This is the eval-gate equivalent of
`graduate.py --rationale` for lessons: the human/host judgment is
required AND the record is permanent.

## What this is not

- Not an LLM judge. No inferential sensor, no network, no model call.
  Pure computational scoring per Fowler's harness-engineering frame.
- Not a replacement for human review. The host agent still has to write
  the rewrite and read the score output.
- Not fit for scoring arbitrary prose. The axes are skill-file-shaped
  on purpose.
