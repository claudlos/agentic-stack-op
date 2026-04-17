"""Runs after every action. Appends a structured entry to episodic memory.

Structured trace fields (tool, tool_args, tool_output, duration_ms, exit_code)
are optional — when the caller supplies them, the entry becomes replayable
and scoreable. Without them we still get the free-form skill/action/detail
log, so existing callers keep working.
"""
import json, datetime, os
from ._provenance import build_source

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
EPISODIC = os.path.join(ROOT, "memory/episodic/AGENT_LEARNINGS.jsonl")

# Truncation bounds — keep episodic lines small enough to grep + cluster on
# without exploding disk. tool_output is generous (real command output is the
# most useful thing to replay), action/detail stay short.
_ACTION_MAX = 200
_DETAIL_MAX = 500
_TOOL_OUTPUT_MAX = 2000
_TOOL_ARGS_MAX = 1000


def _truncate(text, limit):
    """Byte-safe truncation with an explicit `...[truncated]` marker.

    Avoids chopping inside a JSON literal in tool_args when the dict itself is
    huge, and makes the elision visible during later replay so evolve.py
    doesn't diff truncated-vs-full outputs and conclude they differ.
    """
    if text is None:
        return None
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f"...[truncated {len(s) - limit}b]"


def log_execution(skill_name, action, result, success, reflection="",
                  importance=5, confidence=0.5, evidence_ids=None,
                  tool=None, tool_args=None, tool_output=None,
                  duration_ms=None, exit_code=None):
    os.makedirs(os.path.dirname(EPISODIC), exist_ok=True)
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "skill": skill_name,
        "action": _truncate(action, _ACTION_MAX),
        "result": "success" if success else "failure",
        "detail": _truncate(result, _DETAIL_MAX),
        "pain_score": 2 if success else 7,
        "importance": importance,
        "reflection": reflection,
        "confidence": confidence,
        "source": build_source(skill_name),
        "evidence_ids": list(evidence_ids) if evidence_ids else [],
    }
    # Only populate trace fields when the caller actually supplied them —
    # None values on the wire aren't signal, just noise that bloats lines.
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
    with open(EPISODIC, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
