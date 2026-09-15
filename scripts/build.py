#!/usr/bin/env python3
"""Reapply this repository's decisions to openapi.yaml, and regenerate what is
derived from it.

    Inherit the shape. Re-ground the prose.

openapi.yaml was originally generated from an inherited base specification.
That linkage is over: the base is no longer fetched, no longer compared
against, and openapi.yaml is now the source of truth for structure. What
remains is the set of decisions that are held in small files rather than in the
document -- the base URLs in _project/servers.yaml, the one security scheme,
the tag information architecture in tags-map.yaml, the operations declared
undropped in _project/drops.yaml.

So this script reads openapi.yaml, applies those decisions to it, and writes it
back. It is idempotent: running it on an unchanged repository changes nothing.
That is what keeps "the one place to change a base URL is _project/servers.yaml"
true -- edit a host there, rebuild, and all 67 blocks follow.

What it does NOT do is author. It never writes a description, and it never
overwrites one: overlays/docs-prose.yaml is topped up with empty stubs for
operations that lack them and is otherwise left alone.

Usage:
    scripts/build.py
    scripts/build.py --check      # fail if anything would change
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"

# Natural-language fields. These belong in overlays/docs-prose.yaml, never here.
#
# Code samples are in this set because a code sample is prose. It asserts a base
# URL, an auth header, a content type and a set of fields worth sending -- all
# claims, none of them checkable by a schema validator. The base carried 106 of
# them on operations, hardcoding api.portkey.ai and the x-portkey-api-key and
# x-portkey-virtual-key headers. Mintlify renders a supplied sample *instead of*
# the one it would generate, so leaving those in place silently overrode both
# the base URL change and the auth change: the reader would have been told to
# call the old host with headers this API does not read.
#
# Both spellings. The base used x-code-samples; Mintlify reads x-codeSamples.
# Guarding only the one that was present is how the other comes back.
#
# The list is kept here rather than in check.py because check.py imports it: the
# strip that produced openapi.yaml and the check that keeps it clean have to
# agree on what counts as prose, and two copies of that list would not.
PROSE_KEYS = {"description", "summary", "example", "examples", "externalDocs",
              "x-code-samples", "x-codeSamples"}

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


def esc(token: str) -> str:
    """RFC 6901 JSON pointer escaping."""
    return token.replace("~", "~0").replace("/", "~1")


def drop_null_defaults(node, pointer: str = "", found: list | None = None) -> list[str]:
    """Remove `default: null`, which is invalid in OpenAPI 3.0 without
    `nullable: true`.

    The base specification carried nine of these and did not validate because
    of them. Adding `nullable: true` would assert a behaviour nothing here
    supports; removing the default asserts nothing. A default is a stated
    behaviour, so removing an unverifiable one is the conservative direction.

    Kept as an applier rather than a check because it costs nothing and the
    failure it prevents -- a document that does not validate -- is one a
    contributor would otherwise hit after the fact.
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


def load_tag_map(path: Path):
    doc = yaml.safe_load(path.read_text())
    names = {entry["to"] for entry in doc["tags"]}
    group_of = {entry["to"]: entry["group"] for entry in doc["tags"]}
    return doc, names, group_of


def load_drops(path: Path):
    """Tags and operations deliberately not shipped. See _project/drops.yaml."""
    if not path.exists():
        return set(), set()
    doc = yaml.safe_load(path.read_text()) or {}
    tags = set(doc.get("tags") or [])
    ops = {str(entry).strip().lower() for entry in (doc.get("operations") or [])}
    return tags, ops


def matches_drop(path: str, method: str, op, drop_tags: set[str],
                 drop_ops: set[str]) -> bool:
    return bool(drop_tags.intersection(op.get("tags") or [])) \
        or f"{method} {path}" in drop_ops


