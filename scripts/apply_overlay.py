#!/usr/bin/env python3
"""Apply OpenAPI Overlay 1.0.0 documents to a specification.

Mintlify applies overlays at build time; this reproduces that locally and in CI
so a broken overlay is caught here rather than on the docs site.

Usage:
    scripts/apply_overlay.py openapi.yaml overlays/*.yaml -o build/openapi.resolved.yaml
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import yaml
from jsonpath_ng.ext import parse


def merge(target, update):
    """Overlay `update` semantics: recursive merge, scalars and lists replace."""
    if isinstance(target, dict) and isinstance(update, dict):
        for key, value in update.items():
            if key in target:
                target[key] = merge(target[key], value)
            else:
                target[key] = copy.deepcopy(value)
        return target
    return copy.deepcopy(update)


def apply(spec, overlay, *, strict=True):
    """Returns (spec, [unresolved target descriptions])."""
    unresolved = []
    for index, action in enumerate(overlay.get("actions", [])):
        target = action.get("target")
        if not target:
            raise ValueError(f"action {index}: missing target")

        matches = parse(target).find(spec)
        if not matches:
            unresolved.append(target)
            continue

        for match in matches:
            if "remove" in action and action["remove"]:
                path = match.full_path
                parent = path.left.find(spec)[0].value if hasattr(path, "left") else None
                if isinstance(parent, dict):
                    parent.pop(str(path.right), None)
                continue
            merge(match.value, action.get("update", {}))

    if unresolved and strict:
        raise ValueError(
            "overlay targets matched nothing:\n  " + "\n  ".join(unresolved)
        )
    return spec, unresolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("overlays", nargs="+", type=Path)
    parser.add_argument("-o", "--out", type=Path)
    args = parser.parse_args()

    spec = yaml.safe_load(args.spec.read_text())
    for path in args.overlays:
        overlay = yaml.safe_load(path.read_text())
        if overlay.get("overlay") != "1.0.0":
            print(f"error: {path} is not an Overlay 1.0.0 document", file=sys.stderr)
            return 1
        spec, _ = apply(spec, overlay)
        print(f"applied {len(overlay.get('actions', []))} actions from {path}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
