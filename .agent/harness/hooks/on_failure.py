"""Failures are learning. High pain score + rewrite flag after repeat offenses."""
import json, datetime, os
from ._provenance import build_source

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
EPISODIC = os.path.join(ROOT, "memory/episodic/AGENT_LEARNINGS.jsonl")
FAILURE_THRESHOLD = 3
WINDOW_DAYS = 14

_ACTION_MAX = 200
_DETAIL_MAX = 500
_TOOL_OUTPUT_MAX = 2000
_TOOL_ARGS_MAX = 1000


def _truncate(text, limit):
    if text is None:
        return None
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f"...[truncated {len(s) - limit}b]"


def _count_recent_failures(skill_name):
    if not os.path.exists(EPISODIC):
        return 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=WINDOW_DAYS)
    count = 0
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
            if datetime.datetime.fromisoformat(e["timestamp"]) > cutoff:
                count += 1
        except (KeyError, ValueError):
            continue
    return count


def on_failure(skill_name, action, error, context="", confidence=0.9,
               evidence_ids=None, tool=None, tool_args=None, tool_output=None,
               duration_ms=None, exit_code=None):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "skill": skill_name,
        "action": _truncate(action, _ACTION_MAX),
        "result": "failure",
        "detail": _truncate(error, _DETAIL_MAX),
        "pain_score": 8,
        "importance": 7,
        "reflection": f"FAILURE in {skill_name}: {type(error).__name__}: "
                      f"{str(error)[:200]}",
        "context": context[:300],
        "confidence": confidence,
        "source": build_source(skill_name),
        "evidence_ids": list(evidence_ids) if evidence_ids else [],
    }
    if tool is not None:
        entry["tool"] = str(tool)
    if tool_args is not None:
        entry["tool_args"] = _truncate(
            tool_args if isinstance(tool_args, str) else json.dumps(tool_args,
                                                                    default=str),
            _TOOL_ARGS_MAX,
        )
    if tool_output is not None:
        entry["tool_output"] = _truncate(tool_output, _TOOL_OUTPUT_MAX)
    if duration_ms is not None:
        entry["duration_ms"] = int(duration_ms)
    if exit_code is not None:
        entry["exit_code"] = int(exit_code)
    # _count_recent_failures returns PRIOR failures only; add 1 for this one
    # so the rewrite flag fires on the Nth failure, not the (N+1)th.
    recent = _count_recent_failures(skill_name) + 1
    if recent >= FAILURE_THRESHOLD:
        entry["reflection"] += (
            f" | THIS SKILL HAS FAILED {recent} TIMES IN {WINDOW_DAYS}d. "
            f"Flag for rewrite."
        )
        entry["pain_score"] = 10
        entry["rewrite_flag"] = True
    os.makedirs(os.path.dirname(EPISODIC), exist_ok=True)
    with open(EPISODIC, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
