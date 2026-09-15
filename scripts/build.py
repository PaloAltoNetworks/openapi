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
undropped in _project/drops.yaml, the published docs URLs in _project/hrefs.yaml.

So this script reads openapi.yaml, applies those decisions to it, and writes it
back. It is idempotent: running it on an unchanged repository changes nothing.
That is what keeps "the one place to change a base URL is _project/servers.yaml"
true -- edit a host there, rebuild, and all 67 blocks follow.

**openapi.yaml is the published artifact, prose included.** It used to be
structure-only, with overlays/docs-prose.yaml applied downstream by whoever
rendered it. That arrangement had one reader -- the docs site -- and it was not
applying the overlay, so the moment prose was written the published URL would
have served prose-free pages with nothing failing. The overlay is still the only
place prose is *authored*, and it is still the file the grounding gate reviews;
the build now strips prose from openapi.yaml and reapplies the overlay on every
run, so what ships is resolved and what is reviewed is small. A description
hand-written into openapi.yaml does not survive a build, and check.py fails on
it in the meantime.

What this script does NOT do is author. It never writes a description, and it
never overwrites one: overlays/docs-prose.yaml is topped up with empty stubs for
operations that lack them and is otherwise left alone.

Usage:
    scripts/build.py
    scripts/build.py --check        # fail if anything would change
    scripts/build.py --apply-drops  # remove what drops.yaml newly declares
    scripts/build.py --apply-hrefs  # adopt changed docs URLs (a docs migration)
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hrefs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"

# Root keys that are inherited residue: not OpenAPI, read by nothing here, and
# carrying stale values. Popped on every build rather than deleted once, so a
# re-import cannot bring one back.
#
# x-server-groups held three api.portkey.ai URLs and two unsubstituted
# SELF_HOSTED_* placeholders -- the last surviving copy of the old base URLs
# anywhere in the published corpus, months after servers[] moved off them. It is
# not a standard field, the real servers blocks are generated from
# _project/servers.yaml, and nothing consumes it (confirmed with docs,
# 2026-09-15).
DROP_ROOT_KEYS = {"x-server-groups"}

# Natural-language fields. These are authored in overlays/docs-prose.yaml and
# nowhere else. openapi.yaml carries them because it is the published artifact,
# but it carries them only as the build put them there: strip_prose removes
# every one of these keys on each run and apply_prose writes them back from the
# overlay, so a value typed in here does not survive.
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


def strip_prose(node, keywords: bool = True) -> int:
    """Remove every prose field, so the overlay can put them back.

    This ran once, against the inherited base, and produced a structure-only
    openapi.yaml. It is an applier again, for a different reason: openapi.yaml
    is now the published artifact and carries prose, so the build has to be able
    to say where that prose came from. Stripping and reapplying the overlay on
    every run makes the answer unconditional -- everything a reader reads was
    authored in overlays/docs-prose.yaml and passed the grounding gate. Prose
    typed directly into openapi.yaml does not survive.

    `servers` is skipped: those descriptions come from _project/servers.yaml,
    which check_servers compares block for block, so they are reviewed in the
    one place that decides them.

    `description` and `summary` are *emptied* rather than deleted, and the
    distinction is load-bearing twice over. A Response Object requires
    `description` -- deleting it produces a document that does not validate,
    which is what the first version of this function did. And emptying in place
    keeps the key where the author put it, so re-running the build reorders
    nothing and the diff shows the prose that changed rather than the whole
    file. The rest of PROSE_KEYS is deleted: nothing requires them, and an empty
    `externalDocs` is not a valid object.
    """
    removed = 0
    if isinstance(node, list):
        return sum(strip_prose(v, True) for v in node)
    if not isinstance(node, dict):
        return 0
    if not keywords:
        return sum(strip_prose(v, True) for v in node.values())
    for k in [k for k in node if k in PROSE_KEYS]:
        if k in ("description", "summary") and isinstance(node[k], str):
            if node[k]:
                node[k] = ""
                removed += 1
            continue
        del node[k]
        removed += 1
    for k, v in node.items():
        if k in OPAQUE_KEYS or k == "servers":
            continue
        removed += strip_prose(v, k not in NAME_MAPS)
    return removed