def check_drops(spec, drop_tags: set[str], drop_ops: set[str]) -> None:
    """Nothing declared dropped has come back.

    While the base was still being rebuilt from, this was an applier: it deleted
    the 61 operations. Now that openapi.yaml is the source, the same file has to
    work the other way round -- as the guard that stops one of them reappearing
    because somebody pasted an endpoint back in or re-imported from upstream.

    Declining to drop something is a decision; it just has to be made in
    drops.yaml rather than by an edit nobody reviewed.
    """
    back = [f"{method.upper()} {path}"
            for path, method, op in operations(spec)
            if matches_drop(path, method, op, drop_tags, drop_ops)]
    if back:
        raise SystemExit(
            f"_project/drops.yaml declares these not shipped, but they are in "
            f"openapi.yaml: {sorted(back)}. Run `python scripts/build.py "
            f"--apply-drops` to remove them.")


def apply_drops(spec, drop_tags: set[str], drop_ops: set[str]) -> list[str]:
    """Delete what drops.yaml newly declares. Only under --apply-drops.

    Removing operations from the published artifact is not something a routine
    build should do on its own -- it is a deliberate act, and it wants to show
    up in the diff of openapi.yaml where a reviewer sees it. So the default
    build only checks, and this runs when a human asks for it: add the tag to
    drops.yaml, run with the flag once, commit both halves together.
    """
    gone: list[str] = []
    for path, item in list((spec.get("paths") or {}).items()):
        if not isinstance(item, dict):
            continue
        for method in [m for m in list(item) if m in HTTP_METHODS]:
            op = item[method]
            if isinstance(op, dict) and matches_drop(path, method, op,
                                                     drop_tags, drop_ops):
                del item[method]
                gone.append(f"{method.upper()} {path}")
        # A path item with no methods left describes nothing; its parameters
        # and summary would linger as an empty entry in the navigation.
        if not any(m in item for m in HTTP_METHODS):
            del spec["paths"][path]
    return sorted(gone)


# The only way to authenticate. The base offered six schemes in five
# combinations -- an API key plus, depending on the operation, a virtual key, a
# provider bearer token, a provider name, a config id or a custom host. Prisma
# AIRS uses none of that: one bearer token in the Authorization header.
#
# This is the one place the "names are never renamed" rule is deliberately
# broken. A security scheme name is not an API identifier the way an
# operationId is; it is a label on a requirement, and keeping `Portkey-Key`
# pointing at `x-portkey-api-key` would document a header this API does not read.
SECURITY_SCHEME_NAME = "Authorization"
SECURITY_SCHEME = {"type": "http", "scheme": "bearer"}


def apply_security(spec) -> tuple[int, list[str]]:
    """One scheme, one requirement, declared once at the root.

    Operation-level `security` is removed so the root requirement applies
    everywhere -- with a single scheme there is nothing left for an override to
    say. The exception is `security: []`, which is not a variation on the
    requirement but its absence: it marks an operation as needing no
    authentication at all. That is a claim about the API, inherited and not
    ours to quietly reverse, so it is preserved and reported.
    """
    spec.setdefault("components", {})["securitySchemes"] = {
        SECURITY_SCHEME_NAME: dict(SECURITY_SCHEME)
    }
    spec["security"] = [{SECURITY_SCHEME_NAME: []}]

    removed = 0
    public: list[str] = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method not in HTTP_METHODS or not isinstance(op, dict):
                continue
            if "security" not in op:
                continue
            if op["security"] == []:
                public.append(f"{method.upper()} {path}")
                continue
            del op["security"]
            removed += 1

    return removed, sorted(public)


def load_servers() -> dict[str, list[dict]]:
    """The base URLs, as one `servers` array per plane. Order is significant:
    Mintlify generates its code sample from the first entry and offers the rest
    in a "Select base URL" dropdown."""
    defs = yaml.safe_load((ROOT / "_project" / "servers.yaml").read_text())
    for plane, entries in defs.items():
        if not isinstance(entries, list) or not entries:
            raise SystemExit(
                f"servers.yaml: {plane!r} must be a non-empty list of server "
                f"objects, got {type(entries).__name__}")
    return defs


