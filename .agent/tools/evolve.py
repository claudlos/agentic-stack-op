"""Evolve skills by scoring rewrites against deterministic evals.

The meta-harness move: when `on_failure` flags a skill for rewrite (3+ fails
in 14 days), the host agent proposes a new SKILL.md. This tool mechanically
scores the original and the candidate against a skill-local eval file plus
the recent failure log, and refuses to swap in a regression.

Philosophy (mirrors auto_dream.py): the dumb parts are dumb, the reasoning
lives in the host agent. This file never writes a rewrite itself — it only
measures. No LLM call, no network, no unattended reasoning.

Commands:
  score <skill>                              # current SKILL.md
  score <skill> --file path/to/candidate.md  # any candidate
  compare <skill> --candidate path           # side-by-side, pick winner
  prepare <skill>                            # emit a rewrite brief for the host
  accept <skill> --candidate path [--force]  # swap in ONLY if not a regression

Eval file: skills/<name>/evals/eval.json (see the seed examples for shape).
"""
import os, sys, json, re, argparse, datetime, shutil

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS_DIR = os.path.join(BASE, "skills")
EPISODIC = os.path.join(BASE, "memory/episodic/AGENT_LEARNINGS.jsonl")
FAILURE_WINDOW_DAYS = 14


# ── Eval loading ───────────────────────────────────────────────────────────

def _eval_path(skill_name):
    return os.path.join(SKILLS_DIR, skill_name, "evals", "eval.json")


def load_eval(skill_name):
    """Load skill-local eval config. Missing file -> empty config (still scoreable).

    Returning {} rather than raising means a skill without explicit evals
    still produces a baseline score from dynamic failure references alone.
    That matters during bootstrap — you shouldn't need to write evals before
    you can measure the first rewrite.
    """
    path = _eval_path(skill_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: could not load {path}: {e}", file=sys.stderr)
        return {}


def load_skill_md(skill_name, override_path=None):
    path = override_path or os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"skill file not found: {path}")
    with open(path) as f:
        return f.read()


# ── Recent-failure extraction ─────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{3,}")


def recent_failure_keywords(skill_name, window_days=FAILURE_WINDOW_DAYS,
                            top_n=8):
    """Extract distinctive keywords from recent failures of this skill.

    A rewrite that doesn't address the very failures that triggered it is a
    rewrite in name only. These keywords become required references in the
    dynamic score component — if the candidate SKILL.md doesn't mention at
    least one of them, it can't beat the original.

    Stopwords + common skill nouns are filtered so 'failure'/'error'/'bash'
    don't dominate the signal.
    """
    if not os.path.exists(EPISODIC):
        return []
    cutoff = datetime.datetime.now() - datetime.timedelta(days=window_days)
    stops = {"failure", "failed", "error", "bash", "skill", "tool", "this",
             "that", "with", "from", "when", "where", "into", "about",
             "have", "been", "will", "would", "should", "could", "some"}
    counts = {}
    for line in open(EPISODIC):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("skill") != skill_name or e.get("result") != "failure":
            continue
        try:
            if datetime.datetime.fromisoformat(e["timestamp"]) <= cutoff:
                continue
        except (KeyError, ValueError):
            continue
        text = " ".join([
            str(e.get("action", "")),
            str(e.get("detail", "")),
            str(e.get("reflection", "")),
            str(e.get("tool_output", "")),
        ])
        for tok in _WORD_RE.findall(text.lower()):
            if tok in stops:
                continue
            counts[tok] = counts.get(tok, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:top_n]


# ── Scoring ────────────────────────────────────────────────────────────────

