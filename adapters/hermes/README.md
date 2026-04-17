# Hermes Agent adapter

[Hermes Agent](https://github.com/nousresearch/hermes-agent) by Nous
Research is an open-source agent with its own persistent memory layer
and agentskills.io-compatible skill support. Our adapter layers the
portable `.agent/` brain on top so you keep one knowledge base even if
you later swap harnesses.

## Install
```bash
cp adapters/hermes/AGENTS.md ./AGENTS.md
```

Or:
```bash
./install.sh hermes
```

## What it wires up
- `AGENTS.md` - Hermes reads this natively as workspace-level context;
  we point it at `.agent/`.
- Skills in `.agent/skills/` use the same frontmatter-plus-body shape
  Hermes expects. Browse via `/skills` in the Hermes CLI.
- `tools/hermes_sync.py` - idempotent bridge that mirrors accepted
  lessons + preferences into Hermes's own MEMORY.md / USER.md. Uses
  HTML sentinels so re-runs replace only the managed section.

## Bridge into Hermes's own memory
```bash
# set AGENT_HARNESS so provenance is tagged correctly
export AGENT_HARNESS=hermes

# mirror graduated lessons + preferences into Hermes files
python .agent/tools/hermes_sync.py plan    # dry run
python .agent/tools/hermes_sync.py apply   # write

# override the target with HERMES_HOME or --hermes-root
HERMES_HOME=/path/to/alt-hermes python .agent/tools/hermes_sync.py apply
```

The bridge never touches `state.db` - Hermes's SQLite schema is a moving
target across versions and accidentally corrupting it could wipe an
in-flight session. File-level mirroring only.

Run the bridge after every `.agent/tools/graduate.py` so Hermes-native
tooling sees the same lessons the review queue just accepted. A cron or
post-commit hook on `.agent/memory/semantic/lessons.jsonl` keeps it
hands-off.

## Verify
In Hermes: "What's in my LESSONS file?" - it should read
`.agent/memory/semantic/LESSONS.md`.
Then: "What's in MEMORY.md?" - it should show the synced section
bracketed by the `BEGIN agentic-stack managed` sentinel.
