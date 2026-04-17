# Recipes

Five concrete workflows with the exact commands. If your situation doesn't
fit one of these, the README Quickstart is the general case.

---

## 1. Brand-new project, Claude Code, from zero

You have no project yet. You want a ready-to-code directory with git, the
brain installed, Claude Code hooks wired up, and a sensible `.gitignore`.

```bash
git clone https://github.com/claudlos/agentic-stack-op.git ~/src/agentic-stack-op
cd /path/where/your/projects/live

~/src/agentic-stack-op/install.sh claude-code \
  --new-project my-api \
  --yes

cd my-api
# start Claude Code here; it reads CLAUDE.md + .agent/ on startup
```

What just happened:

- `my-api/` was created (refuses if non-empty).
- `git init`, starter `.gitignore`, starter `README.md`.
- `.agent/` (the portable brain) copied in.
- `CLAUDE.md` + `.claude/settings.json` copied in, python binary probed,
  deny patterns from `permissions.json` merged into the settings.
- Onboarding wizard ran with `--yes`, writing default
  `.agent/memory/personal/PREFERENCES.md`.

Open the project in your editor, edit `PREFERENCES.md` to your taste,
and start typing.

Windows equivalent (PowerShell):

```powershell
cd C:\path\where\your\projects\live
C:\src\agentic-stack-op\install.ps1 claude-code -NewProject my-api -Yes
cd my-api
```

---

## 2. Add the brain to an existing repo

You already have a project at `~/src/my-service`. You want to retrofit it
with the brain without changing anything else.

```bash
cd ~/src/agentic-stack-op
./install.sh claude-code ~/src/my-service
# or: cursor | windsurf | opencode | openclient | hermes | standalone-python
```

The installer:

- **Does not** `git init` - your repo already has history.
- Copies `.agent/` only if it's absent (so re-running is safe).
- Copies the adapter overlay (CLAUDE.md, .cursor/rules/, etc).
- Runs the onboarding wizard interactively (drop `--yes` for defaults).

Commit the new files:

```bash
cd ~/src/my-service
git add .agent/ CLAUDE.md .claude/
git commit -m "chore: install agentic-stack-op brain (claude-code adapter)"
```

If your repo already had an `AGENTS.md` (from upstream agentic-stack or
another tool), the installer will overwrite the adapter-rendered one.
`git diff` shows what changed; revert if you want to keep your version
and re-target manually.

---

## 3. Claude Code + Hermes sharing one brain

You use Claude Code most days but want Hermes to see the same lessons.
Install both adapters against the same project and bridge into Hermes's
native memory layer.

```bash
cd ~/src/my-project

# primary adapter (gives you hooks, deny-list enforcement, the dream cycle)
~/src/agentic-stack-op/install.sh claude-code $(pwd) --yes

# add the Hermes pointer (drops an AGENTS.md alongside CLAUDE.md;
# Hermes reads AGENTS.md, Claude Code reads CLAUDE.md - no conflict)
~/src/agentic-stack-op/install.sh hermes $(pwd) --yes

# tag Hermes sessions so provenance is correct
export AGENT_HARNESS=hermes  # put this in your shell profile

# mirror graduated lessons into Hermes's own MEMORY.md / USER.md
python .agent/tools/hermes_sync.py plan    # dry run
python .agent/tools/hermes_sync.py apply
```

After the bridge runs, Hermes sees your lessons in its native
`~/.hermes/MEMORY.md` between `BEGIN/END agentic-stack managed`
sentinels. Re-running `hermes_sync.py apply` replaces that block
without touching anything above/below it or the SQLite `state.db`.

Run it after every `graduate.py` acceptance, or via cron:

```bash
0 4 * * * cd ~/src/my-project && python .agent/tools/hermes_sync.py apply
```

---

## 4. Migrate from upstream `codejunkie99/agentic-stack` v0.5.0

You already have the upstream v0.5.0 installed (via brew or a clone) and
want the meta-harness layer without losing your memory.

