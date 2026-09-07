#!/usr/bin/env python3
"""Detect drift between the specification and the KB.

The specification is a second trusted source. It is authoritative in its own
domain and not subordinate to the KB, which has a specific consequence for this
script: **it never fixes anything.** Drift is a defect regardless of which
artifact moved, there is no authoritative side to fall back on, and conflicts
are resolved by maintainers -- never automatically, never last-write-wins. So
this reports and exits non-zero. The workflow that runs it opens an issue.

`x-airs-provenance.claims` is the join key. An operation with no claims is not
"fine", it is invisible to this check: nothing can tell that the KB moved and
the specification did not.

Usage:
    scripts/drift.py --manifest kb-manifest.json
    scripts/drift.py --manifest-url https://kb.example/claims.json
    scripts/drift.py --dry-run        # no KB: report grounding coverage only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import operations  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"
OVERLAY_DIR = ROOT / "overlays"


def load_manifest(path: Path | None, url: str | None):
    """KB claim manifest: {"claims": {"<id>": {"revision": ..., "status": ...}}}"""
    if url:
        with urllib.request.urlopen(url, timeout=30) as fh:  # noqa: S310
            return json.load(fh)
    if path:
        return json.loads(path.read_text())
    return None


def overlay_prose():
    """Prose keyed by overlay target, with the provenance written beside it."""
    entries = {}
    for path in sorted(OVERLAY_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        for action in doc.get("actions", []):
            update = action.get("update", {}) or {}
            text = " ".join(
                str(update.get(k, "")) for k in ("summary", "description")
            ).strip()
            entries[action["target"]] = {
                "file": path.name,
                "text": text,
                "provenance": update.get("x-airs-provenance") or {},
            }
    return entries


def target_for(path: str, method: str) -> str:
    return f"$.paths['{path}']" + f".{method}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", type=Path, help="write the findings as JSON")
    args = parser.parse_args()

    spec = yaml.safe_load(SPEC.read_text())
    prose = overlay_prose()
    manifest = load_manifest(args.manifest, args.manifest_url)

    ops = list(operations(spec))
    findings: list[dict] = []

    def flag(kind: str, where: str, detail: str) -> None:
        findings.append({"kind": kind, "where": where, "detail": detail})

    grounded = 0
    written = 0

    for path, method, op in ops:
        where = f"{method.upper()} {path}"
        prov = op.get("x-airs-provenance") or {}
        claims = prov.get("claims") or []
        entry = prose.get(target_for(path, method), {})
        text = entry.get("text", "")
        overlay_prov = entry.get("provenance") or {}
        overlay_claims = overlay_prov.get("claims") or []

        if text:
            written += 1

        # Prose exists but rests on nothing. The failure the split exists to stop.
        if text and not overlay_claims:
            flag("ungrounded", where, "overlay writes prose with no claim")

        # Prose was edited without re-grounding it.
        if text and overlay_claims:
            expected = "sha256-" + hashlib.sha256(text.encode()).hexdigest()
            if overlay_prov.get("text_digest") not in (expected, "", None):
                flag("stale-digest", where,
                     "text_digest does not match the prose it ships")

        if claims or overlay_claims:
            grounded += 1

        if manifest is None:
            continue

        known = manifest.get("claims", {})
        # The same claim is normally cited in both openapi.yaml and the overlay.
        # Deduplicate so one drifted claim is one finding, not two.
        seen = {
            (c.get("id"), c.get("revision"))
            for c in list(claims) + list(overlay_claims)
        }
        for cid, revision in sorted(seen, key=lambda t: (t[0] or "", t[1] or "")):
            claim = {"id": cid, "revision": revision}
            if cid not in known:
                flag("unknown-claim", where, f"cites {cid}, absent from the KB manifest")
                continue
            kb = known[cid]
            if kb.get("status") != "accepted":
                flag("unaccepted-claim", where,
                     f"cites {cid}, which the KB now reports as {kb.get('status')}")
            cited = claim.get("revision")
            if cited and kb.get("revision") and cited != kb["revision"]:
                flag("revision-drift", where,
                     f"cites {cid} at {cited}; the KB is at {kb['revision']}")

    # Claims the KB holds that nothing in the specification cites. Not a defect
    # on its own -- most claims are not about the API -- so it is reported only
    # when the KB marks a claim as belonging to the spec's domain.
    if manifest:
        cited = {
            c.get("id")
            for _, _, op in ops
            for c in (op.get("x-airs-provenance") or {}).get("claims") or []
        }
        for cid, meta in manifest.get("claims", {}).items():
            if meta.get("domain") == "api" and cid not in cited:
                flag("orphan-claim", cid,
                     "KB marks this claim as API-domain, but no operation cites it")

    # --- report -----------------------------------------------------------
    total = len(ops)
    print(f"operations              {total}")
    print(f"with a claim reference  {grounded}")
    print(f"with written prose      {written}")
    print(f"KB manifest             "
          f"{'not supplied (coverage only)' if manifest is None else 'loaded'}")
    print()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(findings, indent=2) + "\n")

    if not findings:
        if manifest is None and not args.dry_run:
            print("no KB manifest: nothing to compare against")
            return 0
        print("no drift detected")
        return 0

    by_kind: dict[str, list[dict]] = {}
    for f in findings:
        by_kind.setdefault(f["kind"], []).append(f)

    for kind, items in sorted(by_kind.items()):
        print(f"{kind} ({len(items)})")
        for item in items[:20]:
            print(f"    {item['where']}: {item['detail']}")
        if len(items) > 20:
            print(f"    ... and {len(items) - 20} more")
        print()

    print(f"{len(findings)} finding(s). Drift is a defect on whichever side moved;")
    print("resolve it by maintainer decision, not by regenerating either artifact.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
