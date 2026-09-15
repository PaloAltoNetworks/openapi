# Prisma AIRS AI Gateway API — OpenAPI specification

The source of truth for the Prisma AIRS API reference. Replaces
`Portkey-AI/openapi` as the artifact the documentation site renders from.

> **Inherit the shape. Re-ground the prose.**

An OpenAPI specification is published documentation, not configuration. Every
`summary`, `description`, example and enum note in it becomes public prose on
the docs site and in `llms.txt` / `llms-full.txt`. So the grounding rule applies
to this repository exactly as it applies to a hand-written page: every
substantive assertion needs accepted KB support.

This repository was **not** produced by forking and rebranding. Structure was
carried over mechanically and verifiably; all 4,221 natural-language fields were
stripped. Where the KB does not yet support a description, it is empty. An empty
description renders as a visible gap and shows up in coverage. A confident,
plausible, wrong description is invisible and survives review.

## Layout

| Path | Owner | Contents | Review |
|---|---|---|---|
| `openapi.yaml` | Generated | **The published document.** Structure and resolved prose | — |
| `overlays/docs-prose.yaml` | Docs | Where `summary`, `description`, examples and tag prose are *written* | **Grounding gate** |
| `tags-map.yaml` | Docs | Tag information architecture and naming | IA review |
| `docs-navigation.json` | Docs | Generated `docs.json` navigation fragment | — |
| `_project/servers.yaml` | Engineering | **The base URLs.** One place, all four planes | API review |
| `_project/planes.yaml` | Engineering | Which plane each path is on, and which tags may span two | API review |
| `_project/hrefs.yaml` | Docs | **The published URL of every operation's page** | Docs migration |
| `_project/drops.yaml` | Product | What is deliberately not shipped: tags, operations, parameters | Product |
| `webhooks/*.schema.json` | Both | The KB sync contract, in both directions | Both |
| `.spectral.yaml` | Both | Lint rules, including the grounding gate | — |
| `.spectral-baseline.json` | — | Inherited defect counts. May shrink, never grow | — |
| `build-report.txt` | — | Counts, and the gaps that want engineering | — |

The split is the point, and it is a split between *where prose is written* and
*what gets published* — not between two files someone else has to join up.
`openapi.yaml` is the published document, prose included; `scripts/build.py`
strips every prose field out of it and reapplies the overlay on every run. So
the grounding gate reviews a file that is small and entirely prose, and what it
reviews is byte-for-byte what ships. A description typed straight into
`openapi.yaml` does not survive a build, and `scripts/check.py` fails on it
until one is run.

It used to work the other way: `openapi.yaml` was structure-only and the overlay
was applied downstream by whoever rendered it. That had exactly one reader, the
docs site, and it was not applying the overlay — so the published URL served
prose-free pages and nothing failed. It cost nothing while every description was
empty, and it would have cost the whole gate the day one was written.

The four decision files under `_project/` are the same idea applied to
structure. Each
holds a decision that would otherwise be spread across the document — sixty-odd
`servers` blocks, eleven tag groups' worth of operations, 187 page URLs — where
it can be read, reviewed and changed in one place. `scripts/build.py` applies
them back onto `openapi.yaml` and CI fails if the document and the decisions
disagree.

## What is in it

| | |
|---|---|
| OpenAPI | 3.0.0 |
| Paths / operations | 121 / 187 |
| Components | 480, of which 442 schemas |
| Tags | 42, across 6 navigation groups |
| Servers | 5 hosts across 4 planes — managed and self-hosted gateway, control plane, admin, admin-in-path |
| Security | 1 scheme: `Authorization: Bearer` |
| Docs URLs | 187 — one `x-mint.href` per operation, all unique |
| Prose fields stripped | 4,221 |
| Written descriptions | 0 — blocked on KB access |

Eleven capability groups the base carried are **not shipped** — Audit Logs,
Collections, Labels, Log Exports, Prompts, Prompt Partials, User Invites, Users,
Virtual Keys, Workspaces and Workspaces > Members. That is 63 operations and 34
paths, declared by tag in `_project/drops.yaml`.