```bash
# back up the existing .agent/ - it has your graduated lessons, episodic log,
# preferences. Migration preserves everything but you want a rollback option.
cd ~/src/my-project
cp -R .agent .agent.bak

# pull this fork and re-install. The installer skips .agent/ when it
# already exists, so your lessons/memory/preferences survive untouched.
git clone https://github.com/claudlos/agentic-stack-op.git ~/src/agentic-stack-op
~/src/agentic-stack-op/install.sh claude-code $(pwd) --reconfigure

# but the NEW files (evolve.py, coverage.py, permissions.json, evals/, etc.)
# live under .agent/ too and were skipped because .agent/ already existed.
# Copy them in without touching your memory dirs:
rsync -a --update \
  ~/src/agentic-stack-op/.agent/tools/ \
  .agent/tools/
rsync -a --update \
  ~/src/agentic-stack-op/.agent/protocols/ \
  .agent/protocols/
rsync -a --update \
  ~/src/agentic-stack-op/.agent/skills/ \
  .agent/skills/
# cluster.py / promote.py / review_state.py / auto_dream.py etc. grew new
# features in v0.6.0 - update them too. The JSONL episodic format is
# backward-compat, so old entries keep working.
rsync -a --update \
  ~/src/agentic-stack-op/.agent/memory/*.py \
  .agent/memory/
rsync -a --update \
  ~/src/agentic-stack-op/.agent/harness/ \
  .agent/harness/

# regenerate permission artefacts from the new permissions.json
python .agent/tools/permissions_render.py

# sanity check
python .agent/tools/validate_schemas.py
python .agent/tools/coverage.py  # should populate COVERAGE.md
```

Your lessons, episodic log, and preferences are untouched. The new tools
(evolve, coverage, hermes_sync, validate_schemas) are now available.

To verify nothing broke:

```bash
python ~/src/agentic-stack-op/examples/switchtest/run_switchtest.py
```

If the 5 checks pass against your upgraded `.agent/`, migration worked.

---

## 5. Unattended dream cycle + daily review

The dream cycle is designed to run nightly without a human. The human
review happens in-session the next morning.

```bash
# add to crontab
crontab -e

# at 3am, cluster new episodic entries, stage candidates, refresh
# REVIEW_QUEUE.md + COVERAGE.md; log to a file for diagnostics
0 3 * * * cd /path/to/my-project && python .agent/memory/auto_dream.py >> .agent/memory/dream.log 2>&1
```

The next morning, when you start Claude Code:

1. Your harness reads `CLAUDE.md`, which points at `.agent/AGENTS.md`.
2. `context_budget.py` loads `memory/working/REVIEW_QUEUE.md` into the
   session - Claude sees pending candidates + any skills flagged for
   rewrite.
3. If the queue has >10 pending or the oldest is >7 days old,
   `.agent/AGENTS.md` tells Claude to review before substantive work.

Your daily workflow:

```
$ claude
# Claude notices 3 pending candidates in REVIEW_QUEUE.md and suggests review
You: ok, list them
# Claude runs: python .agent/tools/list_candidates.py
# ...deliberates per candidate...
You: graduate the first, reject the second, reopen the third
# Claude runs:
#   python .agent/tools/graduate.py <id1> --rationale "..."
#   python .agent/tools/reject.py    <id2> --reason    "..."
#   python .agent/tools/reopen.py    <id3>
```

For the rewrite side of the loop (meta-harness):

```bash
# if COVERAGE.md or REVIEW_QUEUE.md shows a skill flagged for rewrite:
python .agent/tools/evolve.py prepare <skill>
# host agent writes candidate-SKILL.md in-session
python .agent/tools/evolve.py compare <skill> --candidate .agent/skills/<skill>/candidate-SKILL.md
python .agent/tools/evolve.py accept  <skill> --candidate .agent/skills/<skill>/candidate-SKILL.md
```

That's the whole operational loop. No dashboards, no web UI - just
markdown files, cron, and a harness that reads them.

---

## Which recipe do I pick?

| Situation | Recipe |
|---|---|
| Starting from zero, solo | #1 |
| Retrofitting an existing repo | #2 |
| Cross-harness setup (Claude Code + Hermes) | #3 |
| Already running upstream v0.5.0 | #4 |
| Already installed, want the production loop | #5 |

If none of these fit, the README's Quickstart + `docs/architecture.md`
cover the general case.
