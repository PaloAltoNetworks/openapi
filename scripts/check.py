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
import json
import re
import sys
from pathlib import Path

import yaml
from jsonpath_ng.ext import parse
from openapi_spec_validator import validate as validate_spec

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hrefs  # noqa: E402
from apply_overlay import apply  # noqa: E402
from build import (  # noqa: E402
    GATEWAY_PLANE,
    HTTP_METHODS,
    SECURITY_SCHEME,
    SECURITY_SCHEME_NAME,
    load_planes,
    load_servers,
    load_spanning_tags,
    nav_entries,
    operations,
)

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


def check_prose_came_from_the_overlay(spec) -> None:
    """Every word a reader reads was authored in overlays/docs-prose.yaml.

    openapi.yaml is the published artifact and carries prose, so the rule can no
    longer be "there is no prose here". It is the stronger one instead: strip
    every prose field out of the document, apply the overlay to what is left,
    and the result has to be the document again. Anything typed straight into
    openapi.yaml fails, because the overlay does not put it back.

    That keeps the grounding gate load-bearing. The gate reviews the overlay;
    this check is what makes reviewing the overlay equivalent to reviewing what
    is published.

    A code sample is prose by the same rule. It asserts a base URL, an auth
    header and a set of fields worth sending, none of which a validator checks,
    and Mintlify renders a supplied sample *instead of* the generated one -- so
    one written here quietly overrides the real servers and security blocks.
    The base shipped 106 of them.
    """
    import copy  # noqa: PLC0415

    from build import apply_prose, strip_prose  # noqa: PLC0415

    rebuilt = copy.deepcopy(spec)
    strip_prose(rebuilt)
    try:
        written = apply_prose(rebuilt)
    except (SystemExit, ValueError) as exc:
        fail("prose provenance", f"the overlay does not apply: {exc}")
        return

    if rebuilt != spec:
        fail(
            "prose provenance",
            "openapi.yaml does not equal (openapi.yaml stripped of prose + "
            f"overlays applied). {_first_prose_difference(spec, rebuilt)}. "
            "Prose is authored in overlays/docs-prose.yaml; run "
            "scripts/build.py.",
        )
    else:
        report("prose provenance",
               f"{written} written field(s), all from overlays/docs-prose.yaml")


def _first_prose_difference(spec, rebuilt, pointer: str = "") -> str:
    """Where the two documents part company, as a JSON pointer."""
    if isinstance(spec, dict) and isinstance(rebuilt, dict):
        for key in list(spec) + [k for k in rebuilt if k not in spec]:
            if key not in spec:
                return f"{pointer}/{key} is missing from openapi.yaml"
            if key not in rebuilt:
                return f"{pointer}/{key} is not produced by the overlay"
            if spec[key] != rebuilt[key]:
                return _first_prose_difference(spec[key], rebuilt[key],
                                               f"{pointer}/{key}")
    elif isinstance(spec, list) and isinstance(rebuilt, list) and len(spec) == len(rebuilt):
        for i, (a, b) in enumerate(zip(spec, rebuilt)):
            if a != b:
                return _first_prose_difference(a, b, f"{pointer}/{i}")
    return f"first difference at {pointer or '(root)'}"


def check_dropped_root_keys(spec) -> None:
    """Inherited root keys that are not coming back.

    `x-server-groups` is the one today: not an OpenAPI field, read by nothing,
    and carrying three api.portkey.ai URLs plus two unsubstituted SELF_HOSTED_*
    placeholders. Every other base URL in the corpus moved off api.portkey.ai;
    this was the last copy, and it was public.
    """
    from build import DROP_ROOT_KEYS  # noqa: PLC0415

    present = sorted(DROP_ROOT_KEYS & set(spec))
    if present:
        fail("dropped root keys", f"{present} are back in openapi.yaml; "
                                  f"run scripts/build.py")
    else:
        report("dropped root keys", f"{len(DROP_ROOT_KEYS)} declared, none present")


