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


def load_drops(path: Path):
    """Tags and operations deliberately not shipped. See _project/drops.yaml."""
    if not path.exists():
        return set(), set()
    doc = yaml.safe_load(path.read_text()) or {}
    tags = set(doc.get("tags") or [])
    ops = {str(entry).strip().lower() for entry in (doc.get("operations") or [])}
    return tags, ops


def apply_drops(spec, drop_tags: set[str], drop_ops: set[str], known_tags: set[str]):
    """Remove dropped operations, and any path left with none.

    Runs after the tag rename, so the names here are this specification's, not
    the base's -- which is what a reader of drop-list.md decided on.

    A tag or an operation id that matches nothing is an error. The usual cause
    is a rename upstream, and a drop rule that has quietly stopped applying
    puts an endpoint back in public documentation without anyone deciding to.
    """
    unknown = sorted(drop_tags - known_tags)
    if unknown:
        raise SystemExit(f"drops.yaml names tags absent from tags-map.yaml: {unknown}")

    dropped_ops: list[str] = []
    dropped_paths: list[str] = []
    matched_tags: set[str] = set()
    matched_ops: set[str] = set()

    for path, item in list(spec.get("paths", {}).items()):
        if not isinstance(item, dict):
            continue
        for method in [m for m in item if m in HTTP_METHODS]:
            op = item[method]
            if not isinstance(op, dict):
                continue
            hit = drop_tags.intersection(op.get("tags") or [])
            key = f"{method} {path}"
            if not hit and key not in drop_ops:
                continue
            matched_tags |= hit
            if key in drop_ops:
                matched_ops.add(key)
            del item[method]
            dropped_ops.append(f"{method.upper()} {path}")
        if not any(m in HTTP_METHODS for m in item):
            # Nothing callable left. A path item holding only `parameters` is
            # not a resource, it is a leftover.
            del spec["paths"][path]
            dropped_paths.append(path)

    stale = sorted((drop_tags - matched_tags) | (drop_ops - matched_ops))
    if stale:
        raise SystemExit(f"drops.yaml entries match no operation: {stale}")

    return sorted(dropped_paths), sorted(dropped_ops)


def refs_in(node, out: set) -> set:
    """Every `#/components/...` pointer in a subtree, as `section/name`."""
    if isinstance(node, dict):
        target = node.get("$ref")
        if isinstance(target, str) and target.startswith("#/components/"):
            out.add(target[len("#/components/"):])
        for value in node.values():
            refs_in(value, out)
    elif isinstance(node, list):
        for value in node:
            refs_in(value, out)
    return out


def security_names(node, out: set) -> set:
    """Scheme names used by any `security` block. These are named, not $ref'd,
    so reachability alone would prune every security scheme in the document."""
    if isinstance(node, dict):
        for requirement in node.get("security") or []:
            if isinstance(requirement, dict):
                out.update(f"securitySchemes/{name}" for name in requirement)
        for value in node.values():
            security_names(value, out)
    elif isinstance(node, list):
        for value in node:
            security_names(value, out)
    return out


def prune_components(spec) -> list[str]:
    """Drop components nothing reaches, and report what went.

    Roots are the whole document apart from `components` itself, so a schema
    survives only if something outside the component pool asks for it, directly
    or through a chain of $refs. This removes both what the drops orphaned and
    what the base was already carrying unreferenced -- the two are the same
    thing and there is no reason to tell them apart.
    """
    components = spec.get("components") or {}
    outside = {k: v for k, v in spec.items() if k != "components"}

    seen: set[str] = set()
    queue = list(refs_in(outside, set()) | security_names(spec, set()))
    while queue:
        key = queue.pop()
        if key in seen:
            continue
        seen.add(key)
        section, _, name = key.partition("/")
        node = (components.get(section) or {}).get(name)
        if node is not None:
            queue.extend(refs_in(node, set()) - seen)

    removed = []
    for section, entries in list(components.items()):
        if not isinstance(entries, dict):
            continue
        for name in list(entries):
            if f"{section}/{name}" not in seen:
                del entries[name]
                removed.append(f"{section}/{name}")
        if not entries:
            del components[section]
    return sorted(removed)


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

    if unmapped:
        print(f"error: tags used by operations but absent from tags-map.yaml: "
              f"{sorted(unmapped)}", file=sys.stderr)
        return 1

    # --- drops --------------------------------------------------------------
    # After the rename so drops.yaml can name tags as this specification does,
    # and before `used` is computed so an emptied tag leaves no navigation
    # entry pointing at nothing.
    drop_tags, drop_ops = load_drops(ROOT / "_project" / "drops.yaml")
    dropped_paths, dropped_ops = apply_drops(spec, drop_tags, drop_ops, set(rename.values()))
    orphaned = prune_components(spec)

    used = set()
    for _, _, op in operations(spec):
        used.update(op.get("tags") or [])

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
    print(f"operations         {len(ops)}  (dropped {len(dropped_ops)})")
    print(f"paths              {len(spec.get('paths', {}))}  (dropped {len(dropped_paths)})")
    print(f"schemas            {len(spec.get('components', {}).get('schemas', {}))}")
    print(f"components pruned  {len(orphaned)}")
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
        f"\noperations dropped               {len(dropped_ops)}\n"
        "  Declared in _project/drops.yaml and recorded in _project/base-delta.yaml.\n"
        + "".join(f"    {m}\n" for m in dropped_ops)
        + f"\npaths emptied by those drops     {len(dropped_paths)}\n"
        + "".join(f"    {p}\n" for p in dropped_paths)
        + f"\ncomponents pruned                {len(orphaned)}\n"
        "  Reachability sweep. Covers both what the drops orphaned and what the\n"
        "  base already carried unreferenced; the two are indistinguishable and\n"
        "  there is no reason to keep either.\n"
        + "".join(f"    {c}\n" for c in orphaned)
        + f"\nprose fields removed             {len(stripper.removed)}\n"
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
