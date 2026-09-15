#!/usr/bin/env python3
"""Docs URLs for every operation, as `x-mint.href`.

Mintlify generates one page per operation from the specification. Without an
`href` those pages have no stable URL: the slug falls out of whatever Mintlify
makes of a summary, so it moves when prose lands and there is nothing a link in
another repository can point at. 122 links in the docs corpus were waiting on
this.

Two things follow from that, and they pull in opposite directions.

**A slug has to be derivable**, or 173 of them cannot be produced or reviewed.
So there is a scheme, below, and every href in _project/hrefs.yaml is checked
against it.

**A published slug has to stop moving**, because it is a public URL and it is
about to be written into 122 link sites. So the derivation is not the source of
truth -- _project/hrefs.yaml is. The derived value is compared against the
recorded one and a difference fails the build. A tag rename changes the derived
href of every operation under it; that is a docs migration, and it should stop
the build and get coordinated rather than silently republish 40 pages at new
addresses.

The scheme:

    /aigw/api-reference/{tag-path}/{operation-slug}

`{tag-path}`  the operation's first tag, kebab-cased, with the `>` hierarchy
              becoming path segments: `Analytics > Graphs` -> `analytics/graphs`.
`{operation-slug}`
              the `operationId`, kebab-cased: `createChatCompletion` ->
              `create-chat-completion`.

For the 45 operations with no `operationId`, the slug is the method and the
path: `GET /analytics/graphs/cache/hit-rate` ->
`get-analytics-graphs-cache-hit-rate`, with `{id}` becoming `by-id`.

Those 45 get a slug but **not** an `operationId`, and the distinction is the
whole reason this file can proceed while Phase 2 cannot. An `operationId` is a
client-facing contract key -- SDK generators turn it into a method name -- so
inventing one is worse than leaving it missing. An href binds nothing in client
code; it is a docs URL, and picking one is a naming decision, not a claim about
the API. Nothing here back-fills `operationId` from a slug.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HREFS = ROOT / "_project" / "hrefs.yaml"

# Where the API reference lives on the docs site. Changing this moves every
# published URL at once, which is why it is one constant and not a template.
PREFIX = "/aigw/api-reference"

HEADER = """\
# The published URL of every operation's reference page. This is a public
# contract, not a derived artifact.
#
# scripts/build.py stamps these into openapi.yaml as `x-mint.href` and
# scripts/check.py enforces them. Keys are "METHOD /path", the same shape
# _project/drops.yaml uses.
#
# The values follow the scheme in scripts/hrefs.py, and the build re-derives
# each one and fails if it does not match what is recorded here. That is
# deliberate: a tag rename silently changes the derived href of every operation
# under it, and these URLs are written into links in the docs repository. A
# change here is a docs migration and wants coordinating, so it stops the build
# rather than republishing 40 pages at new addresses.
#
# Two ways past that failure, and they mean different things:
#
#   scripts/build.py --apply-hrefs   adopt the new URLs. Tell docs; the old
#                                    ones stop resolving.
#   pinned:                          keep the recorded URL even though the
#                                    scheme now derives a different one. For
#                                    when a tag was renamed and the URLs must
#                                    not move.
#
# New operations are added here automatically with their derived href -- there
# is no URL to break yet, so nothing needs deciding.
"""


def kebab(text: str) -> str:
    """`createChatCompletion` -> `create-chat-completion`, `API Keys` -> `api-keys`."""
    out = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", text)
    out = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", out)
    out = re.sub(r"[^A-Za-z0-9]+", "-", out)
    return re.sub(r"-+", "-", out).strip("-").lower()


def tag_path(tag: str) -> str:
    """`MCP Servers > User Access` -> `mcp-servers/user-access`."""
    return "/".join(kebab(part) for part in tag.split(">") if kebab(part))


def path_slug(method: str, path: str) -> str:
    """The fallback slug, for an operation with no `operationId`.

    Method-prefixed because a path alone is not unique -- `GET /api-keys/{id}`
    and `DELETE /api-keys/{id}` are different pages. Path parameters become
    `by-{name}` rather than being dropped, so `/api-keys` and `/api-keys/{id}`
    stay distinguishable.
    """
    parts = [method.lower()]
    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("by-" + kebab(segment[1:-1]))
        else:
            parts.append(kebab(segment))
    return "-".join(p for p in parts if p)


def key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def derive(method: str, path: str, op: dict) -> str:
    tags = op.get("tags") or []
    if not tags:
        # An untagged operation has no navigation group and so no place in the
        # URL tree. check.py already requires every tag to be mapped; this is
        # the case where there is no tag at all.
        raise SystemExit(
            f"{key(method, path)} has no tag, so it has no docs URL. Every "
            f"operation needs one -- see tags-map.yaml.")
    slug = kebab(op["operationId"]) if op.get("operationId") else path_slug(method, path)
    return f"{PREFIX}/{tag_path(tags[0])}/{slug}"


def load() -> tuple[dict[str, str], set[str]]:
    if not HREFS.exists():
        return {}, set()
    doc = yaml.safe_load(HREFS.read_text()) or {}
    return dict(doc.get("hrefs") or {}), set(doc.get("pinned") or [])


def save(hrefs: dict[str, str], pinned: set[str]) -> None:
    HREFS.write_text(
        HEADER
        + yaml.safe_dump({"hrefs": hrefs}, sort_keys=False, allow_unicode=True,
                         width=100, default_flow_style=False)
        + yaml.safe_dump({"pinned": sorted(pinned)}, sort_keys=False,
                         allow_unicode=True, width=100)
    )