Deployments was a twelfth until Phase 2, when it turned out to be exposed on the
admin plane after all. Un-dropping is recovery rather than a flag flip: the base
was retired at the end of Phase 1, so removing the line brought nothing back and
the six operations were recovered from the pre-drop revision. What came back is
the inherited shape, and nothing has checked it against the API now serving it.

`drops.yaml` also names **parameters** that must not appear on any operation,
matched on `name` wherever they occur. Today that is `organisation_id`, which
engineering confirmed is not needed as a parameter anywhere; it was a query
parameter on `GET /guardrails` and `GET /mcp-integrations`. A name rather than a
list of sites, because the objection is to the parameter itself — listing sites
would let it reappear on a new operation.

The declaration is enforced in both directions. A normal build only *checks* it:
if something named there is in `openapi.yaml`, the build fails rather than
quietly republishing it. Removing something is a separate, deliberate act — add
it and run `scripts/build.py --apply-drops` once, which deletes the operations
and parameters, prunes the components nothing reaches any more, and removes the
now-stale overlay actions. The deletion then shows up in the diff of
`openapi.yaml` where a reviewer sees it, instead of happening on every build.

## How the docs consume it

Not with stub files. The predecessor arrangement was 219 hand-written `.mdx`
files, each binding to one operation by `openapi: post /chat/completions`
frontmatter, each separately listed in navigation. That makes **method+path the
join key**: renaming a path silently unbinds a page, which still builds and just
stops rendering an operation.

Instead, `openapi` goes on a navigation *group* and Mintlify generates a page
per operation. `docs-navigation.json` is generated from the spec's own tags:

```json
{
  "group": "Chat",
  "openapi": {
    "source": "https://raw.githubusercontent.com/PaloAltoNetworks/openapi/refs/heads/main/openapi.yaml",
    "directory": "api-reference"
  },
  "pages": ["POST /chat/completions"]
}
```

No stub files. Tag structure in the spec becomes navigation structure — which
is why `tags-map.yaml` is information architecture, not a lookup table.

The `pages` list is the one join key that survived, and it is here because
Mintlify has no other way to scope a group. This file used to say `"tag":
"Chat"` instead — a key that is not in Mintlify's navigation schema, so it was
ignored, and every group autogenerated the *whole* document with all 42 tags
nested inside it. It shipped that way because nothing here could see it: the
JSON was valid, the spec was untouched, and only a rendered site showed the
fault. `check.py` now re-derives the lists from the spec and compares, so a
renamed path fails the build rather than leaving a dead nav row.

There is no `overlays` key, and its absence is a fix rather than an omission. It
used to list `overlays/docs-prose.yaml` — a path in *this* repository, resolved
against the *docs* repository, where no such file exists. That URL is now the
whole story: it serves the resolved document.

**Two things in here are load-bearing joins with the docs repository, and
changing either is a migration rather than a spec edit.**

- **Tag names.** A tag is the join between an operation and a navigation group.
  Rename one and the group silently empties; add one and it goes unrendered.
  Docs run `check_nav_matches_remote.py` against this repository and it fails on
  drift in either direction, but only after a change ships. So a rename or an
  addition wants telling them first.
- **`x-mint.href`.** Mintlify generates a page per operation, and the href is
  that page's address. Without one the slug is derived from whatever prose the
  operation carries, which means it moves when prose lands and nothing can link
  to it. They are recorded in `_project/hrefs.yaml`:

```
/aigw/api-reference/{tag-path}/{operation-slug}

/aigw/api-reference/chat/create-chat-completion      # from operationId
/aigw/api-reference/analytics/graphs/get-analytics-graphs-cost
```

`{tag-path}` is the tag kebab-cased, with `>` becoming a path separator, and
`{operation-slug}` is the `operationId` kebab-cased. The **45 operations with no
`operationId` get a slug from their method and path** — `by-id` for a `{id}`
segment — and *not* an `operationId`. The distinction is why this could be done
while Phase 2 waits: an `operationId` is a contract key that SDK generators turn
into method names, so inventing one is worse than leaving it missing, whereas an
href binds nothing in client code. Nothing back-fills one from the other.

The build re-derives every href and **fails if it no longer matches what is
recorded**, because a tag rename moves them all at once and links point at them.
Two ways past it, meaning different things: `scripts/build.py --apply-hrefs`
adopts the new URLs (tell docs — the old ones stop resolving), or a key listed
under `pinned:` keeps its recorded URL through a rename.

