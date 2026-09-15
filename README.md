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
| `openapi.yaml` | Engineering | Paths, schemas, types, `required`, enums, security | API review |
| `overlays/docs-prose.yaml` | Docs | `summary`, `description`, examples, tag prose | **Grounding gate** |
| `tags-map.yaml` | Docs | Tag information architecture and naming | IA review |
| `docs-navigation.json` | Docs | Generated `docs.json` navigation fragment | — |
| `_project/servers.yaml` | Engineering | **The base URLs.** One place, both planes | API review |
| `_project/planes.yaml` | Engineering | Which plane each path is on | API review |
| `_project/drops.yaml` | Product | What is deliberately not shipped, by tag | Product |
| `webhooks/*.schema.json` | Both | The KB sync contract, in both directions | Both |
| `.spectral.yaml` | Both | Lint rules, including the grounding gate | — |
| `.spectral-baseline.json` | — | Inherited defect counts. May shrink, never grow | — |
| `PROSE-INVENTORY.csv` | — | Every stripped prose field: location, size, digest | Worklist |
| `build-report.txt` | — | Counts, and the gaps that want engineering | — |

The split is the point. Engineering ships structural changes without touching a
grounded assertion, and the grounding gate applies to a file that is small and
entirely prose. Retrofitting this means unpicking prose from a specification
that has already merged them, so it is here from the first commit.

The four files under `_project/` are the same idea applied to structure. Each
holds a decision that would otherwise be spread across the document — sixty-odd
`servers` blocks, eleven tag groups' worth of operations — where it can be read,
reviewed and changed in one place. `scripts/build.py` applies them back onto
`openapi.yaml` and CI fails if the document and the decisions disagree.

## What is in it

| | |
|---|---|
| OpenAPI | 3.0.0 |
| Paths / operations | 118 / 181 |
| Components | 475, of which 437 schemas |
| Tags | 41, across 6 navigation groups |
| Servers | 3 hosts — managed gateway, self-hosted gateway, control plane |
| Security | 1 scheme: `Authorization: Bearer` |
| Prose fields stripped | 4,221 |
| Written descriptions | 0 — blocked on KB access |

Eleven capability groups the base carried are **not shipped** — Audit Logs,
Collections, Deployments, Labels, Log Exports, Prompts, Prompt Partials, User
Invites, Users, Virtual Keys and Workspaces > Members. That is 61 operations and
33 paths, declared by tag in `_project/drops.yaml` and enforced on every build:
if one reappears, the build fails rather than quietly republishing it.

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
    "source": "https://raw.githubusercontent.com/PaloAltoNetworks/openapi/main/openapi.yaml",
    "directory": "api-reference",
    "overlays": ["overlays/docs-prose.yaml"]
  },
  "tag": "Chat"
}
```

No stub files, no per-endpoint navigation entries, no join key to keep in sync.
Tag structure in the spec becomes navigation structure — which is why
`tags-map.yaml` is information architecture, not a lookup table.

## Working on it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/check.py           # what CI runs
.venv/bin/python scripts/build.py           # reapply _project/ and regenerate
.venv/bin/python scripts/build.py --check   # fail instead of writing; also CI
.venv/bin/python scripts/apply_overlay.py openapi.yaml overlays/*.yaml -o build/resolved.yaml
```

`scripts/build.py` is idempotent and reads `openapi.yaml` as its own input. Run
it after editing anything under `_project/` or `tags-map.yaml`: it rewrites the
`servers` blocks, the security scheme and the ordered `tags` list from those
files, regenerates `docs-navigation.json` and `build-report.txt`, and tops
`overlays/docs-prose.yaml` up with empty stubs for anything new. It is
**add-only against the overlay** — it never overwrites or deletes an action,
because everything in there is prose that passed the grounding gate.

`scripts/check.py` enforces, and each of these has been confirmed to fail when
violated:

- `openapi.yaml` is a valid OpenAPI document
- **no non-empty `description`, `summary` or code sample in `openapi.yaml`** —
  prose belongs in the overlay, where it gets reviewed
