"""Reflection utility. Call from any skill after significant events.

Two call styles are supported so every harness can integrate without a shim:

  1. Positional CLI (legacy, still works):
       memory_reflect.py <skill> <action> <outcome> [--fail ...]

  2. Flag-rich CLI (structured traces):
       memory_reflect.py --skill <s> --action <a> --outcome <o>
         [--tool Bash] [--tool-args JSON] [--tool-output TEXT]
         [--duration-ms N] [--exit-code N] [--harness claude-code] [--model ...]

  3. JSON on stdin (Claude Code hook format):
       echo '{"tool_name":"Bash","tool_input":{...},"tool_response":{...}}' |
         memory_reflect.py --stdin [--skill ...]

Anything the structured trace captures becomes replay fuel for tools/evolve.py
and coverage material for tools/coverage.py. Old callers get the old log
shape — new fields are additive, never required.
"""
import os, sys, json, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
from hooks.post_execution import log_execution
from hooks.on_failure import on_failure


def reflect(skill_name, action, outcome, success=True, importance=5,
            reflection="", error=None, confidence=None, evidence_ids=None,
            tool=None, tool_args=None, tool_output=None,
            duration_ms=None, exit_code=None):
    common = dict(
        tool=tool, tool_args=tool_args, tool_output=tool_output,
        duration_ms=duration_ms, exit_code=exit_code,
    )
    if success:
        return log_execution(skill_name, action, outcome, True,
                             reflection=reflection, importance=importance,
                             confidence=0.5 if confidence is None else confidence,
                             evidence_ids=evidence_ids, **common)
    return on_failure(skill_name, action, error or outcome,
                      context=reflection,
                      confidence=0.9 if confidence is None else confidence,
                      evidence_ids=evidence_ids, **common)


def _load_stdin_json():
    """Parse a Claude-Code-style hook payload from stdin if one is present."""
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
    except Exception:
        return None
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _from_stdin_payload(payload, defaults):
    """Map Claude Code's PostToolUse JSON shape onto reflect() kwargs.

    Claude Code sends {tool_name, tool_input, tool_response, ...}. Other
    harnesses are free to POST the same shape. Defaults (from argparse) fill
    anything stdin omits so operators can override harness/skill at will.
    """
    tool_name = payload.get("tool_name") or payload.get("tool") or defaults.get("tool")
    tool_input = payload.get("tool_input") or payload.get("args")
    tool_response = payload.get("tool_response") or payload.get("output")
    # Success is a best-effort read — Claude Code's hook fires on success
    # AND failure with no unified field, so we look at common signals.
    success = True
    if isinstance(tool_response, dict):
        if tool_response.get("is_error") or tool_response.get("error"):
            success = False
        if tool_response.get("exit_code") not in (None, 0):
            success = False
    action = defaults.get("action") or (f"{tool_name}" if tool_name else "tool-call")
    outcome_text = (
        tool_response if isinstance(tool_response, str)
        else json.dumps(tool_response, default=str)[:500] if tool_response is not None
        else (defaults.get("outcome") or "ok")
    )
    return dict(
        skill_name=defaults.get("skill") or "hook",
        action=action,
        outcome=outcome_text,
        success=success,
        tool=tool_name,
        tool_args=tool_input,
        tool_output=outcome_text if tool_name else None,
        duration_ms=payload.get("duration_ms"),
        exit_code=(
            tool_response.get("exit_code")
            if isinstance(tool_response, dict) else None
        ),
    )


def _build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    # Positional (legacy) — optional so flag-only / stdin-only calls work.
    p.add_argument("skill_pos", nargs="?")
    p.add_argument("action_pos", nargs="?")
    p.add_argument("outcome_pos", nargs="?")
    # Named equivalents (new). Named wins when both are given.
    p.add_argument("--skill")
    p.add_argument("--action")
    p.add_argument("--outcome")
    p.add_argument("--fail", action="store_true")
    p.add_argument("--importance", type=int, default=5)
    p.add_argument("--note", default="")
    p.add_argument("--confidence", type=float, default=None)
    p.add_argument("--evidence", nargs="*", default=None,
                   help="Space-separated episode/lesson IDs this entry builds on.")
    # Structured trace fields
    p.add_argument("--tool", default=None,
                   help="Tool name (Bash, Edit, Write, ...).")
    p.add_argument("--tool-args", default=None,
                   help="JSON string of tool args.")
    p.add_argument("--tool-output", default=None,
                   help="Raw tool output (truncated on write).")
    p.add_argument("--duration-ms", type=int, default=None)
    p.add_argument("--exit-code", type=int, default=None)
    # Provenance overrides (normally auto-detected via _provenance)
    p.add_argument("--harness", default=None,
                   help="Override the auto-detected harness label.")
    p.add_argument("--model", default=None,
                   help="Override the auto-detected model label.")
    # Stdin JSON intake
    p.add_argument("--stdin", action="store_true",
                   help="Read a JSON hook payload from stdin.")
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    # Provenance overrides propagate via env so _provenance picks them up on
    # first touch. Writing to env from CLI is fine — this process exits right
    # after logging, so no cross-run leakage.
    if args.harness:
        os.environ["AGENT_HARNESS"] = args.harness
    if args.model:
        os.environ["AGENT_MODEL"] = args.model

    payload = _load_stdin_json() if args.stdin else None

    skill = args.skill or args.skill_pos
    action = args.action or args.action_pos
    outcome = args.outcome or args.outcome_pos

    tool_args = args.tool_args
    if tool_args:
        try:
            tool_args = json.loads(tool_args)
        except json.JSONDecodeError:
            # Leave as raw string — log_execution handles both dict and string.
            pass

    if payload is not None:
        kwargs = _from_stdin_payload(payload, {
            "skill": skill, "action": action, "outcome": outcome,
            "tool": args.tool,
        })
        # CLI-supplied values still win — stdin payloads are fallback data,
        # not ground truth, because the harness that assembled them may be
        # less informed than the operator firing the hook.
        if args.tool:
            kwargs["tool"] = args.tool
        if tool_args is not None:
            kwargs["tool_args"] = tool_args
        if args.tool_output is not None:
            kwargs["tool_output"] = args.tool_output
        if args.duration_ms is not None:
            kwargs["duration_ms"] = args.duration_ms
        if args.exit_code is not None:
            kwargs["exit_code"] = args.exit_code
        kwargs["importance"] = args.importance
        kwargs["reflection"] = args.note
        kwargs["confidence"] = args.confidence
        kwargs["evidence_ids"] = args.evidence
        if args.fail:
            kwargs["success"] = False
        print(reflect(**kwargs))
        return

    if not (skill and action and outcome):
        print("error: need skill/action/outcome via positional args, flags, "
              "or --stdin payload.", file=sys.stderr)
        sys.exit(2)

    print(reflect(
        skill, action, outcome,
        success=not args.fail,
        importance=args.importance,
        reflection=args.note,
        confidence=args.confidence,
        evidence_ids=args.evidence,
        tool=args.tool,
        tool_args=tool_args,
        tool_output=args.tool_output,
        duration_ms=args.duration_ms,
        exit_code=args.exit_code,
    ))


if __name__ == "__main__":
    main()
