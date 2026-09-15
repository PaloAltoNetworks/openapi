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
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import HTTP_METHODS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def oasdiff_breaking(base_file: Path, head_file: Path) -> list[dict]:
    """Grade the structural changes with oasdiff.

    `structure_changed` is a boolean; this turns it into a reason. For the KB
    that is the difference between "something moved" and "a claim describing
    this behaviour is probably now false".

    Degrades to an empty list if oasdiff is absent, so the payload is still
    produced -- just ungraded.
    """
    if not shutil.which("oasdiff"):
        print("note: oasdiff not installed; changes will not be graded", file=sys.stderr)
        return []
    proc = subprocess.run(
        ["oasdiff", "breaking", str(base_file), str(head_file), "-f", "json"],
        capture_output=True, text=True,
    )
    # oasdiff exits non-zero when it finds breaking changes; that is data here,
    # not an error. Only an unparseable stdout is a failure.
    if not proc.stdout.strip():
        return []
    try:
        return json.loads(proc.stdout) or []
    except json.JSONDecodeError:
        print(f"note: could not parse oasdiff output: {proc.stderr[:200]}", file=sys.stderr)
        return []


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
    # x-mint is the operation's docs URL. It moves when a tag is renamed, which
    # is a documentation migration and not a change to the API -- reporting it
    # as `structure_changed` would tell the KB to re-review claims about
    # behaviour that did not move.
    for key in ("summary", "description", "x-airs-provenance", "externalDocs",
                "x-mint"):
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

    base_doc = at_revision(args.base, "openapi.yaml")
    head_doc = at_revision(args.head, "openapi.yaml")
    before = index(base_doc)
    after = index(head_doc)

    # Grade the diff. Keyed by (method, path) so it can be attached per
    # operation below.
    graded: dict[tuple[str, str], list[dict]] = {}
    if base_doc and head_doc:
        with tempfile.TemporaryDirectory() as tmp:
            base_file = Path(tmp) / "base.yaml"
            head_file = Path(tmp) / "head.yaml"
            base_file.write_text(yaml.safe_dump(base_doc, sort_keys=False))
            head_file.write_text(yaml.safe_dump(head_doc, sort_keys=False))
            for entry in oasdiff_breaking(base_file, head_file):
                key = (entry.get("operation", "").lower(), entry.get("path", ""))
                graded.setdefault(key, []).append(
                    {
                        "id": entry.get("id"),
                        "text": entry.get("text"),
                        "level": entry.get("level"),
                    }
                )

    changes = []
    for key in sorted(set(before) | set(after)):
        method, path = key
        change = classify(before.get(key), after.get(key))
        if not change:
            continue
        op = after.get(key) or before.get(key)
        prov = op.get("x-airs-provenance") or {}
        breaking = graded.get(key, [])
        changes.append(
            {
                "operation_id": op.get("operationId"),
                "method": method,
                "path": path,
                "change": change,
                "breaking": bool(breaking),
                "breaking_changes": breaking,
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
        "breaking_change_count": sum(len(c["breaking_changes"]) for c in changes),
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

    breaking = [c for c in changes if c["breaking"]]
    if breaking:
        print(f"\n{payload['breaking_change_count']} breaking change(s):")
        for c in breaking:
            for b in c["breaking_changes"]:
                print(f"    {c['method'].upper():6} {c['path']}")
                print(f"           {b['text']}  [{b['id']}]")

    ungrounded = sum(1 for c in changes if c["change"] == "structure_changed" and not c["claims"])
    if ungrounded:
        print(f"\nnote: {ungrounded} structurally changed operation(s) cite no claim,")
        print("so the KB cannot tell which of its claims this affects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
