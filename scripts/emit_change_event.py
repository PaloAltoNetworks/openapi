#!/usr/bin/env python3
"""Build the `spec.changed` payload by diffing two revisions of the spec.

Classifies each operation's change so the KB can tell the interesting case from
the noise: `structure_changed` means the shape moved and any claim describing
its behaviour may now be stale. `prose_changed` alone means docs moved and the
KB probably already knows.

Usage:
    scripts/emit_change_event.py --base HEAD~1 --head HEAD -o build/event.json
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import HTTP_METHODS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def at_revision(rev: str, path: str):
    try:
        blob = subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    return yaml.safe_load(blob)


def index(spec):
    """{(method, path): operation}"""
    out = {}
    for path, item in (spec or {}).get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict):
                out[(method, path)] = op
    return out


def shape_of(op):
    """The operation with everything documentation-shaped removed.

    What remains is the machine-verifiable half. If this changes, the API
    changed, and that is what the KB needs to hear about.
    """
    stripped = copy.deepcopy(op)
    for key in ("summary", "description", "x-airs-provenance", "externalDocs"):
        stripped.pop(key, None)
    return json.dumps(stripped, sort_keys=True)


def classify(before, after) -> str | None:
    if before is None:
        return "added"
    if after is None:
        return "removed"
    if shape_of(before) != shape_of(after):
        return "structure_changed"
    if (before.get("x-airs-provenance") or {}) != (after.get("x-airs-provenance") or {}):
        return "provenance_changed"
    if (before.get("summary"), before.get("description")) != (
        after.get("summary"), after.get("description")
    ):
        return "prose_changed"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD~1")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repository", default="PaloAltoNetworks/openapi")
    parser.add_argument("--ref", default="refs/heads/main")
    parser.add_argument("-o", "--out", type=Path, default=Path("build/spec-changed.json"))
    args = parser.parse_args()

    before = index(at_revision(args.base, "openapi.yaml"))
    after = index(at_revision(args.head, "openapi.yaml"))

    changes = []
    for key in sorted(set(before) | set(after)):
        method, path = key
        change = classify(before.get(key), after.get(key))
        if not change:
            continue
        op = after.get(key) or before.get(key)
        prov = op.get("x-airs-provenance") or {}
        changes.append(
            {
                "operation_id": op.get("operationId"),
                "method": method,
                "path": path,
                "change": change,
                "claims": [
                    {"id": c.get("id"), "revision": c.get("revision")}
                    for c in prov.get("claims") or []
                ],
                "text_digest": prov.get("text_digest") or None,
            }
        )

    def sha(rev):
        try:
            return subprocess.run(
                ["git", "rev-parse", rev], cwd=ROOT,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            return None

    payload = {
        "event": "spec.changed",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "spec": {
            "repository": args.repository,
            "ref": args.ref,
            "commit": sha(args.head),
            "previous_commit": sha(args.base),
        },
        "operations": changes,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    kinds: dict[str, int] = {}
    for c in changes:
        kinds[c["change"]] = kinds.get(c["change"], 0) + 1
    print(f"{len(changes)} changed operation(s) -> {args.out}")
    for kind, count in sorted(kinds.items()):
        print(f"    {kind:22} {count}")
    ungrounded = sum(1 for c in changes if c["change"] == "structure_changed" and not c["claims"])
    if ungrounded:
        print(f"\nnote: {ungrounded} structurally changed operation(s) cite no claim,")
        print("so the KB cannot tell which of its claims this affects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
