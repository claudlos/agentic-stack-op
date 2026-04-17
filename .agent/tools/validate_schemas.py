"""Validate permissions.json and per-skill eval.json files against their shape.

Stdlib-only - no jsonschema dep. The checks catch the class of bug we care
about: typos in top-level keys, wrong types, unknown fields that silently
downgrade behaviour. Full JSON Schema semantics (oneOf, format, etc.) are
left to external tooling.

Exit 0 on clean, 2 on any validation failure.

Usage:
  validate_schemas.py            # validate everything under .agent/
  validate_schemas.py --verbose  # print each file as it passes
"""
import os, sys, json, argparse

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PERMISSIONS = os.path.join(BASE, "protocols", "permissions.json")
SKILLS_DIR = os.path.join(BASE, "skills")


# ── permissions.json expected shape ───────────────────────────────────────

_PERM_TOP_REQUIRED = {"version", "always_allowed", "requires_approval",
                      "never_allowed"}
_PERM_TOP_ALLOWED = _PERM_TOP_REQUIRED | {"$schema", "note", "approved_domains"}
_PERM_BLOCK_ALLOWED = {"rule", "patterns", "targets", "keywords"}


def _validate_permissions(path, errors):
    try:
        with open(path) as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"{path}: cannot parse ({e})")
        return
    if not isinstance(doc, dict):
        errors.append(f"{path}: top level must be an object")
        return
    missing = _PERM_TOP_REQUIRED - doc.keys()
    if missing:
        errors.append(f"{path}: missing required keys: {sorted(missing)}")
    unknown = doc.keys() - _PERM_TOP_ALLOWED
    if unknown:
        errors.append(f"{path}: unknown top-level keys: {sorted(unknown)}  "
                      f"(typo? allowed: {sorted(_PERM_TOP_ALLOWED)})")
    if not isinstance(doc.get("version"), int) or doc["version"] < 1:
        errors.append(f"{path}: version must be a positive integer")
    for key in ("always_allowed", "requires_approval"):
        if key in doc and not isinstance(doc[key], list):
            errors.append(f"{path}: {key} must be an array")
    never = doc.get("never_allowed", [])
    if not isinstance(never, list):
        errors.append(f"{path}: never_allowed must be an array")
    else:
        for i, block in enumerate(never):
            where = f"{path} never_allowed[{i}]"
            if isinstance(block, str):
                continue  # legacy shape - allowed
            if not isinstance(block, dict):
                errors.append(f"{where}: must be string or object")
                continue
            if "rule" not in block or not isinstance(block["rule"], str):
                errors.append(f"{where}: missing or non-string 'rule'")
            extra = block.keys() - _PERM_BLOCK_ALLOWED
            if extra:
                errors.append(f"{where}: unknown keys: {sorted(extra)}  "
                              f"(allowed: {sorted(_PERM_BLOCK_ALLOWED)})")
            # Pattern shape: Tool(glob). Catch the class of bug where
            # someone writes a raw glob without the Tool() wrapper, which
            # would silently never match.
            for p in block.get("patterns", []):
                if not (isinstance(p, str) and "(" in p and p.endswith(")")):
                    errors.append(f"{where}: pattern {p!r} must look like "
                                  f"Tool(glob) - e.g. Bash(git push --force*)")


# ── eval.json expected shape ──────────────────────────────────────────────

_EVAL_ALLOWED = {
    "$schema", "required_sections", "required_frontmatter",
    "forbidden_patterns", "preserved_constraints", "trigger_coverage",
    "failure_references", "length_bounds",
}
_EVAL_LIST_OF_STR = {"required_sections", "required_frontmatter",
                     "forbidden_patterns", "preserved_constraints"}


def _validate_eval(path, errors):
    try:
        with open(path) as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"{path}: cannot parse ({e})")
        return
    if not isinstance(doc, dict):
        errors.append(f"{path}: top level must be an object")
        return
    unknown = doc.keys() - _EVAL_ALLOWED
    if unknown:
        errors.append(f"{path}: unknown keys: {sorted(unknown)}  "
                      f"(allowed: {sorted(_EVAL_ALLOWED)})")
    for key in _EVAL_LIST_OF_STR:
        if key in doc:
            val = doc[key]
            if not (isinstance(val, list) and
                    all(isinstance(x, str) for x in val)):
                errors.append(f"{path}: {key} must be array of strings")
    if "trigger_coverage" in doc:
        tc = doc["trigger_coverage"]
        if not isinstance(tc, list):
            errors.append(f"{path}: trigger_coverage must be array of arrays")
        else:
            for i, group in enumerate(tc):
                if not (isinstance(group, list) and group and
                        all(isinstance(x, str) for x in group)):
                    errors.append(f"{path}: trigger_coverage[{i}] must be "
                                  f"a non-empty array of strings")
    if "failure_references" in doc:
        fr = doc["failure_references"]
        if not isinstance(fr, list):
            errors.append(f"{path}: failure_references must be array")
        else:
            for i, ref in enumerate(fr):
                if not isinstance(ref, dict):
                    errors.append(f"{path}: failure_references[{i}] must be object")
                    continue
                kws = ref.get("keywords")
                if not (isinstance(kws, list) and kws and
                        all(isinstance(x, str) for x in kws)):
                    errors.append(f"{path}: failure_references[{i}].keywords "
                                  f"must be non-empty array of strings")
                if "min_count" in ref and not isinstance(ref["min_count"], int):
                    errors.append(f"{path}: failure_references[{i}].min_count "
                                  f"must be int")
                extra = ref.keys() - {"keywords", "min_count"}
                if extra:
                    errors.append(f"{path}: failure_references[{i}] "
                                  f"unknown keys: {sorted(extra)}")
    if "length_bounds" in doc:
        lb = doc["length_bounds"]
        if not isinstance(lb, dict):
            errors.append(f"{path}: length_bounds must be object")
        else:
            for key in ("min_chars", "max_chars"):
                if key in lb and not isinstance(lb[key], int):
                    errors.append(f"{path}: length_bounds.{key} must be int")
            extra = lb.keys() - {"min_chars", "max_chars"}
            if extra:
                errors.append(f"{path}: length_bounds unknown keys: "
                              f"{sorted(extra)}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    errors = []
    checked = 0

    if os.path.exists(PERMISSIONS):
        _validate_permissions(PERMISSIONS, errors)
        checked += 1
        if args.verbose and not errors:
            print(f"ok: {PERMISSIONS}")

    if os.path.isdir(SKILLS_DIR):
        for name in sorted(os.listdir(SKILLS_DIR)):
            eval_path = os.path.join(SKILLS_DIR, name, "evals", "eval.json")
            if os.path.isfile(eval_path):
                before = len(errors)
                _validate_eval(eval_path, errors)
                checked += 1
                if args.verbose and len(errors) == before:
                    print(f"ok: {eval_path}")

    if errors:
        print(f"\nFAIL - {len(errors)} error(s) across {checked} file(s):",
              file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)
    print(f"ok: validated {checked} file(s)")


if __name__ == "__main__":
    main()