None of this can be verified here. A green build says nothing about whether
Mintlify renders the pages; that needs a preview deployment, and the Mintlify
check on PR #1076 came back SKIPPED. What CI can prove — presence, uniqueness,
tag consistency, agreement with `_project/hrefs.yaml` — it proves.

## Working on it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/check.py           # what CI runs
.venv/bin/python scripts/build.py           # reapply _project/ and regenerate
.venv/bin/python scripts/build.py --check   # fail instead of writing; also CI
.venv/bin/python scripts/build.py --apply-hrefs   # adopt moved docs URLs
.venv/bin/python scripts/build.py --apply-drops   # remove what drops.yaml declares
```

`scripts/build.py` is idempotent and reads `openapi.yaml` as its own input. Run
it after editing anything under `_project/`, `tags-map.yaml` or the overlay: it
rewrites the `servers` blocks, the security scheme, the ordered `tags` list and
every `x-mint.href` from those files, strips the prose and reapplies the
overlay, and regenerates `docs-navigation.json` and `build-report.txt`. It is
**add-only against the overlay** — it never overwrites or deletes an action,
because everything in there is prose that passed the grounding gate — and it
tops the overlay up with empty stubs for anything new.

`scripts/check.py` enforces, and each of these has been confirmed to fail when
violated:

- `openapi.yaml` is a valid OpenAPI document
- **every prose field in `openapi.yaml` is what the overlay produces** — strip
  the prose, reapply the overlay, and the result has to be the document again.
  Anything typed in directly fails, because the overlay does not put it back
- **no `x-server-groups`**, or any other inherited root key declared dead
- every tag used is declared and present in `tags-map.yaml`
- **`docs-navigation.json` lists every operation exactly once**, in spec order,
  under the right tag — and no group scopes itself with the `tag` key Mintlify
  ignores
- every operation carries an `x-airs-provenance` block
- **every operation has an `x-mint.href`**, all unique, each under its own tag's
  path, each equal to what `_project/hrefs.yaml` records
- **one security scheme**, declared once at the root, with no operation-level
  override
- **every base URL comes from `_project/servers.yaml`** — every block, not just
  the root, matching the plane `_project/planes.yaml` puts that path on, and
  every URL has to still be a URL
- **every tag sits on one plane**, unless `planes.yaml` declares it as spanning
  two and says why
- every overlay target resolves, and the overlaid result still validates
- **the grounding gate**: any overlay action that writes prose must carry a
  non-empty `claims` list, and its `text_digest` must match the prose it ships

`scripts/build.py` additionally refuses to run if a path is missing from
`_project/planes.yaml`, classified there but absent from the spec, listed under
two planes, or on a plane `_project/servers.yaml` does not define; if an
operation carries a tag `tags-map.yaml` does not know; or if anything declared
in `_project/drops.yaml` has come back.

A code sample counts as prose here, which is not obvious. A sample asserts a
base URL, an auth header and a set of fields worth sending — none of it checked
by a validator — and Mintlify renders a supplied sample *instead of* the one it
would generate. The 106 the base carried therefore silently overrode both the
base URL and the auth scheme, telling readers to call `api.portkey.ai` with
headers this API does not read. They are stripped, and CI fails if one returns.

### Linting

```bash
scripts/lint.py              # check against the baseline
scripts/lint.py --update     # re-record it, then review the diff
```

`.spectral.yaml` is unusual in two ways, both following from the grounding model
rather than from taste.

**The stock OpenAPI style guide is inverted.** It wants a description on
everything; `operation-description`, `info-description` and `info-contact` are
turned off, because an empty description is the correct state until an accepted
claim supports it. In their place `airs-prose-is-grounded` asserts the condition
that actually matters: prose may be here, but not with an empty `claims` list.
Custom rules also enforce the provenance block, the `x-mint.href`, and the tag
naming conventions. Each was confirmed to fire before being relied on.

`airs-prose-is-grounded` replaced `airs-no-prose-in-spec`, which asserted that
prose in `openapi.yaml` was empty. That was right while the document was
structure-only and would have failed on the first description written — a rule
destined to be silenced rather than satisfied. The assertion underneath it
survived the move and got sharper.

**Inherited defects are baselined, not silenced.** They keep their real
severity; `.spectral-baseline.json` holds them at their current count. Debt can
shrink, never grow. What is in there today:

| Count | Rule | What it is |
|---|---|---|
| 64 | `no-$ref-siblings` | `title`, `nullable`, `type` and `x-oaiExpandable` beside a `$ref`, which OpenAPI 3.0 silently ignores |
| 45 | `operation-operationId` | The known gap |
| 4 | `array-items` | Arrays with no `items` |
| 1 | `operation-success-response` | `GET /realtime` declares no 2xx |

114 findings across 4 rules, down from 193 across 6 before the drops.
`oas3-unused-component` went from 26 to **0**: the drop pruned every component
nothing reaches, including 52 the base was already carrying unreferenced.

The `nullable`-beside-`$ref` cases are the interesting ones: the author meant
nullable and OpenAPI 3.0 drops it. Fixing that means restructuring into `allOf`,
which asserts a behaviour, so it is engineering's call and not done here.

For reference, the base specification scored 549 findings — including 144
examples that failed to validate against their own schemas, which is
independent support for not inheriting examples.

### Writing a description

Only with an accepted claim. In `overlays/docs-prose.yaml`:

```yaml
- target: $.paths['/chat/completions'].post
  update:
    summary: ""
    description: ""
    x-airs-provenance:
      claims:
        - id: accepted-claim-id
          revision: claim-revision-or-digest
      origin_kind: human          # human | generated | mixed
      text_digest: sha256-...     # of the prose in this same action
