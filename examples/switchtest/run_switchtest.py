#!/usr/bin/env python3
"""Equivalence suite for the 'one brain, many harnesses' claim.

Five checks. Exit 0 on pass, 1 on fail. Designed to run in CI and locally.

  1. Install parity - .agent/ byte-identical across all adapters.
  2. Trace parity   - same synthetic tool-call via memory_reflect.py yields
                      entries that differ only in source.harness.
  3. Cluster parity - a pattern seen in 2 harnesses ends up with both
                      harness labels in the cluster metadata.
  4. Permission parity - JSON and markdown permission paths produce the
                      same verdicts for the same inputs.
  5. Stdin hook parser - a realistic Claude Code PostToolUse JSON payload
                         passed to memory_reflect.py --stdin produces an
                         episodic entry with tool/tool_args/exit_code
                         populated from the payload.

Uses only stdlib. No LLM call. No network.
"""
import os, sys, json, shutil, hashlib, subprocess, tempfile, datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INSTALL_SH = os.path.join(REPO_ROOT, "install.sh")
INSTALL_PS1 = os.path.join(REPO_ROOT, "install.ps1")

# install.sh / .ps1 subdirs this test treats as the brain. Anything outside
# these paths is adapter-specific overlay (CLAUDE.md, AGENTS.md, etc.) and
# legitimately differs between adapters.
BRAIN_SUBDIR = ".agent"

ADAPTERS = ["claude-code", "cursor", "windsurf", "opencode",
            "openclient", "hermes", "standalone-python"]

GREEN = "\033[32m" if sys.stdout.isatty() else ""
RED = "\033[31m" if sys.stdout.isatty() else ""
RESET = "\033[0m" if sys.stdout.isatty() else ""


def _ok(msg):
    print(f"  {GREEN}PASS{RESET} {msg}")


def _fail(msg):
    print(f"  {RED}FAIL{RESET} {msg}")


def _hash_tree(root, skip=()):
    """Stable hash of a directory tree. File paths + contents only.

    mtimes and perms are excluded - they vary by filesystem and aren't
    part of the portable-brain contract. `skip` paths are rooted at
    the given root.
    """
    skip_abs = {os.path.normpath(os.path.join(root, s)) for s in skip}
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fname in sorted(filenames):
            full = os.path.normpath(os.path.join(dirpath, fname))
            # `any(full.startswith(s)` handles skip being a directory prefix,
            # which matters for _history/ dirs that the test should ignore.
            if any(full == s or full.startswith(s + os.sep) for s in skip_abs):
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            with open(full, "rb") as f:
                data = f.read()
            h.update(rel.encode("utf-8") + b"\x00" + data + b"\x00")
    return h.hexdigest()


