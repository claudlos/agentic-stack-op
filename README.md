# agentic-stack-op

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/claudlos/agentic-stack-op/actions/workflows/ci.yml/badge.svg)](https://github.com/claudlos/agentic-stack-op/actions/workflows/ci.yml)
[![v0.6.0](https://img.shields.io/github/v/release/claudlos/agentic-stack-op)](https://github.com/claudlos/agentic-stack-op/releases/latest)

> **One brain, many harnesses - now measured.** A portable `.agent/` folder
> (memory + skills + protocols) that plugs into Claude Code, Cursor, Windsurf,
> OpenCode, OpenClient, Hermes, or a DIY Python loop and keeps its knowledge
> when you switch. This fork adds a **meta-harness layer** that makes the
> brain self-evaluating: every skill has a deterministic score, every
> episodic entry is a replayable trace, and CI proves harness-parity instead
> of asserting it.

> Extends [codejunkie99/agentic-stack](https://github.com/codejunkie99/agentic-stack)
> (MIT, by [@AV1DLIVE](https://twitter.com/AV1DLIVE)). All original design,
> seed skills, memory architecture, and review protocol credit to the
> upstream author. See [docs/meta-harness.md](docs/meta-harness.md) for
> what's new and why it matters.

<p align="center">
  <img src="docs/diagram.svg" alt="agentic-stack architecture" width="880"/>
</p>

## Why this fork

| Upstream v0.5.0 | This fork, v0.6.0 |
|---|---|
| Skills have self-rewrite hooks but nothing scores them | `evolve.py` scores rewrites against per-skill `eval.json` + live failure log; refuses regressions |
| Episodic log is free-form text | Structured trace fields (`tool`, `tool_args`, `tool_output`, `exit_code`, `duration_ms`) + provenance (`source.harness`, `source.model`) |
| `permissions.md` hand-edited; Claude Code deny list hand-edited; can drift | `permissions.json` is the source of truth; installer renders both; CI fails on drift |
| Hermes adapter = an `AGENTS.md` pointer | Real `hermes_sync.py` bridge mirroring lessons into Hermes's `MEMORY.md` / `USER.md` (sentinel-guarded, idempotent) |
| "One brain, many harnesses" was a claim | `examples/switchtest/` has 5 equivalence checks that **fail the build** if the claim breaks |
| Harness health was unknowable | `coverage.py` writes `COVERAGE.md`: guide %, sensor %, harness mix, dead skills, rewrite-flagged |

Full release notes: [v0.6.0 on GitHub](https://github.com/claudlos/agentic-stack-op/releases/tag/v0.6.0).

## Quickstart

**Starting a new project from zero:**

```bash
# macOS / Linux / Git Bash
git clone https://github.com/claudlos/agentic-stack-op.git
cd agentic-stack-op
./install.sh claude-code --new-project my-app --yes
cd ../my-app   # git-initialised, .gitignore + README seeded, brain installed, ready to code
```

```powershell
# Windows (PowerShell)
git clone https://github.com/claudlos/agentic-stack-op.git
cd agentic-stack-op
.\install.ps1 claude-code -NewProject my-app -Yes
cd ..\my-app
```

**Retrofitting an existing repo:**

```bash
./install.sh claude-code /path/to/existing-project
# adapter: claude-code | cursor | windsurf | opencode | openclient | hermes | standalone-python
```

The installer probes `python` / `python3` with `--version` so the
Microsoft Store stub alias can't silently break your hooks. See
[`docs/recipes.md`](docs/recipes.md) for full walkthroughs (cross-harness
setup, migration from upstream v0.5.0, cron + daily review).

**Verify it works:**

```bash
python examples/switchtest/run_switchtest.py
# [1/5] install parity across adapters
#   PASS all 7 adapters receive identical .agent/ trees
# [2/5] trace parity across harness labels
#   PASS same trace under 3 different harness labels differs only in source.harness
# [3/5] cluster parity surfaces cross-harness patterns
#   PASS cross-harness pattern carries both harness and model labels
# [4/5] permission safety parity (JSON >= markdown fallback)
#   PASS JSON path >= markdown fallback on all cases
# [5/5] stdin hook parser handles Claude Code PostToolUse payload
#   PASS Claude Code JSON payload lands as structured episodic entry
# 5/5 checks passed
```

## What you get

**Memory - four layers.** `working/` (live task state + auto-generated
`REVIEW_QUEUE.md` + `COVERAGE.md`), `episodic/` (every action as a
structured trace), `semantic/` (distilled lessons, `lessons.jsonl` is
source of truth, `LESSONS.md` is rendered), `personal/` (user
conventions, never merged into semantic).

**Skills - progressive disclosure.** A lightweight `_manifest.jsonl`
always loads; full `SKILL.md` only loads when triggers match the task.
Every skill ships with a self-rewrite hook and an `evals/eval.json`
that describes what a rewrite must preserve.

**Protocols - policy-as-code.** `permissions.json` is the source of
truth. `permissions.md` (human) and `.claude-deny.json` (adapter) are
rendered from it. `pre_tool_call.py` reads the JSON directly; CI
(`permissions_render.py --check`) fails if any rendered artefact drifts.

**Review protocol.** `auto_dream.py` stages candidate lessons
mechanically; it does not reason. Your host agent reviews via
`list_candidates.py` / `graduate.py` / `reject.py` / `reopen.py` - each
decision records a required rationale. No unattended reasoning, no
provider coupling.

## The meta-harness loop

When a skill fails 3+ times in 14 days, `on_failure.py` sets a
rewrite flag. The host agent sees it in `REVIEW_QUEUE.md` at session
start and runs:

```bash
# 1. Emit a rewrite brief (current SKILL.md + recent failures + dynamic keywords)
python .agent/tools/evolve.py prepare debug-investigator

# 2. Host agent writes its rewrite to skills/debug-investigator/candidate-SKILL.md

# 3. Score both and compare
python .agent/tools/evolve.py compare debug-investigator \
    --candidate .agent/skills/debug-investigator/candidate-SKILL.md
# === debug-investigator (current)  ->  score 80 ===
#   +10  required_section  [ok] ## The loop
#   +15  preserved_constraint  [ok] reproduce before fixing
#   ...
# === candidate.md  ->  score -40 ===
#   +0   required_section  [miss] ## The loop
#   -5   preserved_constraint  [miss] reproduce before fixing
#   ...
# CANDIDATE LOSES by 120 points. REGRESSION.

# 4. Accept (refuses regressions unless --force)
python .agent/tools/evolve.py accept debug-investigator --candidate <path>
```

Scoring is deterministic: required sections, preserved constraints,
forbidden patterns, length bounds, trigger coverage, *plus* dynamic
failure keywords from the last 14 days of `AGENT_LEARNINGS.jsonl`. A
rewrite that doesn't reference the failures that triggered it can't
beat the original. No LLM in the loop. Full details in
[`docs/meta-harness.md`](docs/meta-harness.md).

## Review protocol (host-agent CLI)

```bash
# Pending candidates + skills flagged for rewrite (auto-generated by auto_dream)
cat .agent/memory/working/REVIEW_QUEUE.md

# Detail on a candidate
python .agent/tools/list_candidates.py

# Accept with rationale (required)
python .agent/tools/graduate.py <id> --rationale "evidence holds, matches PREFERENCES"

# Scope a lesson to one harness if evidence only came from there
python .agent/tools/graduate.py <id> --rationale "..." --scope-to-harness cursor

# Reject with reason (required); preserves decision history
python .agent/tools/reject.py <id> --reason "too specific to generalize"
```

Graduated lessons append to `semantic/lessons.jsonl`; `LESSONS.md`
re-renders. Rejected candidates retain full decision history so
recurring churn is visible, not fresh each time.

## Observability

```bash
python .agent/tools/coverage.py  # writes memory/working/COVERAGE.md
# Entries: 412   Failures: 31 (7.5%)
# Guide coverage:       92.4%   (tool tag present)
# Sensor coverage:      81.3%   (reflection or tool_output)
# Structured trace:     78.6%
# Harness mix: claude-code: 310, cursor: 78, unknown: 24 (5.8%)
# Dead skills: skillforge  (triggers may be stale)
# Flagged for rewrite:  deploy-checklist -> python .agent/tools/evolve.py prepare deploy-checklist
```

Runs inside `auto_dream.py` so the file stays fresh alongside the review
queue. `unknown` harness share > 10% means auto-detection in
`_provenance.py` broke - check `AGENT_HARNESS` in your adapter shell.

## Adapters

Seven adapters, honest capability matrix in
[`docs/adapter-parity.md`](docs/adapter-parity.md). Summary:

- **Claude Code** - first-class. Hooks, deny rules from `permissions.json`,
  harness auto-detected via `CLAUDECODE=1`.
- **OpenCode** - permission rules in `opencode.json`; no execution hook.
- **Cursor / Windsurf / OpenClient** - read `.agent/`; no pre/post-tool
  hook API available upstream, so memory logging is manual (call
  `memory_reflect.py` from skills).
- **Hermes** - reads `AGENTS.md`. Bridge (`hermes_sync.py`) mirrors
  accepted lessons into Hermes's native `MEMORY.md` / `USER.md`.
- **Standalone Python** - full hook control; reference conductor in
  `.agent/harness/conductor.py`.

## Repo layout

```
.agent/                         # the portable brain (byte-identical across adapters)
|-- AGENTS.md                   # the map, incl. meta-harness pointers
|-- harness/                    # conductor + hooks (standalone path)
|   |-- hooks/
|   |   |-- _provenance.py      # harness + model auto-detection
|   |   |-- post_execution.py   # structured trace logger
|   |   |-- pre_tool_call.py    # JSON-policy enforcement
|   |   |-- on_failure.py       # 3-in-14d -> rewrite_flag
|   |   +-- __init__.py
|   +-- {conductor, context_budget, salience, text, llm}.py
|-- memory/                     # working / episodic / semantic / personal
|   |-- auto_dream.py           # staging-only dream cycle + coverage refresh
|   |-- cluster.py              # content clustering + harness/model roll-up
|   |-- promote.py  validate.py  review_state.py  render_lessons.py
|   |-- decay.py  archive.py
|   +-- memory_search.py        # [BETA] FTS5 search (opt-in)
|-- skills/
|   |-- _index.md  _manifest.jsonl
|   |-- _eval.schema.json                        # NEW
|   +-- <skill>/
|       |-- SKILL.md
|       |-- KNOWLEDGE.md        # (optional)
|       |-- evals/eval.json     # NEW: scored by evolve.py
|       +-- _history/           # NEW: auto-archived previous versions
|-- protocols/
|   |-- permissions.json        # NEW: source of truth
|   |-- permissions.schema.json # NEW: drift guard
|   |-- permissions.md          # rendered
|   |-- .claude-deny.json       # rendered for installer
|   |-- tool_schemas/
|   +-- delegation.md
+-- tools/
    |-- memory_reflect.py       # +--stdin JSON intake for Claude Code hooks
    |-- list_candidates.py  graduate.py  reject.py  reopen.py
    |-- evolve.py               # NEW: score/compare/prepare/accept
    |-- coverage.py             # NEW: harness coverage metric
    |-- hermes_sync.py          # NEW: Hermes bridge
    |-- permissions_render.py   # NEW: render permissions.json
    |-- render_claude_settings.py  # NEW: merge deny into settings.json
    |-- validate_schemas.py     # NEW: stdlib JSON-shape validator
    +-- skill_loader.py

adapters/                       # one small shim per harness
docs/                           # architecture, meta-harness, adapter-parity, writing-skills
examples/
|-- first_run.py
+-- switchtest/                 # NEW: 5-check equivalence suite
install.sh  install.ps1         # with working-python probe
onboard.py  onboard_*.py        # wizard (UTF-8-safe on Windows)
```

## Requirements

- Python 3.9+ (3.11 used in CI).
- Git (for commit_sha in provenance; optional).
- That's it. The whole brain is stdlib - no jsonschema, no yaml, nothing
  to `pip install`.

## Run it unattended

```bash
crontab -e
0 3 * * * python /path/to/project/.agent/memory/auto_dream.py >> /path/to/project/.agent/memory/dream.log 2>&1
```

One cron entry refreshes both `REVIEW_QUEUE.md` (pending candidates +
rewrite flags) and `COVERAGE.md`. `auto_dream.py` only does mechanical
file operations - no git commits, no network, no reasoning.

## Limitations

Being honest about what `v0.6.0` doesn't do:

- **No LLM judge.** All scoring in `evolve.py` is computational per
  Fowler's harness-engineering frame. An inferential sensor would catch
  semantic regressions this can't (skill rewrites that technically
  preserve sections but mangle meaning). Out of scope for a no-dep
  stdlib tool.
- **Cursor / Windsurf / OpenClient hooks.** No upstream hook API, so
  logging on those harnesses is operator-driven (skills call
  `memory_reflect.py` themselves). Watcher-daemon approach sketched in
  `docs/adapter-parity.md`, not built.
- **Hermes `state.db` one-way.** The bridge mirrors into Hermes; it does
  not read Hermes's SQLite back. That schema is a moving target and a
  bad write could wipe a session.
- **No end-to-end LLM test.** `switchtest` proves install / trace /
  cluster / permission parity, not agent-behavior parity. An
  LLM-in-the-loop suite (`examples/switchtest/live/`) is future work.
- **No Homebrew tap yet.** Clone-only for this fork. A tap repo + tagged
  Formula will land when there's signal it's wanted.

## Contributing

PRs welcome. The sanity gates are:

```bash
python examples/switchtest/run_switchtest.py       # must stay 5/5
python .agent/tools/validate_schemas.py            # JSON shapes
python .agent/tools/permissions_render.py --check  # no policy drift
```

CI runs all three on Linux + Windows for every push and PR.

## License & credits

MIT - see [LICENSE](LICENSE).

Upstream: [codejunkie99/agentic-stack](https://github.com/codejunkie99/agentic-stack)
by [@AV1DLIVE](https://twitter.com/AV1DLIVE). The original design is
based on the article
[**"The Agentic Stack"**](https://x.com/Av1dlive/status/2044453102703841645?s=20)
by the same author - the memory layering, review protocol, and
harness-agnostic philosophy are all theirs. This fork adds a meta-harness
layer on top without changing the foundation.

Further reading:

- [`docs/recipes.md`](docs/recipes.md) - five end-to-end workflows
- [`docs/architecture.md`](docs/architecture.md) - full module tour
- [`docs/meta-harness.md`](docs/meta-harness.md) - the evolve loop
- [`docs/adapter-parity.md`](docs/adapter-parity.md) - per-harness capability matrix
- [`docs/writing-skills.md`](docs/writing-skills.md) - skill + eval authoring

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=claudlos/agentic-stack-op&type=Date)](https://star-history.com/#claudlos/agentic-stack-op&Date)