```

Prose and provenance are written in one action so they cannot drift apart.
`origin_kind` and `text_digest` are also what make echo protection work if a
description is ever machine-drafted.

## Provenance and drift

The specification is a **second trusted source**, authoritative in its own
domain and not subordinate to the KB (recorded exemption, Q6, 2026-09-07). The
reconciliation loop is therefore three-node — KB ↔ spec ↔ docs — and drift from
*either* side is a defect, with no authoritative side to fall back on.

`x-airs-provenance` is scaffolded on all 187 operations with `claims` empty. It
is not only "which claim supports this description"; it is the **join key that
makes drift detectable**. Without a claim reference on an operation, nothing can
tell that the KB moved and the spec did not.

It costs nothing while authoring and is prohibitively expensive to retrofit,
because reconstructing which claim supported a description after the fact is
indistinguishable from inventing it.

### Sync

Bidirectional and webhook-driven. Polling is the backstop, not the mechanism.

| Direction | Trigger | Workflow | Effect |
|---|---|---|---|
| spec → KB | push to `main` touching `openapi.yaml` or `overlays/` | `notify-kb.yml` | POSTs `spec.changed`; the KB marks cited claims for review |
| KB → spec | `repository_dispatch`, type `kb-claims-changed` | `kb-drift.yml` | Runs the drift check, opens an issue |
| backstop | weekly cron | `kb-drift.yml` | Catches a missed webhook |

`scripts/emit_change_event.py` classifies what moved. The distinction that
matters to the KB is `structure_changed` versus `prose_changed`: the shape
moving may invalidate a claim, docs moving usually does not.

It also grades the diff with **oasdiff**, so the payload carries a reason rather
than a boolean — `new-required-request-parameter` and
`api-path-removed-without-deprecation` tell the KB far more than "structure
changed". `breaking-changes.yml` runs the same grading on pull requests and
comments the result. Neither blocks: a breaking change is sometimes the correct
change, and this repository is not where that is decided.

```bash
scripts/emit_change_event.py --base HEAD~1 --head HEAD -o build/event.json
scripts/drift.py --manifest kb-manifest.json      # or --manifest-url
scripts/drift.py --dry-run                        # no KB: coverage only
```

`scripts/drift.py` reports six kinds of finding, each confirmed to fire against
a synthetic manifest:

| Finding | Meaning |
|---|---|
| `unknown-claim` | The spec cites a claim the KB does not have |
| `revision-drift` | The KB moved and the spec did not, or the reverse |
| `unaccepted-claim` | Cited claim is retracted, superseded or draft |
| `orphan-claim` | KB holds an API-domain claim nothing cites |
| `ungrounded` | Prose written with no claim behind it |
| `stale-digest` | Prose edited after grounding, digest left behind |

**It never fixes anything.** Drift is a defect regardless of which artifact
moved, and there is no authoritative side to fall back on — so it reports,
exits non-zero, and a maintainer decides. Never automatically, never
last-write-wins.

Both workflows are inert until their secrets (`KB_WEBHOOK_URL`,
`KB_WEBHOOK_TOKEN`, `KB_MANIFEST_URL`) exist, but not dormant: `notify-kb`
builds and schema-validates the payload on every run, so the contract is
exercised before the endpoint it talks to does.

## Naming

Rule of thumb: *if a reader would type it or a machine would parse it, it does
not change.*

**Never renamed** — every `x-portkey-*` header parameter, `operationId` values,
component and schema names, property names, enum values. These are things a
reader types or a machine parses, and renaming one breaks a caller.

**Not renamed quietly** — `x-mint.href` and, because it derives them, every tag
name. A published URL is something a reader has bookmarked and another
repository has linked to; the rule of thumb applies to it in full. It is not
frozen, because a page sometimes has to move — it is held in
`_project/hrefs.yaml` so that moving one stops the build and gets coordinated
instead of shipping.

**Two deliberate exemptions**, both decided 2026-09-15:

- **The whole `servers` subtree.** The base URLs are Prisma AIRS's, not the
  base's. They come from `_project/servers.yaml` and nowhere else — one place
  to edit, and `scripts/check.py` compares every block in the document against
  it whole, so a host or a label that was not written there fails. That is also
  why `servers[].description` is exempt from the no-prose rule: it is prose by
  the letter of it, but it cannot enter the document without passing review of
  that one file, which is the property the grounding gate protects.
- **Security scheme keys.** Six schemes in five combinations became a single
  `Authorization` bearer token. A scheme key is a label on a requirement rather
  than an identifier a caller sends, and leaving `Portkey-Key` pointing at
  `x-portkey-api-key` would have documented a header this API does not read.
  `scripts/check.py` enforces that exactly one scheme exists.

The seven `x-portkey-*` header parameters are untouched: they carry tracing,
metadata and cache controls, not authentication, and dropping them alongside
the auth schemes would have removed working functionality nobody asked to lose.

**Rebranded** — `info.title` to `Prisma AIRS AI Gateway API`; all descriptions
and summaries, which are subject to grounding and so are rewritten rather than
translated; tag descriptions.

**Tag names** were redesigned rather than inherited (see `tags-map.yaml`).
Title Case, spaces not hyphens, initialisms uppercased, `Parent > Child`
retained for genuine sub-resources. `Fine-tuning` and `Finetune` were two
spellings of one concept and are merged.

## One spec, no variants

Launch covers managed and hybrid, and product behaviour is deployment-invariant.
Multiple entries in `servers[]` are fine; divergent content is not. Do not
produce environment-variant specs or fork descriptions per deployment.

The self-hosted gateway entry is what that looks like in practice: one document,
one set of operations and schemas, two addresses to reach the same API. Mintlify
renders it as a "Select base URL" dropdown on gateway operations and rebuilds
the code sample from whichever the reader picks (verified against `mint
4.2.893`). The managed host is first and so is the default.

Two constraints on that entry, both learned the hard way:

- **Literal URLs, not server variables.** A `{host}` variable with a default is
  the mechanism OpenAPI provides for exactly this, and Mintlify cannot resolve
  it: a templated `url` renders *"A valid request URL is required to generate
  request examples"* and emits **no code sample at all**, on every operation.
- **The placeholder host is under `example.com`.** RFC 2606 reserves it and IANA
  will never delegate it. The obvious spelling, `self-hosted-gateway-url.com`,
  is an ordinary registrable domain — unregistered as of 2026-09-15 — and
  publishing it beside `Authorization: Bearer <token>` would hand whoever buys
  it a stream of live credentials from readers who copy the sample and forget to
  change the host. A reserved domain fails closed.

### The four planes

One document, four base URLs, and which one an operation publishes is decided in
`_project/planes.yaml` rather than written next to the operation.

| Plane | URL | Paths |
|---|---|---|
| `gateway` | `https://aigw.portkey.ai/v1` (+ the self-hosted entry) | 52 |
| `control-plane` | `https://api.apps.paloaltonetworks.com/ai_gw/v2` | 51 |
| `admin` | `https://api.apps.paloaltonetworks.com/ai_gw/admin/v2` | 14 |
| `admin-in-path` | `https://api.apps.paloaltonetworks.com/ai_gw` | 4 |

