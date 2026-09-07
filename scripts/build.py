#!/usr/bin/env python3
"""Generate the Prisma AIRS specification from an inherited base specification.

    Inherit the shape. Re-ground the prose.

Structure is carried over. Every natural-language field is stripped and
replaced with an empty stub in overlays/docs-prose.yaml, to be filled in only
once an accepted KB claim supports it. An empty description renders as a
visible gap; a plausible invented one does not.

Usage:
    scripts/build.py --base .source/portkey-openapi.yaml
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Natural-language fields. Removed from openapi.yaml at every level.
PROSE_KEYS = {"description", "summary", "example", "examples", "externalDocs"}

# Root-level extensions from the base specification that carry inherited
# navigation and prose rather than structure.
DROP_ROOT_KEYS = {"x-code-samples"}

# Dicts whose keys are author-chosen names, not OpenAPI keywords. Inside these,
# a key called "description" is a property named "description" and must survive.
NAME_MAPS = {
    "properties",
    "patternProperties",
    "definitions",
    "paths",
    "webhooks",
    "schemas",
    "responses",
    "content",
    "headers",
    "encoding",
    "requestBodies",
    "securitySchemes",
    "links",
    "callbacks",
    "variables",
}

# Values that are data, not documents. Never recursed into: a `default` of
# {"description": "none"} is a literal API value, not a description to strip.
OPAQUE_KEYS = {"default", "enum", "const", "mapping", "scopes"}

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def digest(text: str) -> str:
    return "sha256-" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class Stripper:
    """Removes prose while recording where every removal happened.

    The record is a worklist, not an archive. It stores the JSON pointer and a
    digest of what was there, never the text itself -- keeping the inherited
    prose around invites it being pasted back in unreviewed.
    """

    def __init__(self) -> None:
        self.removed: list[dict[str, str]] = []

    def record(self, pointer: str, key: str, value) -> None:
        text = value if isinstance(value, str) else yaml.safe_dump(value, sort_keys=False)
        self.removed.append(
            {
                "pointer": pointer,
                "field": key,
                "chars": str(len(text)),
                "text_digest": digest(text),
            }
        )

    def walk(self, node, pointer: str = "", keywords: bool = True, is_response: bool = False):
        if isinstance(node, list):
            return [self.walk(v, f"{pointer}/{i}", True) for i, v in enumerate(node)]

        if not isinstance(node, dict):
            return node

        # A name map's keys are identifiers. Do not read them as keywords, but
        # each value below them is a keyword object again.
        if not keywords:
            return {
                k: self.walk(v, f"{pointer}/{esc(k)}", True, is_response)
                for k, v in node.items()
            }

        out = {}
        for key, value in node.items():
            child = f"{pointer}/{esc(key)}"
            if key in PROSE_KEYS:
                self.record(child, key, value)
                # OpenAPI 3.0 makes description required on a Response Object,
                # so there it is emptied rather than removed. Same visible gap,
                # still a valid document.
                if key == "description" and is_response:
                    out[key] = ""
                continue
            if key in OPAQUE_KEYS:
                out[key] = value
                continue
            out[key] = self.walk(
                value, child, key not in NAME_MAPS, is_response=(key == "responses")
            )
        return out


def drop_null_defaults(node, pointer: str = "", found: list | None = None) -> list[str]:
    """Remove `default: null`, which is invalid in OpenAPI 3.0 without
    `nullable: true`.

    The base specification carries nine of these and does not validate because
    of them. Adding `nullable: true` would assert a behaviour nothing here
    supports; removing the default asserts nothing. A default is a stated
    behaviour, so removing an unverifiable one is the conservative direction.
    """
    found = [] if found is None else found
    if isinstance(node, dict):
        if node.get("default", "absent") is None:
            del node["default"]
            found.append(f"{pointer}/default")
        for key, value in node.items():
            drop_null_defaults(value, f"{pointer}/{esc(key)}", found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            drop_null_defaults(value, f"{pointer}/{index}", found)
    return found


def esc(token: str) -> str:
    """RFC 6901 JSON pointer escaping."""
    return token.replace("~", "~0").replace("/", "~1")


def load_tag_map(path: Path):
    doc = yaml.safe_load(path.read_text())
    rename = {entry["from"]: entry["to"] for entry in doc["tags"]}
    group_of = {entry["to"]: entry["group"] for entry in doc["tags"]}
    return doc, rename, group_of


def operations(spec):
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict):
                yield path, method, op


def jsonpath_for(path: str, method: str) -> str:
    quoted = path.replace("'", "\\'")
    return f"$.paths['{quoted}'].{method}"


def build(base_path: Path) -> int:
    base = yaml.safe_load(base_path.read_text())
    tagdoc, rename, group_of = load_tag_map(ROOT / "tags-map.yaml")

    stripper = Stripper()
    spec = stripper.walk(base)

    for key in DROP_ROOT_KEYS:
        spec.pop(key, None)

    null_defaults = drop_null_defaults(spec)

    # --- info -------------------------------------------------------------
    # Contact, license and terms in the base point at Portkey resources. They
    # are assertions about this API's governance that nothing here supports,
    # so they are dropped rather than rewritten to a guessed URL.
    version = base.get("info", {}).get("version", "2.0.0")
    spec["info"] = {
        "title": "Prisma AIRS AI Gateway API",
        "version": version,
        "description": "",
    }

    # --- tags -------------------------------------------------------------
    used = set()
    unmapped = set()
    for _, _, op in operations(spec):
        renamed = []
        for tag in op.get("tags", []):
            if tag not in rename:
                unmapped.add(tag)
                renamed.append(tag)
                continue
            renamed.append(rename[tag])
        if renamed:
            # Merged tags (Fine-tuning + Finetune) can collide; keep order,
            # drop duplicates.
            op["tags"] = list(dict.fromkeys(renamed))
            used.update(op["tags"])

    if unmapped:
        print(f"error: tags used by operations but absent from tags-map.yaml: "
              f"{sorted(unmapped)}", file=sys.stderr)
        return 1

    spec["tags"] = [
        {"name": name, "description": ""}
        for name in sorted(used, key=lambda n: (group_order(tagdoc, group_of[n]), n))
    ]

    # --- provenance scaffolding -------------------------------------------
    # Empty now, and deliberately so. Reconstructing which claim supported a
    # description after the fact is indistinguishable from inventing it, so the
    # field shape goes in before there is anything to put in it.
    for _, _, op in operations(spec):
        op["summary"] = ""
        op["description"] = ""
        op["x-airs-provenance"] = {
            "claims": [],
            "origin_kind": "human",
            "text_digest": "",
        }

    # --- Mintlify MCP surface ---------------------------------------------
    spec["x-mint"] = {
        "mcp": {
            "enabled": True,
            "name": "Prisma AIRS AI Gateway",
            "description": "",
        }
    }

    spec = reorder(spec)

    # --- write -------------------------------------------------------------
    (ROOT / "openapi.yaml").write_text(
        "# Generated by scripts/build.py. Structure only -- see overlays/docs-prose.yaml\n"
        "# for every field a reader reads.\n"
        + yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)
    )

    write_overlay(spec)
    write_inventory(stripper.removed)
    write_navigation(tagdoc, used, group_of)

    ops = list(operations(spec))
    missing_ids = [f"{m.upper()} {p}" for p, m, o in ops if not o.get("operationId")]
    print(f"operations         {len(ops)}")
    print(f"paths              {len(spec.get('paths', {}))}")
    print(f"schemas            {len(spec.get('components', {}).get('schemas', {}))}")
    print(f"tags               {len(spec['tags'])}")
    print(f"prose fields removed {len(stripper.removed)}")
    print(f"null defaults dropped {len(null_defaults)}")
    print(f"operations lacking operationId {len(missing_ids)}")

    (ROOT / "build-report.txt").write_text(
        "Generated by scripts/build.py\n\n"
        f"operations                       {len(ops)}\n"
        f"paths                            {len(spec.get('paths', {}))}\n"
        f"schemas                          {len(spec.get('components', {}).get('schemas', {}))}\n"
        f"tags                             {len(spec['tags'])}\n"
        f"prose fields removed             {len(stripper.removed)}\n"
        f"null defaults dropped            {len(null_defaults)}\n"
        + "".join(f"    {p}\n" for p in null_defaults)
        + f"\noperations lacking operationId   {len(missing_ids)}\n"
        "  These are inherited gaps, not introduced here. operationId values are\n"
        "  never renamed, and inventing them is not the same as recovering them,\n"
        "  so they are reported for engineering rather than filled in.\n"
        + "".join(f"    {m}\n" for m in sorted(missing_ids))
    )
    return 0


def group_order(tagdoc, group_id: str) -> int:
    ids = [g["id"] for g in tagdoc["groups"]]
    return ids.index(group_id) if group_id in ids else len(ids)


def reorder(spec):
    """Keep the document in conventional OpenAPI order for reviewable diffs."""
    order = ["openapi", "info", "servers", "x-server-groups", "x-mint",
             "security", "tags", "paths", "components"]
    out = {k: spec[k] for k in order if k in spec}
    out.update({k: v for k, v in spec.items() if k not in out})
    return out


def write_overlay(spec) -> None:
    """Emit the prose overlay: every reader-facing field, empty.

    Scoped to info, tags and operations -- roughly 300 actions. Schema property
    prose is stripped from openapi.yaml but not pre-stubbed here; at 3,000-plus
    entries the overlay would stop being reviewable, which is the one property
    that makes it a usable grounding gate. Those are added as they are grounded,
    targeted by JSON path, and tracked in PROSE-INVENTORY.csv until then.
    """
    actions = [
        {
            "target": "$.info",
            "update": {"description": ""},
        }
    ]

    for tag in spec["tags"]:
        name = tag["name"].replace("'", "\\'")
        actions.append(
            {
                "target": f"$.tags[?(@.name=='{name}')]",
                "update": {"description": ""},
            }
        )

    for path, method, op in operations(spec):
        actions.append(
            {
                "target": jsonpath_for(path, method),
                "update": {
                    "summary": "",
                    "description": "",
                    "x-airs-provenance": {
                        "claims": [],
                        "origin_kind": "human",
                        "text_digest": "",
                    },
                },
            }
        )

    overlay = {
        "overlay": "1.0.0",
        "info": {
            "title": "Prisma AIRS AI Gateway API - documentation prose",
            "version": "0.1.0",
        },
        "actions": actions,
    }

    (ROOT / "overlays").mkdir(exist_ok=True)
    (ROOT / "overlays" / "docs-prose.yaml").write_text(
        "# Generated by scripts/build.py, then edited by hand as claims are accepted.\n"
        "# Every value here is published documentation and passes the grounding gate.\n"
        "# Leave a field empty rather than filling it from the inherited specification.\n"
        + yaml.safe_dump(overlay, sort_keys=False, allow_unicode=True, width=100)
    )


def write_inventory(removed) -> None:
    """The re-grounding worklist: where prose was, and how much of it."""
    with (ROOT / "PROSE-INVENTORY.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["pointer", "field", "chars", "text_digest"])
        writer.writeheader()
        writer.writerows(sorted(removed, key=lambda r: r["pointer"]))


def write_navigation(tagdoc, used, group_of) -> None:
    """A docs.json navigation fragment: groups generated from spec tags.

    No stub pages, no per-endpoint navigation entries, and no method+path join
    key to keep in sync.
    """
    groups = []
    for group in tagdoc["groups"]:
        members = sorted(t for t in used if group_of[t] == group["id"])
        if not members:
            continue
        groups.append(
            {
                "group": group["title"],
                "pages": [
                    {
                        "group": tag,
                        "openapi": {
                            "source": "https://raw.githubusercontent.com/"
                                      "PaloAltoNetworks/openapi/main/openapi.yaml",
                            "directory": "api-reference",
                            "overlays": ["overlays/docs-prose.yaml"],
                        },
                        "tag": tag,
                    }
                    for tag in members
                ],
            }
        )

    import json

    (ROOT / "docs-navigation.json").write_text(
        json.dumps({"groups": groups}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=".source/portkey-openapi.yaml", type=Path)
    args = parser.parse_args()
    sys.exit(build(args.base))