def apply_servers(spec) -> int:
    """Rewrite every `servers` block from _project/servers.yaml.

    This is the mechanism behind "one place to change the base URL". The base
    carried 97 path-level and 2 operation-level overrides, three of which
    published a bare placeholder string as if it were a URL. Changing the base
    URL meant editing a hundred places and noticing all of them, which is not a
    thing anyone does twice.

    The gateway is the root server, so gateway paths need no override at all.
    Control-plane paths get one, because OpenAPI gives a path no way to refer
    back to a server declared once at the root -- the duplication is the
    format's, not ours, and it is generated rather than maintained.

    A path-level block replaces the root list rather than extending it, so the
    gateway's self-hosted entry does not appear on control-plane operations.
    """
    defs = load_servers()
    planes = yaml.safe_load((ROOT / "_project" / "planes.yaml").read_text())
    control = set(planes.get("control-plane") or {})
    gateway = set(planes.get("gateway") or {})

    missing = sorted(set(spec.get("paths") or {}) - control - gateway)
    if missing:
        # Defaulting would put a control-plane endpoint on the gateway host and
        # look entirely normal while doing it.
        raise SystemExit(
            f"planes.yaml does not classify {len(missing)} path(s): {missing}")

    # The other direction. A classification for a path that no longer exists is
    # harmless to the build and misleading to everything else -- gen_drop_list.py
    # counts these, so leftovers from a drop quietly inflate the inventory.
    stale = sorted((control | gateway) - set(spec.get("paths") or {}))
    if stale:
        raise SystemExit(
            f"planes.yaml classifies {len(stale)} path(s) that are not in "
            f"openapi.yaml: {stale}")

    stamped = 0
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        item.pop("servers", None)
        for method in [m for m in item if m in HTTP_METHODS]:
            if isinstance(item[method], dict):
                item[method].pop("servers", None)
        if path in control:
            item["servers"] = copy.deepcopy(defs["control-plane"])
            stamped += 1

    spec["servers"] = copy.deepcopy(defs["gateway"])
    return stamped


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
    or through a chain of $refs. Reports nothing on a clean tree; it earns its
    place the next time a group of operations is dropped.
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


