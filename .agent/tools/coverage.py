"""Harness-coverage metric: the missing gauge for agent observability.

Fowler's harness-engineering frame asks: we measure code coverage for
tests, how do we measure coverage for agent harnesses? This script is one
answer. It reads AGENT_LEARNINGS.jsonl and reports, over a rolling window:

  - Guide coverage    %% of tool calls that were checked against the
                      permission policy (i.e., produced a tool_schema +
                      pre_tool_call decision).
  - Sensor coverage   %% of tool calls that produced a post-execution
                      reflection richer than just result=ok/failure.
  - Skill activity    skills invoked vs. skills installed; dead skills
                      hint at triggers that no longer fire.
  - Harness mix       % of entries per harness. Lets you spot a harness
                      whose provenance isn't being tagged (spike in
                      'unknown' means detection broke).
  - Model mix         % of entries per model. Surfaces model drift.
  - Structured trace  %% of entries that carry tool/tool_args/exit_code
                      fields. Rising over time = the meta-harness work
                      is landing; flat = hooks aren't wired right.

Writes a JSON blob and a markdown summary. The markdown lands in
`memory/working/COVERAGE.md` so it's visible in every host session.

Run it from cron alongside auto_dream.py, or manually during review.
"""
import os, sys, json, argparse, datetime, collections

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EPISODIC = os.path.join(BASE, "memory/episodic/AGENT_LEARNINGS.jsonl")
SKILLS_DIR = os.path.join(BASE, "skills")
MANIFEST = os.path.join(SKILLS_DIR, "_manifest.jsonl")
OUT_MD = os.path.join(BASE, "memory/working/COVERAGE.md")
OUT_JSON = os.path.join(BASE, "memory/working/coverage.json")


def _load_entries(since):
    if not os.path.exists(EPISODIC):
        return []
    out = []
    for line in open(EPISODIC):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            ts = datetime.datetime.fromisoformat(e["timestamp"])
        except (KeyError, ValueError):
            continue
        if ts >= since:
            out.append(e)
    return out


def _load_skills():
    if not os.path.exists(MANIFEST):
        return []
    names = []
    for line in open(MANIFEST):
        line = line.strip()
        if not line:
            continue
        try:
            names.append(json.loads(line).get("name"))
        except json.JSONDecodeError:
            continue
    return [n for n in names if n]


def _pct(num, denom):
    return round(100 * num / denom, 1) if denom else 0.0


def compute(entries, installed_skills):
    total = len(entries)
    if total == 0:
        return {"total": 0}

    # Guide coverage proxy: entries whose tool field is populated AND the
    # skill is one that participates in the permission policy. We don't have
    # per-call gate decisions stored, so use "tool tagged and skill known"
    # as a correlate. Improves when more callers pass --tool.
    tool_tagged = sum(1 for e in entries if e.get("tool"))

    # Sensor coverage: an entry has richer reflection than just success/fail.
    sensor_rich = sum(1 for e in entries
                      if (e.get("reflection") or "").strip()
                      or e.get("tool_output")
                      or e.get("rewrite_flag"))

    structured = sum(1 for e in entries
                     if e.get("tool") and e.get("tool_args") is not None
                     and "exit_code" in e)

    # Skill activity
    skills_seen = collections.Counter(e.get("skill") or "unknown" for e in entries)
    dead_skills = sorted(set(installed_skills) - set(skills_seen))
    over_firing = sorted(
        skills_seen.items(), key=lambda kv: -kv[1])[:5]

    # Harness & model mix (from source.harness / source.model)
    harness_mix = collections.Counter(
        (e.get("source") or {}).get("harness") or "unknown" for e in entries)
    model_mix = collections.Counter(
        (e.get("source") or {}).get("model") or "unknown" for e in entries)

    # Failure concentration - which skill is paying the pain?
    failures = [e for e in entries if e.get("result") == "failure"]
    fail_by_skill = collections.Counter(
        e.get("skill") or "unknown" for e in failures)
    rewrite_flagged = sorted({e.get("skill") for e in entries
                              if e.get("rewrite_flag")})

    return {
        "total": total,
        "failures": len(failures),
        "failure_rate_pct": _pct(len(failures), total),
        "guide_coverage_pct": _pct(tool_tagged, total),
        "sensor_coverage_pct": _pct(sensor_rich, total),
        "structured_trace_pct": _pct(structured, total),
        "harness_mix": dict(harness_mix),
        "model_mix": dict(model_mix),
        "skills_seen": dict(skills_seen),
        "dead_skills": dead_skills,
        "top_skills": over_firing,
        "fail_by_skill": dict(fail_by_skill),
        "rewrite_flagged": rewrite_flagged,
    }


def render_md(stats, window_days):
    if stats.get("total", 0) == 0:
        return f"# Coverage\n\n_No entries in the last {window_days} days._\n"
    lines = [f"# Coverage (last {window_days}d)", ""]
    lines.append(f"**Entries:** {stats['total']}  "
                 f"**Failures:** {stats['failures']} "
                 f"({stats['failure_rate_pct']}%)")
    lines.append("")
    lines.append("## Core metrics")
    lines.append(f"- Guide coverage:       {stats['guide_coverage_pct']}%  "
                 f"(tool tag present)")
    lines.append(f"- Sensor coverage:      {stats['sensor_coverage_pct']}%  "
                 f"(reflection or tool_output)")
    lines.append(f"- Structured trace:     {stats['structured_trace_pct']}%  "
                 f"(tool + tool_args + exit_code)")
    lines.append("")
    lines.append("## Harness mix")
    for h, n in sorted(stats["harness_mix"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {h}: {n} ({_pct(n, stats['total'])}%)")
    if "unknown" in stats["harness_mix"] and stats["harness_mix"]["unknown"] / stats["total"] > 0.1:
        lines.append("")
        lines.append("> `unknown` harness share > 10%. Check AGENT_HARNESS "
                     "detection in adapter shell configs.")
    lines.append("")
    lines.append("## Model mix")
    for m, n in sorted(stats["model_mix"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {m}: {n} ({_pct(n, stats['total'])}%)")
    lines.append("")
    lines.append("## Skill activity")
    if stats["top_skills"]:
        lines.append("Top 5 invoked:")
        for name, n in stats["top_skills"]:
            lines.append(f"- {name}: {n}")
    if stats["dead_skills"]:
        lines.append("")
        lines.append("Dead skills (installed but not fired this window):")
        for s in stats["dead_skills"]:
            lines.append(f"- {s}  _(triggers may be stale)_")
    if stats["rewrite_flagged"]:
        lines.append("")
        lines.append("**Flagged for rewrite:**")
        for s in stats["rewrite_flagged"]:
            lines.append(f"- {s}  -> run `python .agent/tools/evolve.py prepare {s}`")
    if stats["fail_by_skill"]:
        lines.append("")
        lines.append("## Failures by skill")
        for name, n in sorted(stats["fail_by_skill"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {name}: {n}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=14,
                   help="Rolling window in days (default 14)")
    p.add_argument("--json", action="store_true",
                   help="Print JSON to stdout instead of writing files")
    args = p.parse_args(argv)

    since = datetime.datetime.now() - datetime.timedelta(days=args.days)
    entries = _load_entries(since)
    installed = _load_skills()
    stats = compute(entries, installed)
    stats["window_days"] = args.days
    stats["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    if args.json:
        print(json.dumps(stats, indent=2, default=str))
        return

    md = render_md(stats, args.days)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as f:
        f.write(md)
    with open(OUT_JSON, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