def apply_hrefs(spec, rewrite: bool = False) -> tuple[int, int, list[str]]:
    """Stamp the published docs URL onto every operation, from _project/hrefs.yaml.

    Returns (stamped, added, changed). See scripts/hrefs.py for the scheme and
    for why the recorded value wins over the derived one.
    """
    recorded, pinned = hrefs.load()
    derived = {hrefs.key(m, p): hrefs.derive(m, p, op) for p, m, op in operations(spec)}

    added = [k for k in derived if k not in recorded]
    changed = sorted(k for k, v in derived.items()
                     if k in recorded and recorded[k] != v and k not in pinned)
    stale = sorted(set(recorded) - set(derived))

    if changed and not rewrite:
        raise SystemExit(
            "_project/hrefs.yaml: the docs URL of "
            f"{len(changed)} operation(s) no longer matches the scheme -- "
            "usually a tag rename. These are published URLs and links point at "
            "them, so this is a docs migration rather than a spec edit.\n"
            + "".join(f"    {k}\n        recorded {recorded[k]}\n"
                      f"        derived  {derived[k]}\n" for k in changed[:10])
            + "Run `scripts/build.py --apply-hrefs` to adopt the new URLs and "
              "tell docs, or add the key to `pinned:` to keep the old one.")
    if stale and not rewrite:
        raise SystemExit(
            f"_project/hrefs.yaml records {len(stale)} operation(s) that are no "
            f"longer in openapi.yaml: {stale[:5]}. Run `scripts/build.py "
            f"--apply-drops` to remove them along with their prose.")

    # A pinned key keeps its recorded URL even under --apply-hrefs: that is what
    # pinning is for, and adopting it by accident is the failure it guards.
    published = {
        k: recorded[k] if k in pinned and k in recorded
        else derived[k] if rewrite or k in added
        else recorded[k]
        for k in derived
    }
    if rewrite or added:
        hrefs.save(published, {k for k in pinned if k in published})

    for path, method, op in operations(spec):
        mint = op.setdefault("x-mint", {})
        mint["href"] = published[hrefs.key(method, path)]

    return len(published), len(added), changed


def load_tag_map(path: Path):
    doc = yaml.safe_load(path.read_text())
    names = {entry["to"] for entry in doc["tags"]}
    group_of = {entry["to"]: entry["group"] for entry in doc["tags"]}
    return doc, names, group_of


class Drops(NamedTuple):
    """What _project/drops.yaml declares is not shipped."""
    tags: set[str]
    operations: set[str]
    parameters: set[str]


def load_drops(path: Path) -> Drops:
    if not path.exists():
        return Drops(set(), set(), set())
    doc = yaml.safe_load(path.read_text()) or {}
    return Drops(
        tags=set(doc.get("tags") or []),
        operations={str(e).strip().lower() for e in (doc.get("operations") or [])},
        parameters=set(doc.get("parameters") or []),
    )


def matches_drop(path: str, method: str, op, drops: Drops) -> bool:
    return bool(drops.tags.intersection(op.get("tags") or [])) \
        or f"{method} {path}" in drops.operations


def dropped_params(op, drops: Drops) -> list[dict]:
    """The entries in an operation's `parameters` that drops.yaml names."""
    return [p for p in (op.get("parameters") or [])
            if isinstance(p, dict) and p.get("name") in drops.parameters]


def check_drops(spec, drops: Drops) -> None:
    """Nothing declared dropped has come back.

    While the base was still being rebuilt from, this was an applier: it deleted
    the 61 operations. Now that openapi.yaml is the source, the same file has to
    work the other way round -- as the guard that stops one of them reappearing
    because somebody pasted an endpoint back in or re-imported from upstream.

    Declining to drop something is a decision; it just has to be made in
    drops.yaml rather than by an edit nobody reviewed.
    """
    back: list[str] = []
    for path, method, op in operations(spec):
        if matches_drop(path, method, op, drops):
            back.append(f"{method.upper()} {path}")
        for param in dropped_params(op, drops):
            back.append(f"{method.upper()} {path} ?{param['name']}")
    if back:
        raise SystemExit(
            f"_project/drops.yaml declares these not shipped, but they are in "
            f"openapi.yaml: {sorted(back)}. Run `python scripts/build.py "
            f"--apply-drops` to remove them.")