def check_hrefs(spec) -> None:
    """Every operation has a stable, unique docs URL, consistent with its tag.

    Mintlify generates a page per operation and the href is that page's address.
    Without one the slug is derived from whatever prose the operation happens to
    carry, so it moves when prose lands and no link can point at it -- which is
    what left 122 links in the docs corpus pointing at the old site.

    None of this is verifiable locally: a green build says nothing about whether
    Mintlify renders these pages, and that needs a real preview deployment. What
    is checkable here is everything short of that, so it is checked here.
    """
    recorded, pinned = hrefs.load()
    seen: dict[str, str] = {}
    missing, mismatched, inconsistent, duplicate = [], [], [], []

    for path, method, op in operations(spec):
        where = hrefs.key(method, path)
        href = (op.get("x-mint") or {}).get("href")
        if not href:
            missing.append(where)
            continue
        if href != recorded.get(where):
            mismatched.append(where)
        if href in seen:
            duplicate.append(f"{where} and {seen[href]} both publish {href}")
        seen[href] = where
        # A pinned href is one the scheme no longer derives -- a tag was
        # renamed and the URL was deliberately held still so inbound links keep
        # resolving. Being inconsistent with the tag is the whole point of it,
        # so requiring consistency here would make pinning impossible.
        if where in pinned:
            continue
        wanted = [f"{hrefs.PREFIX}/{hrefs.tag_path(t)}/" for t in op.get("tags") or []]
        if not any(href.startswith(w) for w in wanted):
            inconsistent.append(f"{where}: {href} is not under {wanted}")

    for label, problems in (("operations with no x-mint.href", missing),
                            ("not the URL recorded in _project/hrefs.yaml", mismatched),
                            ("URL collisions", duplicate),
                            ("URL does not match the operation's tag", inconsistent)):
        if problems:
            fail("docs hrefs", f"{len(problems)} {label}: {problems[:3]}")
            return

    detail = (f"{len(seen)} operations, all unique, all tag-consistent, "
              f"all from _project/hrefs.yaml")
    if pinned:
        detail += f"; {len(pinned)} pinned across a tag rename"
    report("docs hrefs", detail)


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


def check_navigation(spec) -> None:
    """docs-navigation.json lists operations, so it is a join key into the
    specification and can go stale. A renamed path leaves a nav row pointing at
    nothing; a new operation is simply never rendered.

    It also fails on a group that scopes itself with `tag`. That key is not in
    Mintlify's navigation schema: it was silently ignored, and every group
    autogenerated the whole document instead, nesting all 42 tags inside each
    one. Nothing caught it here because the file was valid JSON and the
    specification was untouched -- only a rendered site showed it.
    """
    nav = json.loads((ROOT / "docs-navigation.json").read_text())
    expected = nav_entries(spec)

    listed: dict[str, list[str]] = {}
    tag_keys: list[str] = []
    for group in nav.get("groups", []):
        for sub in group.get("pages", []):
            if "tag" in sub:
                tag_keys.append(sub.get("group", "?"))
            listed.setdefault(sub.get("group", "?"), []).extend(sub.get("pages", []))

    problems: list[str] = []
    if tag_keys:
        problems.append(f"{len(tag_keys)} group(s) scope themselves with a `tag` key, "
                        f"which Mintlify ignores -- list the operations instead "
                        f"(e.g. {tag_keys[0]!r})")
    for tag in sorted(set(expected) | set(listed)):
        if expected.get(tag) != listed.get(tag):
            missing = sorted(set(expected.get(tag, [])) - set(listed.get(tag, [])))
            extra = sorted(set(listed.get(tag, [])) - set(expected.get(tag, [])))
            detail = "; ".join(
                part for part in (
                    f"{len(missing)} not in the navigation: {missing[:3]}" if missing else "",
                    f"{len(extra)} in the navigation but not the spec: {extra[:3]}" if extra else "",
                    "same operations, different order" if not missing and not extra else "",
                ) if part
            )
            problems.append(f"{tag}: {detail}")

    if problems:
        fail("navigation", f"docs-navigation.json does not match the spec "
                           f"({len(problems)} problem(s)): " + "; ".join(problems))
    else:
        total = sum(len(v) for v in expected.values())
        report("navigation", f"{len(expected)} tag groups, {total} operations, "
                             f"each listed exactly once")


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