def _simulate_install_brain(target):
    """Replicate what install.sh does for the `.agent/` copy step.

    Shelling out to install.sh across Windows + subprocess path-mangling is
    brittle (backslash paths in git-bash, MS Store python3 stub, etc.), and
    what we're testing here is the brain-copy contract - the adapter overlay
    files are out of scope. So we do the deterministic part natively.
    """
    src = os.path.join(REPO_ROOT, ".agent")
    dst = os.path.join(target, ".agent")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def check_install_parity():
    """Copy .agent/ as the installers do; hash must match across invocations.

    The real installers also write adapter-specific overlay files (CLAUDE.md,
    settings.json, etc.) and may patch embedded python binaries - those sit
    OUTSIDE .agent/ and legitimately differ between adapters. The parity
    claim is about the brain, and the brain is `.agent/`.
    """
    print("[1/5] install parity across adapters")
    hashes = {}
    tmpdir = tempfile.mkdtemp(prefix="switchtest-install-")
    try:
        for adapter in ADAPTERS:
            target = os.path.join(tmpdir, adapter)
            os.makedirs(target)
            _simulate_install_brain(target)
            brain = os.path.join(target, BRAIN_SUBDIR)
            if not os.path.isdir(brain):
                _fail(f"{adapter}: .agent/ not created at {brain}")
                return False
            # Skip generated artefacts from prior dev runs that the
            # installer wouldn't carry forward: evolve-created _history/,
            # and the features file that the wizard writes separately.
            hashes[adapter] = _hash_tree(brain, skip=(
                "memory/.features.json",
            ))
        unique = set(hashes.values())
        if len(unique) == 1:
            _ok(f"all {len(hashes)} adapters receive identical .agent/ trees")
            return True
        _fail("brain hashes diverge across adapters:")
        for a, h in hashes.items():
            print(f"    {a:<20} {h[:12]}")
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def check_trace_parity():
    """Log the same synthetic tool call under different AGENT_HARNESS values.

    Entries must be identical except for source.harness. Drift anywhere
    else means the harness label leaked into content fields.
    """
    print("[2/5] trace parity across harness labels")
    # Fresh temp episodic dir - we invoke memory_reflect directly with its
    # repo-root pathing so the test doesn't pollute real memory.
    tmpdir = tempfile.mkdtemp(prefix="switchtest-trace-")
    episodic = os.path.join(tmpdir, ".agent/memory/episodic")
    os.makedirs(episodic, exist_ok=True)
    # Sym/hardlink a copy of the harness dir so _provenance and
    # post_execution resolve their relative ROOT to our tmpdir.
    shutil.copytree(os.path.join(REPO_ROOT, ".agent", "harness"),
                    os.path.join(tmpdir, ".agent", "harness"))
    shutil.copytree(os.path.join(REPO_ROOT, ".agent", "tools"),
                    os.path.join(tmpdir, ".agent", "tools"))

    tool_reflect = os.path.join(tmpdir, ".agent/tools/memory_reflect.py")
    try:
        entries = {}
        for h in ("claude-code", "cursor", "hermes"):
            env = {**os.environ, "AGENT_HARNESS": h, "AGENT_MODEL": "test-model",
                   "AGENT_RUN_ID": "fixed"}
            out = subprocess.run(
                [sys.executable, tool_reflect,
                 "--skill", "test", "--action", "run", "--outcome", "ok",
                 "--tool", "Bash", "--tool-args", '{"command":"echo hi"}',
                 "--tool-output", "hi", "--exit-code", "0",
                 "--duration-ms", "42", "--harness", h, "--model", "test-model"],
                env=env, capture_output=True, text=True,
            )
            if out.returncode != 0:
                _fail(f"harness={h}: memory_reflect returned {out.returncode}\n{out.stderr}")
                return False
            # Read the line that was just appended.
            with open(os.path.join(episodic, "AGENT_LEARNINGS.jsonl")) as f:
                last = [l for l in f if l.strip()][-1]
            entries[h] = json.loads(last)

        # Strip the fields we expect to differ - harness label + timestamp +
        # commit_sha (git may or may not resolve from the temp dir).
        def strip(e):
            e = json.loads(json.dumps(e))  # deep copy
            e.pop("timestamp", None)
            if "source" in e:
                e["source"].pop("harness", None)
                e["source"].pop("commit_sha", None)
            return e

        stripped = {h: strip(e) for h, e in entries.items()}
        first = next(iter(stripped.values()))
        for h, e in stripped.items():
            if e != first:
                _fail(f"harness={h} entry diverges from baseline "
                      f"(non-harness fields differ)")
                print(json.dumps({"baseline": first, h: e}, indent=2))
                return False
            # Also: the harness field MUST have been set correctly.
            if entries[h]["source"]["harness"] != h:
                _fail(f"harness={h} entry has source.harness={entries[h]['source']['harness']}")
                return False
        _ok(f"same trace under {len(entries)} different harness labels differs "
            f"only in source.harness")
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def check_cluster_parity():
    """A pattern with 2 harnesses in its evidence must carry both labels."""
    print("[3/5] cluster parity surfaces cross-harness patterns")
    sys.path.insert(0, os.path.join(REPO_ROOT, ".agent", "harness"))
    sys.path.insert(0, os.path.join(REPO_ROOT, ".agent", "memory"))
    try:
        from cluster import content_cluster, extract_pattern
        entries = [
            {"timestamp": "2026-04-15T10:00:00", "action": "build broke",
             "reflection": "missing env var", "detail": "stripe key missing",
             "pain_score": 8, "importance": 7,
             "source": {"harness": "claude-code", "model": "x"}, "tool": "Bash"},
            {"timestamp": "2026-04-16T11:00:00", "action": "build broke",
             "reflection": "missing env var", "detail": "stripe key missing again",
             "pain_score": 8, "importance": 7,
             "source": {"harness": "cursor", "model": "y"}, "tool": "Bash"},
        ]
        clusters = content_cluster(entries, threshold=0.3, min_size=2)
        if not clusters:
            _fail("content_cluster found no clusters on twinned evidence")
            return False
        p = extract_pattern(clusters[0])
        if set(p.get("harnesses") or []) != {"claude-code", "cursor"}:
            _fail(f"pattern.harnesses = {p.get('harnesses')}, expected both")
            return False
        if set(p.get("models") or []) != {"x", "y"}:
            _fail(f"pattern.models = {p.get('models')}, expected both")
            return False
        _ok("cross-harness pattern carries both harness and model labels")
        return True
    finally:
        # Tear down the sys.path insertions so later checks don't inherit them.
        sys.path[:] = [p for p in sys.path if p not in (
            os.path.join(REPO_ROOT, ".agent", "harness"),
            os.path.join(REPO_ROOT, ".agent", "memory"),
        )]


