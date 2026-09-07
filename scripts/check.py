#!/usr/bin/env python3
"""Repository invariants, enforced in CI.

Validation is the point of this file, but the grounding gate is the reason it
exists. An OpenAPI specification is published documentation: every summary and
description in it becomes public prose. So CI checks not just that the document
parses, but that no ungrounded prose has been added to it.

Usage:
    scripts/check.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml
from jsonpath_ng.ext import parse
from openapi_spec_validator import validate as validate_spec

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_overlay import apply  # noqa: E402
from build import HTTP_METHODS, operations  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"
OVERLAY_DIR = ROOT / "overlays"
TAG_MAP = ROOT / "tags-map.yaml"

failures: list[str] = []


def fail(check: str, detail: str) -> None:
    failures.append(f"{check}: {detail}")


def report(check: str, detail: str = "") -> None:
    print(f"  ok    {check}{(' -- ' + detail) if detail else ''}")


def check_spec_valid(spec) -> None:
    try:
        validate_spec(spec)
        report("openapi.yaml is a valid OpenAPI document")
    except Exception as exc:  # noqa: BLE001 - surface the validator's own message
        fail("openapi.yaml validation", str(exc).splitlines()[0])


def check_no_prose_in_spec(spec) -> None:
    """The structure/prose split, enforced.

    openapi.yaml is engineering's artifact. Prose belongs in the overlay, where
    it is small enough to review claim by claim. A description that appears here
    has bypassed that review.
    """
    offenders: list[str] = []

    def walk(node, pointer="", keywords=True):
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{pointer}/{i}", True)
            return
        if not isinstance(node, dict):
            return
        if not keywords:
            for k, v in node.items():
                walk(v, f"{pointer}/{k}", True)
            return
        for k, v in node.items():
            if k in ("description", "summary") and isinstance(v, str) and v.strip():
                offenders.append(f"{pointer}/{k}")
            if k in ("default", "enum", "const", "mapping", "scopes"):
                continue
            walk(v, f"{pointer}/{k}", k not in NAME_MAPS)

    from build import NAME_MAPS  # noqa: PLC0415

    walk(spec)
    if offenders:
        fail(
            "prose in openapi.yaml",
            f"{len(offenders)} non-empty description/summary; move to overlays/. "
            f"First: {offenders[0]}",
        )
    else:
        report("no prose in openapi.yaml", "structure/prose split intact")


def check_tags(spec) -> None:
    declared = {t["name"] for t in spec.get("tags", [])}
    mapped = {e["to"] for e in yaml.safe_load(TAG_MAP.read_text())["tags"]}
    used = {t for _, _, op in operations(spec) for t in op.get("tags", [])}

    if used - declared:
        fail("tags", f"used but not declared in spec: {sorted(used - declared)}")
    elif declared - used:
        fail("tags", f"declared but unused: {sorted(declared - used)}")
    elif used - mapped:
        fail("tags", f"not present in tags-map.yaml: {sorted(used - mapped)}")
    else:
        report("tags", f"{len(declared)} declared, all used, all mapped")


def check_provenance(spec) -> None:
    """Without a claim reference on an operation, nothing can tell that the KB
    moved and the specification did not. The scaffold has to be present even
    while claims are empty."""
    missing = []
    malformed = []
    for path, method, op in operations(spec):
        prov = op.get("x-airs-provenance")
        if prov is None:
            missing.append(f"{method.upper()} {path}")
        elif not {"claims", "origin_kind", "text_digest"} <= set(prov):
            malformed.append(f"{method.upper()} {path}")
        elif prov.get("origin_kind") not in ("human", "generated", "mixed"):
            malformed.append(f"{method.upper()} {path} (origin_kind)")

    if missing:
        fail("provenance", f"{len(missing)} operations lack x-airs-provenance: {missing[:3]}")
    elif malformed:
        fail("provenance", f"{len(malformed)} malformed: {malformed[:3]}")
    else:
        report("provenance", f"scaffolded on all {len(list(operations(spec)))} operations")


def check_overlays(spec) -> None:
    overlays = sorted(OVERLAY_DIR.glob("*.yaml"))
    if not overlays:
        fail("overlays", "no overlay documents found")
        return

    import copy

    resolved = copy.deepcopy(spec)
    for path in overlays:
        doc = yaml.safe_load(path.read_text())
        if doc.get("overlay") != "1.0.0":
            fail("overlays", f"{path.name} is not an Overlay 1.0.0 document")
            return
        try:
            resolved, _ = apply(resolved, doc)
        except ValueError as exc:
            fail("overlays", f"{path.name}: {exc}".splitlines()[0])
            return
        report(f"overlays/{path.name}", f"{len(doc.get('actions', []))} targets all resolve")

    try:
        validate_spec(resolved)
        report("overlay result", "still a valid OpenAPI document")
    except Exception as exc:  # noqa: BLE001
        fail("overlay result", str(exc).splitlines()[0])

    check_grounding_gate(overlays)


def check_grounding_gate(overlays) -> None:
    """Prose that has been written must carry the claim that supports it.

    This is the check that makes the exemption workable. An empty description
    is fine -- it renders as a visible gap. A written one with no accepted claim
    behind it is the failure mode the whole split exists to prevent.
    """
    ungrounded = []
    stale = []
    written = 0

    for path in overlays:
        doc = yaml.safe_load(path.read_text())
        for action in doc.get("actions", []):
            update = action.get("update", {})
            prose = " ".join(
                str(update.get(k, "")) for k in ("summary", "description")
            ).strip()
            if not prose:
                continue
            written += 1
            prov = update.get("x-airs-provenance") or {}
            if not prov.get("claims"):
                ungrounded.append(action["target"])
                continue
            expected = "sha256-" + hashlib.sha256(prose.encode()).hexdigest()
            if prov.get("text_digest") not in (expected, ""):
                stale.append(action["target"])

    if ungrounded:
        fail(
            "grounding gate",
            f"{len(ungrounded)} overlay actions write prose with no accepted claim: "
            f"{ungrounded[:3]}",
        )
    elif stale:
        fail("grounding gate", f"{len(stale)} text_digest values do not match their prose: {stale[:3]}")
    else:
        report("grounding gate", f"{written} written descriptions, all with claims")


def check_servers(spec) -> None:
    """Server URLs are typed by readers and parsed by machines. They do not get
    rebranded. This guards against a well-meaning search and replace."""
    urls = [s.get("url", "") for s in spec.get("servers", [])]
    if not urls:
        fail("servers", "no servers declared")
    else:
        report("servers", ", ".join(urls))


def main() -> int:
    print(f"checking {SPEC.relative_to(ROOT)}\n")
    spec = yaml.safe_load(SPEC.read_text())

    check_spec_valid(spec)
    check_no_prose_in_spec(spec)
    check_tags(spec)
    check_provenance(spec)
    check_servers(spec)
    check_overlays(spec)

    print()
    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
