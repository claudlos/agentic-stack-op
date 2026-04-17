"""Runs before every tool call. Enforces permissions and tool schemas.

Reads `protocols/permissions.json` (the policy source of truth) rather than
regex'ing the rendered markdown. That means: deny rules stay deterministic
even when the markdown formatting drifts, and the same policy that gates
Claude Code's `settings.json.permissions.deny` gates the standalone path too.
"""
import json, os, re, fnmatch

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _schema(tool_name):
    p = os.path.join(ROOT, "protocols/tool_schemas", f"{tool_name}.schema.json")
    if not os.path.exists(p):
        return {}
    return json.load(open(p))


def _load_policy():
    """Prefer the JSON source; fall back to rendered markdown for back-compat.

    Old installs that haven't regenerated yet still get the deny behaviour
    from the markdown fallback, just with coarser matching. The JSON path
    is the forward direction.
    """
    j = os.path.join(ROOT, "protocols/permissions.json")
    if os.path.exists(j):
        try:
            with open(j) as f:
                return json.load(f), "json"
        except (OSError, json.JSONDecodeError):
            pass
    md = os.path.join(ROOT, "protocols/permissions.md")
    if os.path.exists(md):
        return {"never_allowed_md": open(md).read()}, "markdown"
    return {}, "none"


def _matches_bash_pattern(pattern, tool_name, args):
    """Match a Claude-Code-style Bash(...) pattern against a call.

    Supports `Bash(git push --force*)` shape — tool name, then a parenthesized
    glob against the full command text. Any other pattern format falls
    through to False so we don't pretend to match what we can't parse.
    """
    m = re.match(r"^([A-Za-z_]+)\((.+)\)$", pattern)
    if not m:
        return False
    tool_in_pat = m.group(1)
    glob = m.group(2)
    if tool_in_pat.lower() != tool_name.lower():
        return False
    # Search common arg shapes for the command string. Different callers use
    # different field names; try each rather than demanding a canonical shape.
    command = ""
    if isinstance(args, dict):
        for key in ("command", "cmd", "bash", "script"):
            if key in args:
                command = str(args[key])
                break
    elif isinstance(args, str):
        command = args
    if not command:
        return False
    return fnmatch.fnmatchcase(command, glob)


def _block_from_json(policy, tool_name, operation, args):
    """Return (blocked, reason) from JSON policy, or (None, None) if N/A."""
    desc = f"{tool_name} {operation} {json.dumps(args) if args else ''}".lower()
    for block in policy.get("never_allowed", []):
        if isinstance(block, str):
            rule = block
            keywords = [w for w in rule.lower().split() if len(w) > 3]
            if keywords and sum(1 for k in keywords if k in desc) >= 2:
                return True, f"BLOCKED by permission rule: {rule}"
            continue
        # Structured block.
        # 1) Exact pattern match on Bash(...) glob.
        for pat in block.get("patterns", []):
            if _matches_bash_pattern(pat, tool_name, args):
                return True, f"BLOCKED by permission rule: {block['rule']}"
        # 2) Target-list match (git push to main, etc.).
        target = (args.get("branch") or args.get("target") or args.get("env") or ""
                  if isinstance(args, dict) else "")
        if target and target in block.get("targets", []):
            return True, (f"BLOCKED: target '{target}' is in never_allowed "
                          f"list for rule: {block['rule']}")
        # 3) Keyword fallback — same heuristic as the old markdown path.
        kws = [w.lower() for w in block.get("keywords", []) if len(w) > 3]
        if kws and sum(1 for k in kws if k in desc) >= 2:
            return True, f"BLOCKED by permission rule: {block['rule']}"
    return None, None


def _block_from_markdown(md_text, tool_name, operation, args):
    if "## Never allowed" not in md_text:
        return None, None
    never = md_text.split("## Never allowed")[1].split("##")[0]
    desc = f"{tool_name} {operation} {json.dumps(args) if args else ''}".lower()
    for line in never.strip().splitlines():
        if not line.startswith("- "):
            continue
        rule = line[2:].lower()
        keywords = [w for w in rule.split() if len(w) > 3]
        if keywords and sum(1 for k in keywords if k in desc) >= 2:
            return True, f"BLOCKED by permission rule: {line[2:]}"
    return None, None


def check_tool_call(tool_name, operation, args):
    """Returns (allowed, reason). allowed may be True, False, or 'approval_needed'."""
    schema = _schema(tool_name)
    op = schema.get("operations", {}).get(operation, {})

    blocked = op.get("blocked_targets", [])
    target = args.get("branch") or args.get("target") or args.get("env") or ""
    if target and target in blocked:
        return False, f"BLOCKED: {operation} to '{target}' is forbidden"

    if op.get("requires_approval", False):
        return "approval_needed", f"{operation} requires human approval"

    policy, source = _load_policy()
    if source == "json":
        verdict, reason = _block_from_json(policy, tool_name, operation, args)
    elif source == "markdown":
        verdict, reason = _block_from_markdown(
            policy.get("never_allowed_md", ""), tool_name, operation, args)
    else:
        verdict, reason = None, None
    if verdict:
        return False, reason

    return True, "allowed"
