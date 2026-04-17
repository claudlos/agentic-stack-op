"""Merge permissions.json deny patterns into a target Claude Code settings.json.

Runs during adapter install (and whenever permissions.json changes) so the
Claude Code permission engine sees the exact same deny list the
pre_tool_call hook enforces. Without this, the two can drift - a new rule
added to permissions.json would be enforced by the hook at tool-call time
but NOT by Claude Code's own UI-level block, leading to inconsistent
gating.

Usage:
  render_claude_settings.py <path-to-target-settings.json>

Writes in-place. Preserves every setting key other than
`permissions.deny`; that one is owned by this script.
"""
import os, sys, json


SENTINEL_COMMENT_KEY = "_generated_by_agentic_stack"


def _base_permissions_path():
    # This script lives in .agent/tools/ - climb to find permissions.json
    # without demanding a specific repo layout. Lets it run both from an
    # installed `.agent/` and from the source tree.
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(here, "..", "protocols", "permissions.json"))
    return candidate


def _collect_deny(policy):
    """Flatten explicit Bash(...) patterns across all never_allowed blocks."""
    patterns = []
    for block in policy.get("never_allowed", []):
        if isinstance(block, dict):
            patterns.extend(block.get("patterns", []))
    seen, out = set(), []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def merge(settings_path, permissions_path=None):
    if not os.path.exists(settings_path):
        print(f"error: settings.json not found: {settings_path}", file=sys.stderr)
        return 1
    pol_path = permissions_path or _base_permissions_path()
    if not os.path.exists(pol_path):
        print(f"error: permissions.json not found: {pol_path}", file=sys.stderr)
        return 1

    with open(pol_path) as f:
        policy = json.load(f)
    deny = _collect_deny(policy)

    with open(settings_path) as f:
        settings = json.load(f)

    perms = settings.setdefault("permissions", {})
    perms["deny"] = deny
    # Leave a breadcrumb so humans reading settings.json know the list is
    # auto-generated and where to look for the source.
    perms[SENTINEL_COMMENT_KEY] = (
        "permissions.deny is generated from .agent/protocols/permissions.json "
        "by .agent/tools/render_claude_settings.py - edit the JSON, not this file."
    )

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print(f"merged {len(deny)} deny pattern(s) into {settings_path}")
    return 0


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) < 1:
        print("usage: render_claude_settings.py <path-to-settings.json> "
              "[path-to-permissions.json]", file=sys.stderr)
        return 2
    settings_path = argv[0]
    pol_path = argv[1] if len(argv) > 1 else None
    return merge(settings_path, pol_path)


if __name__ == "__main__":
    sys.exit(main())