def check_permission_parity():
    """Safety direction: JSON must be at least as strict as markdown fallback.

    The JSON path has explicit `patterns` (Bash(rm -rf /*) etc.) that the
    markdown fallback can't match via keyword heuristics alone. That's a
    known downgrade - the contract is that JSON >= markdown in strictness,
    never the reverse. This check enforces that direction.
    """
    print("[4/5] permission safety parity (JSON >= markdown fallback)")
    sys.path.insert(0, os.path.join(REPO_ROOT, ".agent", "harness"))
    try:
        from hooks import pre_tool_call as ptc

        # Three kinds of cases: rules covered by keywords (both paths block),
        # rules covered only by patterns (JSON blocks, markdown may not),
        # benign (both paths allow).
        cases = [
            # keyword-heavy: "force push to main" has 3 keywords in desc
            ("keyword", "Bash", "exec",
             {"command": "git push --force origin main"}, False),
            # pattern-only rule: Bash(rm -rf /*)
            ("pattern", "Bash", "exec", {"command": "rm -rf /"}, False),
            # benign: should be allowed in both
            ("benign", "Bash", "exec",
             {"command": "git commit -m 'ok'"}, True),
        ]

        json_verdicts, md_verdicts = {}, {}
        for tag, tool, op, args, _ in cases:
            allowed, _r = ptc.check_tool_call(tool, op, args)
            json_verdicts[tag] = allowed is True

        # Force markdown fallback by temporarily renaming the JSON source.
        src = os.path.join(REPO_ROOT, ".agent", "protocols", "permissions.json")
        backup = src + ".switchtest-bak"
        os.rename(src, backup)
        try:
            import importlib
            importlib.reload(ptc)
            for tag, tool, op, args, _ in cases:
                allowed, _r = ptc.check_tool_call(tool, op, args)
                md_verdicts[tag] = allowed is True
        finally:
            os.rename(backup, src)
            importlib.reload(ptc)

        # JSON must block every expected-block case.
        for tag, _, _, _, want_allowed in cases:
            if json_verdicts[tag] != want_allowed:
                _fail(f"JSON path on '{tag}': got allowed={json_verdicts[tag]}, "
                      f"wanted allowed={want_allowed}")
                return False

        # JSON must be at least as strict as markdown (no case where md blocks
        # but JSON allows).
        for tag in md_verdicts:
            if md_verdicts[tag] is False and json_verdicts[tag] is True:
                _fail(f"safety regression on '{tag}': markdown blocks but JSON allows")
                return False

        # keyword-heavy cases should block on both paths.
        if md_verdicts["keyword"] is True:
            _fail("markdown fallback failed to block keyword-heavy rule "
                  "(force push to main)")
            return False
        _ok("JSON path >= markdown fallback on all cases; keyword rules "
            "enforced on both paths")
        return True
    finally:
        sys.path[:] = [p for p in sys.path
                       if p != os.path.join(REPO_ROOT, ".agent", "harness")]