def apply_drops(spec, drops: Drops) -> list[str]:
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
            if not isinstance(op, dict):
                continue
            if matches_drop(path, method, op, drops):
                del item[method]
                gone.append(f"{method.upper()} {path}")
                continue
            for param in dropped_params(op, drops):
                op["parameters"].remove(param)
                gone.append(f"{method.upper()} {path} ?{param['name']}")
            if not op.get("parameters"):
                op.pop("parameters", None)
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


GATEWAY_PLANE = "gateway"


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
    if GATEWAY_PLANE not in defs:
        raise SystemExit(f"servers.yaml: no {GATEWAY_PLANE!r} plane; it is the "
                         f"root server block and cannot be absent")
    return defs


# A planes.yaml key that is not a plane: the tags allowed to span two. It is
# named here so an unrecognised key is still an error rather than being skipped
# along with it -- a plane misspelled in one of the two files is exactly the
# mistake the cross-check exists to catch.
SPANNING_KEY = "tags-spanning-planes"


def load_spanning_tags() -> set[str]:
    """Tags whose operations are deliberately split across planes."""
    doc = yaml.safe_load((ROOT / "_project" / "planes.yaml").read_text()) or {}
    return set(doc.get(SPANNING_KEY) or [])


def load_planes() -> dict[str, str]:
    """{path: plane}, from _project/planes.yaml.

    Fails on a path in two planes. YAML would accept that silently across two
    blocks and the last one would win, which is a way to move an endpoint to a
    different host by adding a line rather than changing one.
    """
    doc = yaml.safe_load((ROOT / "_project" / "planes.yaml").read_text()) or {}
    plane_of: dict[str, str] = {}
    for plane, paths in doc.items():
        if plane == SPANNING_KEY:
            continue
        for path in paths or {}:
            if path in plane_of:
                raise SystemExit(
                    f"planes.yaml: {path} is in both {plane_of[path]!r} and "
                    f"{plane!r}; a path is on one plane")
            plane_of[path] = plane
    return plane_of