The gateway is the root `servers` block, so its paths carry no override at all.
Everything else gets a generated one, because OpenAPI gives a path no way to
refer back to a server declared once at the root — and a path-level block
*replaces* the root list rather than extending it, which is what stops the
self-hosted gateway entry from appearing on a management operation.

`admin-in-path` is the same host as `admin`, split out for a reason worth
knowing: the API serves the org-level guardrails at `/ai_gw/admin/v2/guardrails`
and the control-plane ones at `/ai_gw/v2/guardrails`, and **a document cannot
hold two paths spelled the same**. For those four, and only those four, the
server stops at `/ai_gw` and the `/admin/v2` prefix moves into the path key. The
rendered URL is identical either way; what changes is which file the prefix is
written in. Keeping it in `servers.yaml` for the rest of the admin plane is what
kept fourteen existing paths, their `operationId`s and their published docs URLs
from moving to accommodate one collision.

Two invariants hold this together, both in `scripts/check.py`:

- **Every block matches the plane its path is on.** Not just "matches one of
  them" — an admin endpoint carrying the control-plane block is a failure, and
  so is an admin path carrying no block at all, since that publishes it on the
  gateway host.
- **A tag sits on one plane.** The split was decided by capability and
  `planes.yaml` can only record paths, so a new path under an admin capability
  can be classified control-plane and look entirely deliberate. Tags carry the
  capability, so that is what is compared. `Models` is the one declared
  exception — listing the models available to a caller is a gateway concern,
  administering one is not — and it is written down in `planes.yaml` under
  `tags-spanning-planes`. An allowance that stops being needed fails too.

