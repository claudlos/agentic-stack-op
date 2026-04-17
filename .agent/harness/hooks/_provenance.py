"""Shared provenance helpers for episodic entries. Cached per-process.

Provenance = who/what/where produced this entry. Lets cross-harness
clustering (cluster.py) surface patterns that are harness-specific and lets
the evolve loop (tools/evolve.py) attribute a failure to the right harness +
model combo rather than blaming the skill in isolation.
"""
import os, subprocess

AGENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

_CACHED_COMMIT = None
_CACHED_RUN_ID = None
_CACHED_HARNESS = None
_CACHED_MODEL = None


def run_id():
    global _CACHED_RUN_ID
    if _CACHED_RUN_ID is None:
        _CACHED_RUN_ID = os.environ.get("AGENT_RUN_ID", f"pid-{os.getpid()}")
    return _CACHED_RUN_ID


def commit_sha():
    global _CACHED_COMMIT
    if _CACHED_COMMIT is None:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=2,
                cwd=AGENT_ROOT,
            )
            _CACHED_COMMIT = out.stdout.strip() if out.returncode == 0 else ""
        except Exception:
            _CACHED_COMMIT = ""
    return _CACHED_COMMIT


_KNOWN_HARNESSES = (
    "claude-code", "cursor", "windsurf", "opencode",
    "openclient", "hermes", "standalone-python",
)


def harness():
    """Which harness is running right now.

    Explicit env var wins (AGENT_HARNESS). Otherwise infer from harness-specific
    env markers — Claude Code sets CLAUDECODE=1; Cursor sets CURSOR_TRACE_ID;
    Windsurf sets WINDSURF_PROJECT; Hermes sets HERMES_SESSION_ID.
    Unknown is explicit, not silent, so cross-harness analysis can flag
    entries whose origin can't be attributed.
    """
    global _CACHED_HARNESS
    if _CACHED_HARNESS is not None:
        return _CACHED_HARNESS
    explicit = os.environ.get("AGENT_HARNESS", "").strip().lower()
    if explicit in _KNOWN_HARNESSES:
        _CACHED_HARNESS = explicit
        return _CACHED_HARNESS
    if os.environ.get("CLAUDECODE") == "1" or os.environ.get("CLAUDE_CODE"):
        _CACHED_HARNESS = "claude-code"
    elif os.environ.get("CURSOR_TRACE_ID") or os.environ.get("CURSOR"):
        _CACHED_HARNESS = "cursor"
    elif os.environ.get("WINDSURF_PROJECT") or os.environ.get("WINDSURF"):
        _CACHED_HARNESS = "windsurf"
    elif os.environ.get("HERMES_SESSION_ID") or os.environ.get("HERMES"):
        _CACHED_HARNESS = "hermes"
    elif os.environ.get("OPENCODE"):
        _CACHED_HARNESS = "opencode"
    elif os.environ.get("OPENCLIENT"):
        _CACHED_HARNESS = "openclient"
    else:
        _CACHED_HARNESS = "unknown"
    return _CACHED_HARNESS


def model():
    """Which model is behind this session, best-effort.

    AGENT_MODEL is the canonical signal. Falls back to provider-specific
    envs so the majority of harnesses get populated without per-harness
    glue code. Never blocks logging — returns 'unknown' if nothing matches.
    """
    global _CACHED_MODEL
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL
    for var in ("AGENT_MODEL", "CLAUDE_MODEL", "ANTHROPIC_MODEL",
                "OPENAI_MODEL", "OPENROUTER_MODEL", "MODEL"):
        v = os.environ.get(var, "").strip()
        if v:
            _CACHED_MODEL = v
            return _CACHED_MODEL
    _CACHED_MODEL = "unknown"
    return _CACHED_MODEL


def build_source(skill):
    return {
        "skill": skill,
        "run_id": run_id(),
        "commit_sha": commit_sha(),
        "harness": harness(),
        "model": model(),
    }
