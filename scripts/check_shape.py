#!/usr/bin/env python3
"""Assert that we only ever *removed* things from the base, never reshaped one.

Until now, fidelity to the base was a single boolean: strip prose from both
documents, compare the trees, get True. That stops working the moment we drop
an operation on purpose. This replaces it with a per-operation and
per-component comparison plus an explicit allow-list, so the claim survives
deliberate divergence:

    every operation and component that still exists is structurally identical
    to the base, and everything that differs is listed with a reason

The allow-list is the point. A removal that nobody wrote down fails here, which
is what stops "drop the control-plane endpoints" from quietly taking a schema
somebody still needed with it.

Usage:
    scripts/check_shape.py                       # skips if the base is absent
    scripts/check_shape.py --require-base        # CI: absent base is a failure
    scripts/check_shape.py --suggest             # print allow-list YAML to paste
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import (  # noqa: E402
    HTTP_METHODS,
    Stripper,
    drop_null_defaults,
    load_tag_map,
)

ROOT = Path(__file__).resolve().parent.parent
DELTA = ROOT / "_project" / "base-delta.yaml"

# Component sections worth comparing. Anything keyed by an author-chosen name
# whose contents are structural.
COMPONENT_SECTIONS = (
    "schemas",
    "parameters",
    "requestBodies",
    "responses",
    "headers",
    "securitySchemes",
    "links",
    "callbacks",
)


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------

def rename_tags(spec, rename: dict) -> None:
    """Apply tags-map.yaml renames to the base, so tag IA is not a difference."""
    for _, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict) and op.get("tags"):
                op["tags"] = list(dict.fromkeys(rename.get(t, t) for t in op["tags"]))


def strip_key(node, key: str) -> None:
    if isinstance(node, dict):
        node.pop(key, None)
        for value in node.values():
            strip_key(value, key)
    elif isinstance(node, list):
        for value in node:
            strip_key(value, key)


def normalise(spec, options: set[str], rename: dict):
    """Remove the differences we have already decided are intentional.

    Each entry here is a decision that was made once and should not have to be
    re-argued on every run. Adding one is how a future sweeping change stops
    being reported as drift -- so an entry is a commitment, not a convenience.
    """
    out = Stripper().walk(spec) if "prose" in options else spec
    if "null-defaults" in options:
        drop_null_defaults(out)
    if "provenance" in options:
        strip_key(out, "x-airs-provenance")
    if "security" in options:
        # Both halves of the change, or the check reports half of it. `security`
        # is the requirement on each operation; `securitySchemes` is what the
        # requirement names. Six schemes in five combinations became one bearer
        # token, which is an auth decision rather than a reshape of the API.
        strip_key(out, "security")
        (out.get("components") or {}).pop("securitySchemes", None)
    if "servers" in options:
        strip_key(out, "servers")
    if "tags" in options:
        rename_tags(out, rename)
    return out


# --------------------------------------------------------------------------
# indexing
# --------------------------------------------------------------------------

def index_operations(spec) -> dict[str, str]:
    """{"post /chat/completions": canonical-json-of-its-shape}

    Path-item level `parameters` and `servers` are folded into each operation
    that inherits them, so a change made one level up cannot hide from a
    per-operation comparison.
    """
    out = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        inherited = {k: v for k, v in item.items() if k in ("parameters", "servers")}
        for method, op in item.items():
            if method not in HTTP_METHODS or not isinstance(op, dict):
                continue
            shape = {**inherited, **op}
            out[f"{method} {path}"] = json.dumps(shape, sort_keys=True)
    return out


def index_components(spec) -> dict[str, str]:
    out = {}
    components = spec.get("components") or {}
    for section in COMPONENT_SECTIONS:
        for name, value in (components.get(section) or {}).items():
            out[f"{section}/{name}"] = json.dumps(value, sort_keys=True)
    return out


# --------------------------------------------------------------------------
# comparison
# --------------------------------------------------------------------------

def allowed(entries) -> dict[str, str]:
    """[{id, reason}] -> {id: reason}. Also accepts bare strings."""
    out = {}
    for entry in entries or []:
        if isinstance(entry, str):
            out[entry] = ""
        else:
            out[entry["id"]] = entry.get("reason", "")
    return out


def compare(kind: str, base: dict, ours: dict, delta: dict, problems: list, suggest: dict):
    removed_ok = allowed(delta.get(f"removed_{kind}"))
    added_ok = allowed(delta.get(f"added_{kind}"))
    reshaped_ok = allowed(delta.get(f"reshaped_{kind}"))

    removed = sorted(set(base) - set(ours))
    added = sorted(set(ours) - set(base))
    reshaped = sorted(k for k in set(base) & set(ours) if base[k] != ours[k])

    suggest[f"removed_{kind}"] = removed
    suggest[f"added_{kind}"] = added
    suggest[f"reshaped_{kind}"] = reshaped

    for key in removed:
        if key not in removed_ok:
            problems.append(f"{kind}: removed without an allow-list entry -- {key}")
    for key in added:
        if key not in added_ok:
            problems.append(f"{kind}: added without an allow-list entry -- {key}")
    for key in reshaped:
        if key not in reshaped_ok:
            problems.append(f"{kind}: RESHAPED -- {key}")

    # A stale allow-list is how the guardrail rots: an entry left behind after
    # the thing came back keeps excusing a difference nobody re-checked.
    for key in removed_ok:
        if key in ours:
            problems.append(f"{kind}: allow-listed as removed but present -- {key}")
    for key in added_ok:
        if key in base and key in ours:
            problems.append(f"{kind}: allow-listed as added but exists in the base -- {key}")
    for key in reshaped_ok:
        if key in base and key in ours and base[key] == ours[key]:
            problems.append(f"{kind}: allow-listed as reshaped but identical -- {key}")

    kept = len(set(base) & set(ours)) - len(reshaped)
    print(f"  {kind:11} base {len(base):4}   ours {len(ours):4}   "
          f"identical {kept:4}   removed {len(removed):3}   "
          f"added {len(added):3}   reshaped {len(reshaped):3}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=ROOT / ".source" / "portkey-openapi.yaml")
    parser.add_argument("--spec", type=Path, default=ROOT / "openapi.yaml")
    parser.add_argument("--delta", type=Path, default=DELTA)
    parser.add_argument("--require-base", action="store_true",
                        help="fail if the base is not present (use in CI)")
    parser.add_argument("--suggest", action="store_true",
                        help="print the differences as allow-list YAML")
    args = parser.parse_args()

    if not args.base.exists():
        message = (f"base specification not found at {args.base}\n"
                   f"        fetch it with scripts/fetch-base.sh")
        if args.require_base:
            print(f"FAIL    {message}")
            return 1
        print(f"skip    {message}")
        return 0

    delta = yaml.safe_load(args.delta.read_text()) if args.delta.exists() else {}
    options = set(delta.get("normalise") or ["prose", "provenance", "tags", "null-defaults"])
    _, rename, _ = load_tag_map(ROOT / "tags-map.yaml")

    print(f"base    {args.base}")
    if delta.get("base", {}).get("commit"):
        print(f"commit  {delta['base']['commit']}")
    print(f"ignore  {', '.join(sorted(options))}")
    print()

    base = normalise(yaml.safe_load(args.base.read_text()), options, rename)
    ours = normalise(yaml.safe_load(args.spec.read_text()), options, rename)

    problems: list[str] = []
    suggest: dict[str, list[str]] = {}
    compare("operations", index_operations(base), index_operations(ours),
            delta, problems, suggest)
    compare("components", index_components(base), index_components(ours),
            delta, problems, suggest)

    if args.suggest:
        print("\n--- paste into _project/base-delta.yaml, with a reason each ---")
        for key, values in suggest.items():
            if not values:
                continue
            print(f"\n{key}:")
            for value in values:
                print(f"  - id: {json.dumps(value)}\n    reason: \"\"")
        return 0

    print()
    if problems:
        print(f"FAIL    {len(problems)} unexplained difference(s) from the base\n")
        for problem in problems[:60]:
            print(f"        {problem}")
        if len(problems) > 60:
            print(f"        ... and {len(problems) - 60} more")
        print("\n        Run with --suggest to generate allow-list entries.")
        print("        A RESHAPED operation is the serious one: structure was")
        print("        supposed to be inherited, not edited.")
        return 1

    print("OK      every surviving operation and component matches the base,")
    print("        and every difference is accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