def _has_frontmatter_key(text, key):
    """Frontmatter is a YAML-ish block between `---` fences at the top."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    fm = parts[1]
    return any(line.lstrip().startswith(f"{key}:") for line in fm.splitlines())


def score_skill(text, eval_config, failure_keywords):
    """Deterministic score. Higher is better; components are explainable.

    Explainable is the whole point — when evolve.py refuses a rewrite, the
    host agent needs to see WHICH axis regressed, not just a scalar verdict.
    """
    detail = []
    total = 0

    # Required sections (structural preservation)
    for section in eval_config.get("required_sections", []):
        present = section in text
        pts = 10 if present else 0
        total += pts
        detail.append({"axis": "required_section", "target": section,
                       "present": present, "points": pts})

    # Required frontmatter keys
    for key in eval_config.get("required_frontmatter", []):
        present = _has_frontmatter_key(text, key)
        pts = 5 if present else 0
        total += pts
        detail.append({"axis": "required_frontmatter", "target": key,
                       "present": present, "points": pts})

    # Forbidden patterns (negative signal)
    for pat in eval_config.get("forbidden_patterns", []):
        found = pat in text
        pts = -20 if found else 0
        total += pts
        detail.append({"axis": "forbidden_pattern", "target": pat,
                       "present": found, "points": pts})

    # Preserved constraints — the agent rewriting must not silently drop them
    for constraint in eval_config.get("preserved_constraints", []):
        present = constraint.lower() in text.lower()
        pts = 15 if present else -5
        total += pts
        detail.append({"axis": "preserved_constraint", "target": constraint,
                       "present": present, "points": pts})

    # Trigger coverage — at least one trigger per keyword group
    for group in eval_config.get("trigger_coverage", []):
        covered = any(kw.lower() in text.lower() for kw in group)
        pts = 5 if covered else 0
        total += pts
        detail.append({"axis": "trigger_coverage", "target": group,
                       "present": covered, "points": pts})

    # Static failure references from eval file
    for ref in eval_config.get("failure_references", []):
        kws = ref.get("keywords", [])
        hits = sum(1 for kw in kws if kw.lower() in text.lower())
        need = ref.get("min_count", 1)
        pts = 5 if hits >= need else -10
        total += pts
        detail.append({"axis": "static_failure_ref",
                       "target": {"keywords": kws, "need": need, "hits": hits},
                       "present": hits >= need, "points": pts})

    # Dynamic failure references — the keywords from actual recent failures.
    # A rewrite must reference at least one or it isn't responsive to the
    # failures that triggered the rewrite flag in the first place.
    if failure_keywords:
        hits = sum(1 for kw in failure_keywords if kw in text.lower())
        coverage = hits / len(failure_keywords)
        pts = int(round(20 * coverage))  # 0..20 bonus
        total += pts
        detail.append({"axis": "dynamic_failure_coverage",
                       "target": {"keywords": failure_keywords,
                                  "hits": hits, "coverage": round(coverage, 2)},
                       "present": hits > 0, "points": pts})

    # Length bounds
    bounds = eval_config.get("length_bounds", {})
    if bounds:
        n = len(text)
        lo = bounds.get("min_chars", 0)
        hi = bounds.get("max_chars", 10**9)
        pts = 0
        if n < lo:
            pts = -50
        elif n > hi:
            pts = -((n - hi) // 100)
        total += pts
        detail.append({"axis": "length", "target": {"min": lo, "max": hi},
                       "present": lo <= n <= hi, "chars": n, "points": pts})

    return {"total": total, "detail": detail}


# ── CLI commands ──────────────────────────────────────────────────────────

def cmd_score(skill_name, override_path=None, as_json=False):
    text = load_skill_md(skill_name, override_path)
    cfg = load_eval(skill_name)
    kws = recent_failure_keywords(skill_name)
    result = score_skill(text, cfg, kws)
    if as_json:
        print(json.dumps(result, indent=2))
        return result
    _print_score(skill_name, override_path, result)
    return result


def _print_score(skill_name, path, result):
    label = path or f"{skill_name} (current)"
    print(f"=== {label}  ->  score {result['total']} ===")
    for d in result["detail"]:
        sign = "+" if d["points"] >= 0 else ""
        print(f"  {sign}{d['points']:>4}  {d['axis']:<26} "
              f"{'[ok] ' if d.get('present') else '[miss] '}{d.get('target')}")


def cmd_compare(skill_name, candidate_path):
    cfg = load_eval(skill_name)
    kws = recent_failure_keywords(skill_name)
    current = score_skill(load_skill_md(skill_name), cfg, kws)
    candidate = score_skill(load_skill_md(skill_name, candidate_path), cfg, kws)
    _print_score(skill_name, None, current)
    print()
    _print_score(skill_name, candidate_path, candidate)
    print()
    delta = candidate["total"] - current["total"]
    if delta > 0:
        print(f"CANDIDATE WINS by {delta} points.")
    elif delta == 0:
        print("TIE — candidate is not worth swapping in.")
    else:
        print(f"CANDIDATE LOSES by {abs(delta)} points. REGRESSION.")
    return delta


def cmd_prepare(skill_name):
    """Emit a rewrite brief the host agent can paste into its working buffer.

    Includes: current SKILL.md text, recent failure episodes (action +
    reflection), dynamic failure keywords, preserved constraints from the
    eval. This is the *input* to the rewrite; the host agent generates the
    output as a new file under `skills/<name>/candidate-SKILL.md`.
    """
    text = load_skill_md(skill_name)
    cfg = load_eval(skill_name)
    kws = recent_failure_keywords(skill_name)
    recent = _recent_failures(skill_name, limit=10)
    preserved = cfg.get("preserved_constraints", [])
    sections = cfg.get("required_sections", [])

    print(f"# Rewrite brief for `{skill_name}`\n")
    print(f"**Recent failures (last {FAILURE_WINDOW_DAYS}d):** {len(recent)}")
    for e in recent:
        print(f"- [{e.get('timestamp','')[:19]}] {e.get('action','')}: "
              f"{e.get('reflection') or e.get('detail','')}")
    print(f"\n**Dynamic failure keywords:** {', '.join(kws) or '(none)'}")
    print(f"\n**Preserved constraints** (must survive the rewrite): "
          f"{preserved or '(none)'}")
    print(f"\n**Required sections** (must remain): {sections or '(none)'}")
    print("\n**Current SKILL.md:**\n")
    print("```markdown")
    print(text)
    print("```")
    print("\n---\nNext step: write your rewrite to "
          f"`.agent/skills/{skill_name}/candidate-SKILL.md`, then run\n"
          f"`python .agent/tools/evolve.py compare {skill_name} "
          f"--candidate .agent/skills/{skill_name}/candidate-SKILL.md`\n"
          "If the candidate wins, run `evolve.py accept`.")


def _recent_failures(skill_name, limit=10):
    if not os.path.exists(EPISODIC):
        return []
    cutoff = datetime.datetime.now() - datetime.timedelta(days=FAILURE_WINDOW_DAYS)
    out = []
    for line in open(EPISODIC):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("skill") != skill_name or e.get("result") != "failure":
            continue
        try:
            if datetime.datetime.fromisoformat(e["timestamp"]) <= cutoff:
                continue
        except (KeyError, ValueError):
            continue
        out.append(e)
    out.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return out[:limit]


def cmd_accept(skill_name, candidate_path, force=False):
    """Swap the candidate in only if scoring says it's not a regression.

    The original SKILL.md is archived to `skills/<name>/_history/` with a
    timestamp so rollback is trivial. `--force` bypasses the regression
    guard and is logged loudly — this is not a silent escape hatch.
    """
    current_text = load_skill_md(skill_name)
    cand_text = load_skill_md(skill_name, candidate_path)
    cfg = load_eval(skill_name)
    kws = recent_failure_keywords(skill_name)
    current = score_skill(current_text, cfg, kws)
    candidate = score_skill(cand_text, cfg, kws)
    delta = candidate["total"] - current["total"]

    if delta <= 0 and not force:
        print(f"REFUSED: candidate delta = {delta} (<=0). "
              f"Use --force to override; the refusal will be logged.",
              file=sys.stderr)
        sys.exit(3)

    skill_dir = os.path.join(SKILLS_DIR, skill_name)
    hist_dir = os.path.join(skill_dir, "_history")
    os.makedirs(hist_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = os.path.join(hist_dir, f"SKILL.{stamp}.md")
    shutil.copy2(os.path.join(skill_dir, "SKILL.md"), archive)
    shutil.copy2(candidate_path, os.path.join(skill_dir, "SKILL.md"))

    # Write an audit note so git log + a grep over _history/ tells the full
    # story of what changed and why scoring accepted it.
    note_path = os.path.join(hist_dir, f"SKILL.{stamp}.note.md")
    with open(note_path, "w") as f:
        f.write(f"# Rewrite accepted {stamp}\n\n")
        f.write(f"- previous score: {current['total']}\n")
        f.write(f"- new score:      {candidate['total']}\n")
        f.write(f"- delta:          {delta}\n")
        f.write(f"- forced:         {force}\n")
        f.write(f"- candidate src:  {candidate_path}\n")
    print(f"accepted: score {current['total']} -> {candidate['total']} "
          f"(Δ {delta:+d}). previous archived at {archive}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_score = sub.add_parser("score")
    p_score.add_argument("skill")
    p_score.add_argument("--file", default=None,
                         help="Score this file instead of the live SKILL.md.")
    p_score.add_argument("--json", action="store_true")

    p_comp = sub.add_parser("compare")
    p_comp.add_argument("skill")
    p_comp.add_argument("--candidate", required=True)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("skill")

    p_acc = sub.add_parser("accept")
    p_acc.add_argument("skill")
    p_acc.add_argument("--candidate", required=True)
    p_acc.add_argument("--force", action="store_true")

    args = p.parse_args(argv)
    if args.cmd == "score":
        cmd_score(args.skill, args.file, as_json=args.json)
    elif args.cmd == "compare":
        cmd_compare(args.skill, args.candidate)
    elif args.cmd == "prepare":
        cmd_prepare(args.skill)
    elif args.cmd == "accept":
        cmd_accept(args.skill, args.candidate, force=args.force)


if __name__ == "__main__":
    main()