- every tag used is declared and present in `tags-map.yaml`
- every operation carries an `x-airs-provenance` block
- **one security scheme**, declared once at the root, with no operation-level
  override
- **every base URL comes from `_project/servers.yaml`** — every block, not just
  the root, and every URL has to still be a URL
- every overlay target resolves, and the overlaid result still validates
- **the grounding gate**: any overlay action that writes prose must carry a
  non-empty `claims` list, and its `text_digest` must match the prose it ships

`scripts/build.py` additionally refuses to run if a path is missing from
`_project/planes.yaml`, if an operation carries a tag `tags-map.yaml` does not
know, or if anything declared in `_project/drops.yaml` has come back.

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
turned off and replaced by `airs-no-prose-in-spec`, which asserts the opposite.
Custom rules also enforce the provenance block and the tag naming conventions.
Each was confirmed to fire before being relied on.

**Inherited defects are baselined, not silenced.** They keep their real
severity; `.spectral-baseline.json` holds them at their current count. Debt can
shrink, never grow. What is in there today:

| Count | Rule | What it is |
|---|---|---|
| 65 | `no-$ref-siblings` | `title`, `nullable`, `type` and `x-oaiExpandable` beside a `$ref`, which OpenAPI 3.0 silently ignores |
| 53 | `operation-operationId` | The known gap |
| 4 | `array-items` | Arrays with no `items` |
| 1 | `operation-success-response` | `GET /realtime` declares no 2xx |

123 findings across 4 rules, down from 193 across 6 before the Phase 1 drops.
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

`x-airs-provenance` is scaffolded on all 181 operations with `claims` empty. It
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

`PROSE-INVENTORY.csv` records every stripped field by JSON pointer, length and
SHA-256 digest — never the text. It is a worklist for re-grounding, not an
archive to restore from. It is now **frozen**: it could only ever be derived by
diffing against the base, so it describes the strip as it happened and does not
regenerate.

## Known gaps

- **Descriptions are blocked on KB access (Q2).** Structural work is complete;
  prose is not started. This is the intended state, not an omission.
- **Nothing has been verified against the running API.** Structure was carried
  over from the base specification because no credentialled endpoint was
  reachable from this workspace. The left-hand column of the inherit/re-ground
  split is *machine-verifiable in principle* — send a request, compare the
  response — and that verification has not been done.
- **53 operations have no `operationId`** (listed in `build-report.txt`). An
  inherited gap. Inventing identifiers is not the same as recovering them, so
  they are reported for engineering rather than filled in. This also blocks SDK
  generation: Stainless, Speakeasy and Fern all derive method names from it.
- **No code samples.** Mintlify generates one per operation from the schema, and
  it dumps every property: `POST /chat/completions` renders all 24, `seed` and
  `logit_bias` included, because Mintlify does not use `required` to trim the
  example. Hand-written cURL samples for all 181 operations are Phase 2 work.
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
- **123 lint findings are baselined**, all inherited. See the linting section.
- **One operation is documented as needing no credentials** —
  `GET /model-configs/pricing/{provider}/{model}`, which the base declared with
  `security: []`. Preserved rather than quietly reversed: making it require auth
  is as much an unverified claim as leaving it public. `scripts/check.py` prints
  it on every run. Wants engineering.
- **The plane split is 23 decided and 95 inherited.** `_project/planes.yaml`
  decides which of the two base URLs each path gets, and for 95 paths that call
  was read off the base's own per-path server overrides and never independently
  verified. It is recorded per path as `inherited` versus `classification.yaml`,
  and `_project/drop-list.md` marks the difference. Getting one wrong publishes
  a working endpoint against the wrong host.
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
- **No self-hosted control plane is offered.** The gateway has a self-hosted
  entry; the control plane does not. That asymmetry is deliberate — a hybrid
  deployment, self-hosted data plane against a managed control plane, is a
  normal arrangement, and nothing here establishes that a self-hosted control
  plane exists or where it would sit. Offering one would be asserting it. If it
  does exist, it is two lines in `_project/servers.yaml`.