## Provenance of this repository

Structure was derived from `Portkey-AI/openapi` at commit
`3fa53f23216a2ba6c57e2f9eb538753bf9461f7e` (2026-09-04).

**That linkage is closed.** It was a live relationship for the length of Phase 1
and no longer is: the base is not fetched, not compared against, and not
committed here. `openapi.yaml` is the source of truth for structure, and Portkey
is history rather than an upstream.

Closing it was deliberate and deferred until last. While the sweeping changes
were being made, a fidelity check compared every surviving operation against the
base — that is what proved the drops *removed* 61 operations and *reshaped*
none, which is the one thing that could not be established any other way. Once
that was established the check had nothing left to say, and keeping it would
have meant treating every future intentional change as drift from a
specification for a different product.

What replaces it is `scripts/build.py --check`, which asks a narrower question
about files that still decide things: does `openapi.yaml` agree with
`_project/servers.yaml`, `_project/planes.yaml`, `_project/drops.yaml` and
`tags-map.yaml`? The base is gone; the decisions taken against it are still
enforced.

The strip itself was recorded in `PROSE-INVENTORY.csv` — a pointer, length and
SHA-256 digest per field, never the text. It was frozen at the end of Phase 1,
because it could only be derived by diffing against the base, and removed on
2026-09-15: 3,618 of its 4,221 pointers had come to name operations and
components that the drops deleted. The worklist it was meant to be is
`overlays/docs-prose.yaml`, which has one stub per authoring site and is
checked on every build. Recoverable from history if the digests are ever
wanted.

## Known gaps

- **Descriptions are blocked on KB access (Q2).** Structural work is complete;
  prose is not started. This is the intended state, not an omission.
- **Nothing has been verified against the running API.** Structure was carried
  over from the base specification because no credentialled endpoint was
  reachable from this workspace. The left-hand column of the inherit/re-ground
  split is *machine-verifiable in principle* — send a request, compare the
  response — and that verification has not been done.