def check_security(spec) -> None:
    """One scheme, one requirement, declared once at the root.

    The base offered six schemes in five combinations. Prisma AIRS takes a
    bearer token in the Authorization header and nothing else, so an
    operation-level `security` block has nothing left to say -- if one appears,
    something is documenting an auth path this API does not have.

    `security: []` is the exception, and not a variation on the requirement but
    its absence: it says the endpoint needs no authentication at all. That is a
    real claim, so it is allowed through and listed every run rather than
    quietly normalised away.
    """
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    root = spec.get("security")
    problems: list[str] = []

    if set(schemes) != {SECURITY_SCHEME_NAME}:
        problems.append(f"expected exactly one scheme named {SECURITY_SCHEME_NAME!r}, "
                        f"found {sorted(schemes)}")
    elif schemes[SECURITY_SCHEME_NAME] != SECURITY_SCHEME:
        problems.append(f"{SECURITY_SCHEME_NAME} is {schemes[SECURITY_SCHEME_NAME]}, "
                        f"expected {SECURITY_SCHEME}")
    if root != [{SECURITY_SCHEME_NAME: []}]:
        problems.append(f"root security is {root}, expected [{{{SECURITY_SCHEME_NAME}: []}}]")

    public: list[str] = []
    for path, method, op in operations(spec):
        if "security" not in op:
            continue
        if op["security"] == []:
            public.append(f"{method.upper()} {path}")
        else:
            problems.append(f"{method.upper()} {path}: operation-level security "
                            f"override {op['security']}")

    if problems:
        fail("security", f"{len(problems)} problem(s)")
        for problem in sorted(set(problems)):
            print(f"          {problem}")
        return

    detail = f"one {SECURITY_SCHEME['scheme']} scheme, {SECURITY_SCHEME_NAME} header"
    report("security", detail)
    for op in public:
        # Not a failure, but it should never go unnoticed that an endpoint is
        # documented as needing no credentials.
        print(f"          unauthenticated: {op}   <- inherited, wants confirming")


def check_planes(spec) -> None:
    """A tag's operations all sit on the same plane.

    The admin split was decided by capability -- "Integrations, MCP
    Integrations, Secret References, Org Guardrails and Deployments are
    administered on /ai_gw/admin/v2" -- but _project/planes.yaml can only
    record paths. Nothing in that file knows that /integrations/{slug}/models
    belongs with /integrations, so a path added later under an admin capability
    can be classified control-plane and read as a deliberate exception.

    Tags are what carries the capability, so that is what this compares. The
    two guardrail surfaces are two tags precisely because they are two
    surfaces; Guardrails is control-plane and Org Guardrails is admin, and this
    check is what stops that distinction from quietly collapsing.

    A tag genuinely on two planes is declared in planes.yaml under
    `tags-spanning-planes`, with the reasoning. `Models` is one: listing the
    models available to a caller is a gateway concern and administering one is
    not.
    """
    plane_of = load_planes()
    allowed = load_spanning_tags()
    planes_of_tag: dict[str, dict[str, list[str]]] = {}
    for path, method, op in operations(spec):
        for tag in op.get("tags") or []:
            planes_of_tag.setdefault(tag, {}).setdefault(
                plane_of.get(path, "unclassified"), []).append(path)

    split = {tag: planes for tag, planes in planes_of_tag.items()
             if len(planes) > 1 and tag not in allowed}
    stale = sorted(t for t in allowed if len(planes_of_tag.get(t) or {}) < 2)
    if stale:
        # An allowance that is not being used any more is a licence nobody
        # reviewed. It should come out of planes.yaml when the tag stops
        # spanning, not sit there ready to excuse the next accident.
        fail("planes", f"tags-spanning-planes lists {stale}, which no longer "
                       f"span two planes")
    if split:
        fail("planes", f"{len(split)} tag(s) span more than one plane")
        for tag, planes in sorted(split.items()):
            print(f"          {tag}")
            for plane, paths in sorted(planes.items()):
                print(f"            {plane}: {', '.join(sorted(set(paths)))}")
        return

    if stale:
        return

    counts: dict[str, int] = {}
    for tag, planes in planes_of_tag.items():
        plane = next(iter(planes)) if len(planes) == 1 else "declared as spanning"
        counts[plane] = counts.get(plane, 0) + 1
    report("planes", "every tag sits on one plane -- "
                     + ", ".join(f"{n} {plane}" for plane, n in sorted(counts.items())))