def build(dry_run: bool = False, do_drops: bool = False) -> int:
    spec = yaml.safe_load(SPEC.read_text())
    before = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)
    tagdoc, tag_names, group_of = load_tag_map(ROOT / "tags-map.yaml")

    null_defaults = drop_null_defaults(spec)

    # --- drops --------------------------------------------------------------
    # Before the tag check, because a tag that has just been dropped is also
    # about to leave tags-map.yaml, and the two edits land in the same commit.
    drop_tags, drop_ops = load_drops(ROOT / "_project" / "drops.yaml")
    if do_drops:
        dropped = apply_drops(spec, drop_tags, drop_ops)
        print(f"dropped {len(dropped)} operation(s):")
        for entry in dropped:
            print(f"    {entry}")
    else:
        check_drops(spec, drop_tags, drop_ops)

    # --- info -------------------------------------------------------------
    # 3.0.0 is pinned, not inherited. This specification does not describe the
    # same API the base did: 61 operations are gone, there is one way to
    # authenticate where there were five, and the base URLs are different.
    # Contact, license and terms are absent because they are assertions about
    # this API's governance that nothing here supports.
    spec["info"] = {
        "title": "Prisma AIRS AI Gateway API",
        "version": "3.0.0",
        "description": "",
    }

    # --- tags ---------------------------------------------------------------
    # The rename from the base's tag names happened once and is done. What is
    # left is the invariant: every tag an operation names is one tags-map.yaml
    # knows about, so it has a navigation group to sit in.
    unmapped = sorted({t for _, _, op in operations(spec)
                       for t in op.get("tags") or [] if t not in tag_names})
    if unmapped:
        print(f"error: tags used by operations but absent from tags-map.yaml: "
              f"{unmapped}", file=sys.stderr)
        return 1

    security_overrides, public_ops = apply_security(spec)
    control_paths = apply_servers(spec)
    orphaned = prune_components(spec)

    used = set()
    for _, _, op in operations(spec):
        used.update(op.get("tags") or [])

    spec["tags"] = [
        {"name": name, "description": ""}
        for name in sorted(used, key=lambda n: (group_order(tagdoc, group_of[n]), n))
    ]

    # --- provenance scaffolding -------------------------------------------
    # Without a claim reference on an operation, nothing can tell that the KB
    # moved and the specification did not. The scaffold goes in even while the
    # claims are empty -- but only where it is missing, because an operation
    # that has been grounded carries a real digest here.
    for _, _, op in operations(spec):
        op.setdefault("summary", "")
        op.setdefault("description", "")
        op.setdefault("x-airs-provenance", {
            "claims": [],
            "origin_kind": "human",
            "text_digest": "",
        })

    # --- Mintlify MCP surface ---------------------------------------------
    spec["x-mint"] = {
        "mcp": {
            "enabled": True,
            "name": "Prisma AIRS AI Gateway",
            "description": "",
        }
    }

    spec = reorder(spec)

    body = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)
    changed = body != before

    if dry_run:
        stubs = overlay_stubs(spec, dry_run=True)
        if changed or stubs:
            print("build --check: openapi.yaml or the overlay is not up to date; "
                  "run scripts/build.py", file=sys.stderr)
            return 1
        print("build --check: up to date")
        return 0

    # --- write -------------------------------------------------------------
    SPEC.write_text(
        "# Structure only -- see overlays/docs-prose.yaml for every field a\n"
        "# reader reads. Run scripts/build.py to reapply _project/servers.yaml,\n"
        "# the security scheme and tags-map.yaml after editing any of them.\n"
        + body
    )

    if do_drops:
        for target in prune_overlay(spec):
            print(f"    overlay action removed: {target}")
    added = overlay_stubs(spec)
    write_navigation(tagdoc, used, group_of)

    ops = list(operations(spec))
    missing_ids = [f"{m.upper()} {p}" for p, m, o in ops if not o.get("operationId")]
    print(f"operations         {len(ops)}")
    print(f"paths              {len(spec.get('paths', {}))}")
    print(f"schemas            {len(spec.get('components', {}).get('schemas', {}))}")
    print(f"components pruned  {len(orphaned)}")
    print(f"security           1 scheme ({security_overrides} operation overrides "
          f"removed, {len(public_ops)} unauthenticated)")
    print(f"servers            1 root + {control_paths} control-plane")
    print(f"tags               {len(spec['tags'])}")
    print(f"overlay stubs added  {added}")
    print(f"null defaults dropped {len(null_defaults)}")
    print(f"operations lacking operationId {len(missing_ids)}")
    print(f"openapi.yaml       {'rewritten' if changed else 'unchanged'}")

    (ROOT / "build-report.txt").write_text(
        "Generated by scripts/build.py from openapi.yaml.\n\n"
        f"operations                       {len(ops)}\n"
        f"paths                            {len(spec.get('paths', {}))}\n"
        f"schemas                          {len(spec.get('components', {}).get('schemas', {}))}\n"
        f"tags                             {len(spec['tags'])}\n"
        f"\nservers                          1 root + {control_paths} control-plane\n"
        "  Every URL comes from _project/servers.yaml; which plane a path is on\n"
        "  comes from _project/planes.yaml. Edit a host there and rebuild. The\n"
        "  first entry in a plane is the one Mintlify builds its sample from;\n"
        "  the rest appear in its base-URL dropdown.\n"
        + "".join(f"    {plane:<14} {e['url']}"
                  f"{'  -- ' + e['description'] if e.get('description') else ''}\n"
                  for plane, entries in load_servers().items() for e in entries)
        + f"\nsecurity                         1 scheme\n"
        "  One Authorization bearer token, declared once at the root. Six schemes\n"
        "  in five combinations were collapsed into it.\n"
        f"    operation-level overrides removed this run  {security_overrides}\n"
        f"\noperations requiring no authentication  {len(public_ops)}\n"
        "  Inherited `security: []`. Preserved rather than quietly reversed, but\n"
        "  each is a claim that the endpoint is public and wants confirming.\n"
        + "".join(f"    {m}\n" for m in public_ops)
        + f"\ncomponents pruned this run       {len(orphaned)}\n"
        "  Reachability sweep. Zero on a clean tree; it earns its place the next\n"
        "  time a group of operations is dropped.\n"
        + "".join(f"    {c}\n" for c in orphaned)
        + f"\nnull defaults dropped this run   {len(null_defaults)}\n"
        + "".join(f"    {p}\n" for p in null_defaults)
        + f"\noperations lacking operationId   {len(missing_ids)}\n"
        "  Inherited gaps, not introduced here. operationId values are never\n"
        "  renamed, and inventing them is not the same as recovering them, so\n"
        "  they are reported for engineering rather than filled in. Phase 2.\n"
        + "".join(f"    {m}\n" for m in sorted(missing_ids))
        + "\noperations not shipped\n"
        "  Declared by tag in _project/drops.yaml and enforced by this script:\n"
        "  if one reappears in openapi.yaml the build fails.\n"
        + "".join(f"    {t}\n" for t in sorted(drop_tags))
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


def prune_overlay(spec) -> list[str]:
    """Remove actions whose target no longer resolves. Only under --apply-drops.

    The counterpart to overlay_stubs being add-only: when an operation leaves
    the specification its prose has nowhere to land, and check.py fails until
    somebody removes it. That removal is deleting published documentation, so
    it happens on the same deliberate flag that did the dropping -- and the
    prose goes out in the same diff as the operation it described.
    """
    from apply_overlay import apply as apply_overlay_doc

    path = ROOT / "overlays" / "docs-prose.yaml"
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text()) or {}
    header = ""
    for line in path.read_text().splitlines():
        if not line.startswith("#"):
            break
        header += line + "\n"

    _, unresolved = apply_overlay_doc(copy.deepcopy(spec), doc, strict=False)
    if not unresolved:
        return []

    stale = set(unresolved)
    doc["actions"] = [a for a in doc.get("actions") or []
                      if a.get("target") not in stale]
    path.write_text(header + yaml.safe_dump(
        doc, sort_keys=False, allow_unicode=True, width=100))
    return sorted(stale)


