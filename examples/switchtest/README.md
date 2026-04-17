# switchtest - one brain, many harnesses, actually tested

The agentic-stack thesis is that you can switch harnesses (Claude Code,
Cursor, Windsurf, OpenCode, OpenClient, Hermes, standalone Python) without
losing your memory. This directory turns that thesis into a test.

## What it checks

1. **Install parity.** Installing each adapter into a fresh target leaves
   `.agent/` byte-identical across adapters. Only the adapter-specific
   overlay (CLAUDE.md vs AGENTS.md vs .windsurfrules etc.) differs.

2. **Trace parity.** Feeding the same synthetic tool-call through
   `memory_reflect.py` with different `--harness` values produces entries
   that are structurally identical except for the `source.harness` field.

3. **Clustering parity.** A pattern discovered across two harnesses ends
   up with both harness labels in `pattern.harnesses`, so the host agent
   can see it's cross-harness evidence, not single-harness noise.

4. **Permissions parity.** The deny rules in `protocols/permissions.json`
   produce the same `(allowed, reason)` verdicts whether loaded via the
   JSON path or (fallback) the markdown path.

Failure of any of these is a failure of the portability claim. That's the
point - the test has teeth only if it can fail.

## Run it

From the repo root:

```bash
python examples/switchtest/run_switchtest.py
```

Exit 0 = all four checks pass. Exit 1 = at least one regressed; the output
names which.

## Why no LLM call

This is an *equivalence* test, not an agent-behavior test. Agent behavior
is model-dependent and flaky; the brain's byte-level and trace-level
invariants are not. For LLM-in-the-loop testing see the (future)
`examples/switchtest/live/` suite.