def check_servers(spec) -> None:
    """Every base URL comes from _project/servers.yaml and nowhere else.

    Server URLs are typed by readers and parsed by machines, so this guards a
    well-meaning search and replace. It walks every `servers` block, not just
    the root: the base left 97 path-level and 2 operation-level overrides, and
    reporting only the root would describe 1 of 264 entries -- a replace that
    missed the other 263 would sail through the check meant to catch it.

    Four things fail here. An operation-level override, because the build
    writes none and one appearing means something else is editing the document.
    A root block that is not exactly the gateway list, or a path-level block
    that is not exactly the list for the plane _project/planes.yaml puts that
    path on -- either is how a stale copy of an old host survives a base URL
    change, and with four planes it is also how an admin endpoint ends up
    published on the control-plane host. And any URL that does not resolve to
    a real one once its variable defaults are substituted; the base published
    three bare placeholders as if they were addresses.

    Comparing whole lists rather than just URLs is what lets the prose check
    leave this subtree alone: `description` on a server entry is prose by the
    letter of the rule, but it cannot be hand-edited into the document without
    failing here, because it has to match _project/servers.yaml exactly.
    """
    defs = load_servers()
    plane_of = load_planes()

    def resolve(entry) -> str:
        url = str(entry.get("url", ""))
        for name, spec_ in (entry.get("variables") or {}).items():
            url = url.replace("{" + name + "}", str(spec_.get("default", "")))
        return url

    problems: list[str] = []
    blocks: list[tuple[str, list]] = [("root", spec.get("servers") or [])]

    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        plane = plane_of.get(path)
        if plane is None:
            problems.append(f"{path}: not classified in _project/planes.yaml")
        elif plane == GATEWAY_PLANE and "servers" in item:
            problems.append(f"{path}: gateway paths take the root server block, "
                            f"but this one carries an override")
        elif plane != GATEWAY_PLANE and "servers" not in item:
            problems.append(f"{path}: on the {plane!r} plane and carries no "
                            f"servers block, so it publishes the gateway host")
        if "servers" in item:
            blocks.append((path, item["servers"]))
            expected = defs.get(plane or "")
            if expected is not None and item["servers"] != expected:
                problems.append(f"{path}: servers block is not the {plane!r} "
                                f"definition from _project/servers.yaml")
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict) and "servers" in op:
                problems.append(f"{method.upper()} {path}: operation-level servers "
                                f"override; the build writes none")

    if not blocks[0][1]:
        fail("servers", "no root server declared")
        return
    if blocks[0][1] != defs[GATEWAY_PLANE]:
        problems.append("root servers block is not the gateway list from "
                        "_project/servers.yaml")

    urls: dict[str, int] = {}
    for _, block in blocks:
        for entry in block:
            url = resolve(entry)
            urls[url] = urls.get(url, 0) + 1
            if not re.match(r"^https?://[^/\s{}]+", url):
                problems.append(f"{url or '(empty)'}: not a URL once variable "
                                f"defaults are substituted")

    if problems:
        fail("servers", f"{len(problems)} problem(s)")
        for problem in sorted(set(problems)):
            print(f"          {problem}")
        return

    report("servers", f"{len(blocks)} block(s), {len(urls)} distinct host(s), "
                      f"all from _project/servers.yaml")
    for url, count in sorted(urls.items(), key=lambda kv: -kv[1]):
        print(f"          {count:4}  {url}")


def main() -> int:
    print(f"checking {SPEC.relative_to(ROOT)}\n")
    spec = yaml.safe_load(SPEC.read_text())

    check_spec_valid(spec)
    check_prose_came_from_the_overlay(spec)
    check_dropped_root_keys(spec)
    check_tags(spec)
    check_navigation(spec)
    check_provenance(spec)
    check_hrefs(spec)
    check_security(spec)
    check_planes(spec)
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