def apply_servers(spec) -> dict[str, int]:
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
    gateway's self-hosted entry does not appear on management operations.

    Returns the number of paths stamped per plane, gateway included -- those
    are the ones that needed no block at all.
    """
    defs = load_servers()
    plane_of = load_planes()

    unknown = {plane: p for p, plane in plane_of.items() if plane not in defs}
    if unknown:
        # The two files are one decision split across two places. A plane named
        # in only one of them means half the decision was written down.
        raise SystemExit(
            f"planes.yaml uses {len(unknown)} plane(s) that servers.yaml does "
            f"not define, so those paths have no base URL: "
            + "; ".join(f"{plane!r} (e.g. {path})"
                        for plane, path in sorted(unknown.items())))

    missing = sorted(set(spec.get("paths") or {}) - set(plane_of))
    if missing:
        # Defaulting would put a management endpoint on the gateway host and
        # look entirely normal while doing it.
        raise SystemExit(
            f"planes.yaml does not classify {len(missing)} path(s): {missing}")

    # The other direction. A classification for a path that no longer exists is
    # harmless to the build and misleading to every reader of the file -- it
    # says a decision is load-bearing when nothing bears on it any more.
    stale = sorted(set(plane_of) - set(spec.get("paths") or {}))
    if stale:
        raise SystemExit(
            f"planes.yaml classifies {len(stale)} path(s) that are not in "
            f"openapi.yaml: {stale}")

    stamped = {plane: 0 for plane in defs}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        item.pop("servers", None)
        for method in [m for m in item if m in HTTP_METHODS]:
            if isinstance(item[method], dict):
                item[method].pop("servers", None)
        plane = plane_of[path]
        stamped[plane] += 1
        if plane != GATEWAY_PLANE:
            item["servers"] = copy.deepcopy(defs[plane])

    spec["servers"] = copy.deepcopy(defs[GATEWAY_PLANE])
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


def build(dry_run: bool = False, do_drops: bool = False,
          do_hrefs: bool = False) -> int:
    spec = yaml.safe_load(SPEC.read_text())
    before = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)
    tagdoc, tag_names, group_of = load_tag_map(ROOT / "tags-map.yaml")

    # Prose comes back at the end, from the overlay and only from the overlay.
    stripped = strip_prose(spec)
    for root_key in sorted(DROP_ROOT_KEYS & set(spec)):
        del spec[root_key]
        print(f"removed root key {root_key} -- inherited residue, read by nothing")

    null_defaults = drop_null_defaults(spec)

    # --- drops --------------------------------------------------------------
    # Before the tag check, because a tag that has just been dropped is also
    # about to leave tags-map.yaml, and the two edits land in the same commit.
    drops = load_drops(ROOT / "_project" / "drops.yaml")
    if do_drops:
        dropped = apply_drops(spec, drops)
        print(f"dropped {len(dropped)} item(s):")
        for entry in dropped:
            print(f"    {entry}")
        for target in prune_overlay(spec):
            print(f"    overlay action removed: {target}")
    else:
        check_drops(spec, drops)

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
    per_plane = apply_servers(spec)
    overridden = sum(n for plane, n in per_plane.items() if plane != GATEWAY_PLANE)
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

    # --- Mintlify --------------------------------------------------------
    spec["x-mint"] = {
        "mcp": {
            "enabled": True,
            "name": "Prisma AIRS AI Gateway",
            "description": "",
        }
    }
    stamped, hrefs_added, _ = apply_hrefs(spec, rewrite=do_hrefs or do_drops)

    # --- prose -------------------------------------------------------------
    # Last, so everything above it is structural and everything a reader reads
    # arrives from one reviewed file.
    added = overlay_stubs(spec, dry_run=dry_run)
    prose = apply_prose(spec)

    spec = reorder(spec)

    body = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)
    changed = body != before

    if dry_run:
        if changed or added:
            print("build --check: openapi.yaml or the overlay is not up to date; "
                  "run scripts/build.py", file=sys.stderr)
            return 1
        print("build --check: up to date")
        return 0

    # --- write -------------------------------------------------------------
    SPEC.write_text(
        "# The published specification, prose included. Generated: prose is\n"
        "# authored in overlays/docs-prose.yaml and applied here by\n"
        "# scripts/build.py, which also reapplies _project/servers.yaml,\n"
        "# _project/hrefs.yaml, the security scheme and tags-map.yaml. Editing\n"
        "# this file by hand is not how any of that changes.\n"
        + body
    )

    write_navigation(spec, tagdoc, used, group_of)

    ops = list(operations(spec))
    missing_ids = [f"{m.upper()} {p}" for p, m, o in ops if not o.get("operationId")]
    print(f"operations         {len(ops)}")
    print(f"paths              {len(spec.get('paths', {}))}")
    print(f"schemas            {len(spec.get('components', {}).get('schemas', {}))}")
    print(f"components pruned  {len(orphaned)}")
    print(f"security           1 scheme ({security_overrides} operation overrides "
          f"removed, {len(public_ops)} unauthenticated)")
    print(f"servers            1 root + {overridden} path override(s): "
          + ", ".join(f"{n} {plane}" for plane, n in per_plane.items()))
    print(f"tags               {len(spec['tags'])}")
    print(f"docs hrefs         {stamped} stamped ({hrefs_added} newly recorded)")
    print(f"prose fields       {stripped} stripped, {prose} written back from the overlay")
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
        f"\ndocs URLs                        {stamped}\n"
        "  x-mint.href on every operation, from _project/hrefs.yaml. These are\n"
        "  public URLs: the build re-derives each one and fails if it has moved,\n"
        "  because a tag rename changes them silently and links point at them.\n"
        f"\nprose                            {prose} written of {len(ops) * 2 + len(spec['tags']) + 1} fields\n"
        "  Authored in overlays/docs-prose.yaml under the grounding gate and\n"
        "  merged into openapi.yaml by this script. Every prose field here is\n"
        "  stripped and reapplied on each build, so nothing reaches the\n"
        "  published document without passing that gate.\n"
        f"\nservers                          1 root + {overridden} path override(s)\n"
        "  Every URL comes from _project/servers.yaml; which plane a path is on\n"
        "  comes from _project/planes.yaml. Edit a host there and rebuild. The\n"
        "  first entry in a plane is the one Mintlify builds its sample from;\n"
        "  the rest appear in its base-URL dropdown. The gateway is the root\n"
        "  block, so its paths carry no override.\n"
        + "".join(f"    {plane:<14} {per_plane.get(plane, 0):>4} path(s)\n"
                  + "".join(
                      f"      {e['url']}"
                      f"{'  -- ' + e['description'] if e.get('description') else ''}\n"
                      for e in entries)
                  for plane, entries in load_servers().items())
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
        + "\nnot shipped\n"
        "  Declared in _project/drops.yaml and enforced by this script: if one\n"
        "  reappears in openapi.yaml the build fails.\n"
        "  tags:\n"
        + "".join(f"    {t}\n" for t in sorted(drops.tags))
        + "  parameters, on any operation:\n"
        + "".join(f"    {p}\n" for p in sorted(drops.parameters))
    )
    return 0


def group_order(tagdoc, group_id: str) -> int:
    ids = [g["id"] for g in tagdoc["groups"]]
    return ids.index(group_id) if group_id in ids else len(ids)


def reorder(spec):
    """Keep the document in conventional OpenAPI order for reviewable diffs."""
    order = ["openapi", "info", "servers", "x-mint",
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


def apply_prose(spec) -> int:
    """Merge overlays/docs-prose.yaml into the document, and count what it wrote.

    The overlay is still the authoring surface and still the file the grounding
    gate reviews. What changed is where the result lands: it used to be applied
    by whoever rendered the specification, which meant the published URL served
    whatever openapi.yaml happened to contain -- structure only, and no build
    error to say so. Applying it here makes the published artifact and the
    reviewed artifact the same document.

    Strict: a target that no longer resolves is an error, not a silent no-op.
    `--apply-drops` is what removes an action whose operation has gone.
    """
    from apply_overlay import apply as apply_overlay_doc

    written = 0
    for path in sorted((ROOT / "overlays").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        if doc.get("overlay") != "1.0.0":
            raise SystemExit(f"{path} is not an Overlay 1.0.0 document")
        apply_overlay_doc(spec, doc)
        written += sum(
            1 for action in doc.get("actions") or []
            for k in ("summary", "description")
            if str((action.get("update") or {}).get(k, "")).strip()
        )
    return written


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


def nav_entries(spec) -> dict[str, list[str]]:
    """`METHOD /path` navigation entries per tag, in document order.

    Every operation carries exactly one tag, so every operation appears in
    exactly one group and none appears twice. `check.py` re-derives this and
    compares, because the entries are a method+path join key into the
    specification and a renamed path would otherwise leave a dead nav row.
    """
    entries: dict[str, list[str]] = {}
    for path, method, op in operations(spec):
        for tag in op.get("tags") or []:
            entries.setdefault(tag, []).append(f"{method.upper()} {path}")
    return entries


def write_navigation(spec, tagdoc, used, group_of) -> None:
    """A docs.json navigation fragment: groups generated from spec tags.

    Each tag group names its operations. Mintlify has no way to say "this
    group is the Assistants tag" -- the `tag` key this file used to carry is
    not in its schema, so it was ignored and every group autogenerated the
    *whole* specification, nesting all 42 tags under each one. Listing the
    operations is how a group gets scoped. It costs a join key to keep in
    sync, which `check.py` now does.

    No `overlays` key either, and its absence is the fix rather than an
    omission. It used to list `overlays/docs-prose.yaml` -- a path in *this*
    repository, resolved against the docs repository, where it does not exist.
    The published document is now resolved before it is committed, so the
    source URL is the whole story and there is nothing left to mis-resolve.
    """
    entries = nav_entries(spec)
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
                                      "PaloAltoNetworks/openapi/refs/heads/main/"
                                      "openapi.yaml",
                            "directory": "api-reference",
                        },
                        "pages": entries[tag],
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
    parser.add_argument("--apply-hrefs", action="store_true",
                        help="adopt changed docs URLs in _project/hrefs.yaml "
                             "instead of failing. These are published URLs: "
                             "this is a docs migration, so tell docs")
    args = parser.parse_args()
    if args.check and (args.apply_drops or args.apply_hrefs):
        parser.error("--check and --apply-* are contradictory")
    sys.exit(build(dry_run=args.check, do_drops=args.apply_drops,
                   do_hrefs=args.apply_hrefs))
