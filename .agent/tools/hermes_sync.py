"""Bridge graduated lessons + preferences into Hermes Agent's own memory layer.

Hermes (Nous Research) has its own persistence: MEMORY.md, USER.md, SOUL.md,
plus a SQLite state.db. The agentic-stack brain lives in `.agent/`. Rather
than pretending each is the other, this bridge mirrors the handful of files
the two systems should agree on, with explicit sentinels so the bridge can
rewrite its section without clobbering hand-edits.

Commands:
  hermes_sync.py plan       # dry-run: print the writes we'd make
  hermes_sync.py apply      # do the writes

Philosophy:
  - File-level only. state.db is intentionally out of scope — its schema is a
    moving target across Hermes versions and a bad write would wipe a
    session.
  - Idempotent. Section bounded by HTML sentinels so a re-run replaces the
    managed block and nothing else.
  - Hermes's own edits above the sentinel are preserved, same pattern as
    LESSONS.md uses for hand-curated content.
"""
import os, sys, json, argparse, datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LESSONS_JSONL = os.path.join(BASE, "memory/semantic/lessons.jsonl")
PREFERENCES = os.path.join(BASE, "memory/personal/PREFERENCES.md")

# Sentinels — any Hermes-side content above these fences is user-owned and
# we never touch it. Between the fences is managed; we regenerate it each
# run. The fences are HTML comments so Hermes's markdown renderer hides them.
_MEMORY_BEGIN = "<!-- BEGIN agentic-stack managed (do not edit by hand) -->"
_MEMORY_END = "<!-- END agentic-stack managed -->"


def _hermes_root():
    """Resolve the target Hermes directory.

    Priority:
      1. --hermes-root flag (passed through to main)
      2. HERMES_HOME env var
      3. ~/.hermes — the default install location

    Returning None here is fine; main() reports it back to the user as a
    configuration error rather than silently writing to cwd.
    """
    env = os.environ.get("HERMES_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    home = os.path.expanduser("~/.hermes")
    if os.path.isdir(home):
        return home
    return None


def _load_accepted_lessons():
    """Read lessons.jsonl and keep only the accepted (terminal) entries.

    Provisional lessons stay in agentic-stack but don't cross into Hermes —
    mirroring probationary content would let Hermes act on lessons that
    haven't been confirmed yet, which is exactly what the review layer
    exists to prevent.
    """
    if not os.path.exists(LESSONS_JSONL):
        return []
    out = []
    for line in open(LESSONS_JSONL):
        line = line.strip()
        if not line:
            continue
        try:
            l = json.loads(line)
        except json.JSONDecodeError:
            continue
        if l.get("status") != "accepted":
            continue
        out.append(l)
    return out


def _render_memory_block(lessons):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        _MEMORY_BEGIN,
        f"<!-- synced {now} from agentic-stack .agent/memory/semantic/lessons.jsonl -->",
        "",
        "## Lessons (from agentic-stack)",
        "",
    ]
    if not lessons:
        lines.append("_No accepted lessons yet._")
    for l in lessons:
        claim = l.get("claim", "").strip()
        conds = l.get("conditions", [])
        scope = l.get("applies_to_harness")
        suffix = []
        if conds:
            suffix.append(f"_conds: {', '.join(conds[:4])}_")
        if scope:
            suffix.append(f"_scoped: {scope}_")
        tail = f"  {' |'.join(suffix)}" if suffix else ""
        lines.append(f"- {claim}{tail}")
    lines.extend(["", _MEMORY_END])
    return "\n".join(lines) + "\n"


def _splice_managed(existing, block):
    """Replace the managed block in existing content, or append if absent."""
    if _MEMORY_BEGIN in existing and _MEMORY_END in existing:
        pre = existing.split(_MEMORY_BEGIN, 1)[0].rstrip() + "\n"
        post_idx = existing.find(_MEMORY_END) + len(_MEMORY_END)
        post = existing[post_idx:].lstrip("\n")
        return pre + "\n" + block + ("\n" + post if post else "")
    if existing and not existing.endswith("\n"):
        existing = existing + "\n"
    return existing + "\n" + block


def _plan_write(path, new_content):
    """Return (action, preview-diff-lines) without touching disk."""
    existing = open(path).read() if os.path.exists(path) else ""
    if existing == new_content:
        return "noop", []
    action = "update" if existing else "create"
    diff = [f"- {path} ({action})"]
    if existing:
        old_len, new_len = len(existing), len(new_content)
        diff.append(f"  size: {old_len} -> {new_len} ({new_len - old_len:+d})")
    else:
        diff.append(f"  new file, {len(new_content)} bytes")
    return action, diff


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def sync(hermes_root, apply_changes):
    if not hermes_root:
        print("error: could not find Hermes install. Set HERMES_HOME or "
              "pass --hermes-root.", file=sys.stderr)
        return 1
    if not os.path.isdir(hermes_root):
        print(f"error: hermes root not a directory: {hermes_root}",
              file=sys.stderr)
        return 1

    print(f"hermes root: {hermes_root}")

    # --- MEMORY.md: graduated lessons go here, under the sentinel.
    lessons = _load_accepted_lessons()
    memory_path = os.path.join(hermes_root, "MEMORY.md")
    existing_memory = open(memory_path).read() if os.path.exists(memory_path) else ""
    new_memory = _splice_managed(existing_memory, _render_memory_block(lessons))
    action_m, diff_m = _plan_write(memory_path, new_memory)

    # --- USER.md: mirror personal preferences. Full-file replace, no sentinel
    # — PREFERENCES.md is already the single source of truth for user
    # conventions, and Hermes tooling expects USER.md to be short and
    # self-contained rather than layered.
    user_path = os.path.join(hermes_root, "USER.md")
    new_user = ""
    if os.path.exists(PREFERENCES):
        new_user = (
            f"<!-- Synced from agentic-stack .agent/memory/personal/PREFERENCES.md -->\n"
            f"<!-- Last sync: {datetime.datetime.now().isoformat(timespec='seconds')} -->\n\n"
            + open(PREFERENCES).read()
        )
    action_u, diff_u = _plan_write(user_path, new_user) if new_user else ("skip", [
        f"- {user_path} (skip: PREFERENCES.md not present)",
    ])

    for line in diff_m + diff_u:
        print(line)

    if not apply_changes:
        print("\n(dry run - pass `apply` to write)")
        return 0

    if action_m in ("update", "create"):
        _write(memory_path, new_memory)
    if action_u in ("update", "create"):
        _write(user_path, new_user)
    print("\napplied.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cmd", choices=["plan", "apply"],
                   help="plan (dry-run) or apply the writes")
    p.add_argument("--hermes-root", default=None,
                   help="Override Hermes directory (default: $HERMES_HOME or ~/.hermes)")
    args = p.parse_args(argv)

    root = args.hermes_root or _hermes_root()
    sys.exit(sync(root, apply_changes=(args.cmd == "apply")))


if __name__ == "__main__":
    main()