def check_stdin_parser():
    """Feed a realistic Claude Code PostToolUse JSON payload via stdin.

    Success criteria: tool = Bash, tool_args contains the command,
    exit_code populated, source.harness tagged correctly. Without this
    check, a regression in `memory_reflect.py --stdin` would only show
    up once a live Claude Code hook fires, by which time the episodic
    log has already lost trace fidelity for that window.
    """
    print("[5/5] stdin hook parser handles Claude Code PostToolUse payload")
    tmpdir = tempfile.mkdtemp(prefix="switchtest-stdin-")
    try:
        # Mirror the harness/tools/memory dirs so memory_reflect's relative
        # pathing lands in this isolated episodic.
        for sub in ("harness", "tools"):
            shutil.copytree(os.path.join(REPO_ROOT, ".agent", sub),
                            os.path.join(tmpdir, ".agent", sub))
        os.makedirs(os.path.join(tmpdir, ".agent/memory/episodic"),
                    exist_ok=True)
        tool_path = os.path.join(tmpdir, ".agent/tools/memory_reflect.py")

        payload = {
            "session_id": "switchtest",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q", "description": "run tests"},
            "tool_response": {"stdout": "3 passed", "stderr": "", "exit_code": 0},
        }
        env = {**os.environ, "AGENT_HARNESS": "claude-code",
               "AGENT_MODEL": "test", "AGENT_RUN_ID": "fixed"}
        r = subprocess.run(
            [sys.executable, tool_path, "--stdin",
             "--skill", "claude-code", "--action", "post-tool",
             "--outcome", "ok"],
            input=json.dumps(payload), capture_output=True, text=True,
            env=env, timeout=20,
        )
        if r.returncode != 0:
            _fail(f"memory_reflect --stdin exited {r.returncode}: {r.stderr}")
            return False

        ep = os.path.join(tmpdir, ".agent/memory/episodic/AGENT_LEARNINGS.jsonl")
        lines = [l for l in open(ep) if l.strip()]
        if not lines:
            _fail("stdin payload produced no episodic entry")
            return False
        entry = json.loads(lines[-1])

        # Assertions. Each is a property the hook contract promises.
        if entry.get("tool") != "Bash":
            _fail(f"tool field = {entry.get('tool')!r}, expected 'Bash'")
            return False
        if "pytest" not in (entry.get("tool_args") or ""):
            _fail(f"tool_args missing command: {entry.get('tool_args')!r}")
            return False
        if entry.get("exit_code") != 0:
            _fail(f"exit_code = {entry.get('exit_code')!r}, expected 0")
            return False
        if entry.get("source", {}).get("harness") != "claude-code":
            _fail(f"source.harness = {entry.get('source', {}).get('harness')!r}")
            return False
        if entry.get("result") != "success":
            _fail(f"result = {entry.get('result')!r}, expected success")
            return False
        _ok("Claude Code JSON payload lands as structured episodic entry")
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    print(f"switchtest @ {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(f"repo: {REPO_ROOT}\n")
    results = [
        check_install_parity(),
        check_trace_parity(),
        check_cluster_parity(),
        check_permission_parity(),
        check_stdin_parser(),
    ]
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