- **45 operations have no `operationId`** (listed in `build-report.txt`). An
  inherited gap. Inventing identifiers is not the same as recovering them, so
  they are reported for engineering rather than filled in. This also blocks SDK
  generation: Stainless, Speakeasy and Fern all derive method names from it.
  They *do* have docs URLs, derived from method and path — an href is not a
  contract key, and the two are deliberately not joined up.
- **Nothing has confirmed that the generated pages exist.** `x-mint.href` is
  checked here for presence, uniqueness and tag consistency, which is everything
  short of the thing that matters: whether Mintlify renders a page at each of
  those addresses. That needs a preview deployment, and the Mintlify check on
  PR #1076 came back SKIPPED. A green build is not evidence.
- **No code samples.** Mintlify generates one per operation from the schema, and
  it dumps every property: `POST /chat/completions` renders all 24, `seed` and
  `logit_bias` included, because Mintlify does not use `required` to trim the
  example. Hand-written cURL samples for all 187 operations are Phase 3 work.
  Until then the generated sample is correct but verbose. cURL only is the
  intended end state — a single `x-codeSamples` entry suppresses the other
  language tabs, and other languages are a separate decision.
- **`required` is unfilled on five request bodies** — `POST /configs`,
  `POST /admin/workspaces`, and the `PUT`s for configs, providers and
  workspaces. `required` is a claim about the API contract and nothing here
  establishes it; getting it wrong means a reader omits a field the API rejects.
  For the three `PUT`s, requiring nothing may already be correct, since a
  partial update where every field is optional is a normal design. Wants
  engineering.
- **114 lint findings are baselined**, all inherited. See the linting section.
- **One operation is documented as needing no credentials** —
  `GET /model-configs/pricing/{provider}/{model}`, which the base declared with
  `security: []`. Preserved rather than quietly reversed: making it require auth
  is as much an unverified claim as leaving it public. `scripts/check.py` prints
  it on every run. Wants engineering.
- **`organisation_id` is gone as a parameter but survives as a response
  field.** Engineering's instruction was scoped to parameters, and it was
  followed to that scope. Fifteen component schemas still carry an
  `organisation_id` property, three of them with it in `required`. Whether
  those go too is a different question — removing a response field is a
  breaking change for anyone reading it, where removing a request parameter is
  not — and nobody has asked it. Wants engineering.
- **The plane split is 39 decided and 82 inherited.** `_project/planes.yaml`
  decides which of the four base URLs each path gets, and for 82 paths that call
  was read off the base's own per-path server overrides and never independently
  verified. It is recorded per path in that file — `inherited` against a named
  decision — so the difference is readable there. Getting one wrong publishes a
  working endpoint against the wrong host.
- **The recovered Deployments schemas are unexamined.** Deployments was dropped
  in Phase 1 on an engineering list and un-dropped in Phase 2 as an admin-plane
  capability, which meant recovering six operations from the pre-drop revision.
  The build strips what is obviously stale — `api.portkey.ai` samples, a
  `Portkey-Key` override — but the request and response schemas are Portkey's
  and nobody has called `/ai_gw/admin/v2/deployments` to see whether they still
  describe it. First item in Phase 3.
- **Agent Integrations and Plugins are named but absent.** Both were named as
  admin-plane capabilities; neither exists in this document, in the base, or in
  the drop list. They need an endpoint list before they can be classified.
- **`info.contact`, `license` and `termsOfService` were dropped.** The base
  pointed all three at Portkey resources.
- **JSON Schema constraints were retained.** `default`, `maximum`, `minLength`
  and similar are inherited unverified. They are machine-verifiable against a
  running API, which is the same justification that keeps types and `required`,
  but a strict reading of "any stated limit, default, or behaviour" would strip
  them. Worth a decision. Nine `default: null` entries were dropped because they
  made the base specification fail validation.
- **`x-mint.mcp` is enabled globally**, mirroring the base. Every operation is
  agent-callable, including control-plane mutations such as
  `DELETE /guardrails/{guardrailId}`. This was a deliberate product choice;
  narrowing it means per-operation `x-mint.mcp` blocks.
- **There is no self-hosted control plane.** The gateway has a self-hosted
  entry; the control plane does not. Confirmed with engineering on 2026-09-15,
  so the asymmetry is the product, not a gap in the document: a self-hosted data
  plane talks to the managed control plane.