def overlay_stubs(spec, dry_run: bool = False) -> int:
    """Top up overlays/docs-prose.yaml with empty stubs for anything new.

    Add-only, on purpose. Every value in that file is published documentation
    that passed the grounding gate, and the cost of regenerating it wholesale is
    that a rebuild silently deletes reviewed prose. So existing actions are
    never touched, never reordered and never removed -- a stub appears for an
    operation or tag that has none, and nothing else changes.

    Stale actions -- a target that no longer resolves, because the operation
    behind it was dropped -- are left for check.py to fail on rather than
    cleaned up here. Deleting authored prose should be a decision, not a
    side effect of running the build.
    """
    path = ROOT / "overlays" / "docs-prose.yaml"
    doc = yaml.safe_load(path.read_text()) if path.exists() else None
    if not doc:
        doc = {
            "overlay": "1.0.0",
            "info": {
                "title": "Prisma AIRS AI Gateway API - documentation prose",
                "version": "0.1.0",
            },
            "actions": [],
        }
    actions = doc.setdefault("actions", [])
    have = {a.get("target") for a in actions}

    wanted: list[tuple[str, dict]] = [("$.info", {"description": ""})]
    for tag in spec["tags"]:
        name = tag["name"].replace("'", "\\'")
        wanted.append((f"$.tags[?(@.name=='{name}')]", {"description": ""}))
    for path_, method, _ in operations(spec):
        wanted.append((jsonpath_for(path_, method), {
            "summary": "",
            "description": "",
            "x-airs-provenance": {
                "claims": [],
                "origin_kind": "human",
                "text_digest": "",
            },
        }))

    new = [{"target": t, "update": u} for t, u in wanted if t not in have]
    if dry_run:
        return len(new)
    if not new:
        return 0

    actions.extend(new)
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "# Empty stubs are generated by scripts/build.py; every written value is\n"
        "# authored by hand as claims are accepted. This file is add-only -- the\n"
        "# build never overwrites or removes an action, because everything here is\n"
        "# published documentation that passed the grounding gate.\n"
        "# Leave a field empty rather than filling it from memory.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    )
    return len(new)


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

    (ROOT / "docs-navigation.json").write_text(
        json.dumps({"groups": groups}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail instead of writing, for CI")
    parser.add_argument("--apply-drops", action="store_true",
                        help="remove operations drops.yaml newly declares, "
                             "instead of failing because they are still there")
    args = parser.parse_args()
    if args.check and args.apply_drops:
        parser.error("--check and --apply-drops are contradictory")
    sys.exit(build(dry_run=args.check, do_drops=args.apply_drops))
