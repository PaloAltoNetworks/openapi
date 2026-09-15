# TODO

Phase-based task list. Rationale and findings live in `PLAN.md`; this is the
checklist. Strike through as they land.

**This file states current shape, not history.** The table below is the document
as it stands right now; completed tasks record what they *changed* rather than
what the totals were when they landed, so nothing in the body competes with the
table. When a phase closes, any task it did not finish moves to **Residue** at
the bottom rather than staying unticked inside a finished phase.

Every task ends green — `build.py --check`, `check.py` and `lint.py` passing —
so work can stop at any line.

## Current shape

| | Base | Now |
|---|---|---|
| Paths | 151 | **121** |
| Operations | 242 | **187** |
| Components | 578 | **480** |
| Tags | 52 | **42** |
| Spectral findings | 193 | **114** |
| Servers | — | **5 hosts across 70 blocks, 4 planes** |
| Operations without `operationId` | — | **45** |
| Docs URLs (`x-mint.href`) | — | **187, all unique** |
| Written descriptions | — | **0, by design** |
| `info.version` | — | **3.0.0** |

All five hosts are generated from `_project/servers.yaml`: the managed and
self-hosted gateways, and one entry each for the `control-plane`, `admin` and
`admin-in-path` planes. Which plane a path is on is `_project/planes.yaml`. The
114 Spectral findings are 64 `no-$ref-siblings`, 45 `operation-operationId`, 4
`array-items` and 1 `operation-success-response` — unchanged by the 14
operations Phase 2 added, all of which carry an `operationId`.

---

## Phase 1 — the sweeping changes — **complete, 2026-09-15**

All four questions answered. Control-plane base URL confirmed the same day.
Tasks 4 and 5 were moved out by decision rather than left undone — they are in
Phase 3 today — and one item became residue at the bottom of this file.

### 1. ~~Drop the marked control-plane operations~~ — done 2026-09-15
- [x] ~~Delete the 11 tag groups marked `[DROPPED]`: Audit Logs, Collections, Deployments, Labels, Log Exports, Prompt Partials, Prompts, User Invites, Users, Virtual Keys, Workspaces > Members~~
- [x] ~~Also drop the two gateway `Prompts` paths — `/prompts/{promptId}/completions` and `/prompts/{promptId}/render` — so the whole Prompts surface goes together (Q-A)~~
- [x] ~~Removed **33 paths, 61 operations**~~ — exactly as forecast
- [x] ~~Prune components orphaned by the deletion, by reachability~~ — 46 orphaned
- [x] ~~Sweep the components already unreachable before any deletion~~ — 52, not 58
- [x] ~~Regenerate `docs-navigation.json`~~ — 11 tags emptied
- [x] ~~Re-baseline Spectral~~ — 193 to 123 findings at the time; `oas3-unused-component` 26 to 0
- [x] ~~Record every removal in `_project/base-delta.yaml` with a reason~~ — 61 operations, 98 components

Notes worth carrying:
- Drops are declarative in **`_project/drops.yaml`**, applied by `build.py`, so
  `openapi.yaml` stays reproducible. Selection is by tag, not by path: that is
  how the decision was made, and it survives a path rename.
- `tags-map.yaml` kept all 52 entries through this task. The 11 dropped tags had
  to still resolve, because the drop runs *after* the rename so `drops.yaml` can
  name tags the way a reader of `drop-list.md` saw them. They went in task 7.
- **The component forecast was 6 low.** It followed `$ref`s only and so pruned
  the 6 `securitySchemes`, which are referenced *by name* from `security`
  blocks. Five of the six went in task 3.
- `drop-list.md` is regenerated and shows only what still ships. It carries a
  header saying decisions do not live there.

### 2. ~~One base URL that drives everything~~ — done 2026-09-15
- [x] ~~Delete all path-level and operation-level `servers` overrides~~ — 97 and 2, not the 130 estimated
- [x] ~~Data plane → `https://aigw.portkey.ai/v1`, prefix unchanged~~ — now the root server
- [x] ~~Control plane → `https://mp.us.prod.airs-gw.portkey.ai/api/v1`~~ — confirmed 2026-09-15
- [x] ~~The planes do **not** share a prefix: gateway `/v1`, control plane `/api/v1`.~~ Paths are declared bare (`/api-keys`), so the prefix lives entirely in the server URL — no path rewriting needed
- [x] ~~Remove the three placeholder strings that are not URLs~~
- [x] ~~Extend `check.py`~~ — four guards, each confirmed to fire
- [x] ~~Add `servers` to `normalise:` in `base-delta.yaml`~~

**The one place to change a base URL is `_project/servers.yaml`.** Edit a host,
rebuild, and every block follows.

Two deliberate departures from what this list originally said:

- **Not a single root block.** Two root entries, one per plane, would have
  offered both hosts on every operation — a reader could pick the control-plane
  URL for a chat completion and it would look right. Instead the gateway is the
  root server (so the gateway paths carry no override at all) and the
  control-plane paths get a generated override. More blocks in the artifact than
  one, but each operation shows exactly one correct host, and all of them come
  from one source. The duplication is OpenAPI's — a path cannot refer back to a
  server declared at the root.
- **Literal URLs, not server variables.** Variables were built first — they are
  the mechanism OpenAPI provides, and they would have let a self-hosted reader
  substitute their own host. **Mintlify cannot resolve them.** With a templated
  `url` it renders *"A valid request URL is required to generate request
  examples"* and emits no cURL sample at all, on every operation. Found in the
  task 5 experiment and reverted.

New file: **`_project/planes.yaml`**, which plane each path is on. This had to be
written down *before* the overrides were deleted — they were the only record for
95 of them, and `classification.yaml` names just 23. A path absent from it fails
the build rather than defaulting to the gateway.

#### 2a. ~~Self-hosted gateway URL~~ — done 2026-09-15

The variables decision above was read as "self-hosting cannot be offered". It
was narrower than that: *variables* do not work, but **a second literal entry in
`servers[]` does**, and it is the better answer anyway.

- [x] ~~Second root entry, `https://self-hosted-gateway-url.example.com/v1`~~
- [x] ~~`servers.yaml` restructured: each plane is now an ordered list, not one entry~~
- [x] ~~`check.py` compares whole lists, root included; four negative tests fire~~
- [x] ~~`servers` exempted from the no-prose walk, because `check_servers` now owns it~~

Verified against `mint 4.2.893` with the real specification, not a mock:

| | |
|---|---|
| Gateway operation | `<select aria-label="Select base URL">` with both hosts |
| Default | Managed — Mintlify builds the sample from the **first** entry |
| Control-plane operation | No dropdown; the self-hosted entry does **not** leak |
| Samples | Generate normally. No *"A valid request URL"* error |

The path-level override *replaces* the root list rather than extending it, which
is the finding that makes this safe — it is why a second root entry does not
risk offering a chat completion against the control-plane host, which is the
exact objection that produced the "not a single root block" decision above.

**The placeholder is under `example.com` on purpose.** The proposed spelling,
`self-hosted-gateway-url.com`, is an ordinary registrable domain and was
unregistered when checked. Publishing it in a document that also says
`Authorization: Bearer <token>` would hand whoever registers it live credentials
from every reader who copies the sample and forgets to change the host. RFC 2606
reserves `example.com` and IANA will never delegate it, so it fails closed.

No self-hosted **control plane** entry, and **confirmed with engineering on
2026-09-15 that there is none** — a self-hosted data plane talks to the managed
control plane. The commented-out placeholder in `servers.yaml` was removed; the
asymmetry is now documented as the product rather than as an open question.

### 3. ~~Authorization header only~~ — done 2026-09-15
- [x] ~~Drop the five alternative `security` combinations~~ — 85 operation-level overrides removed
- [x] ~~Drop the now-unused security schemes~~ — 6 schemes to 1
- [x] ~~Single `Authorization` bearer scheme, and show only that~~ — `type: http, scheme: bearer`
- [x] ~~Amend the README's "never renamed" rule~~ — both exemptions now written down
- [x] ~~Record the change in `base-delta.yaml`~~ — normalised, same reasoning as `servers`
- [x] ~~New `check_security` in `check.py`~~ — three negative tests all fire

Two things to know:

- **The `x-portkey-*` parameters stayed.** All seven carry tracing, span,
  metadata and cache controls — not authentication. The dropped schemes declared
  their headers inline in `securitySchemes`, so there were no auth parameters to
  remove. Dropping the seven would have deleted working functionality that was
  not part of the ask.
- **One operation is documented as needing no credentials:**
  `GET /model-configs/pricing/{provider}/{model}`, inherited `security: []`.
  Preserved rather than quietly reversed — making it require auth is as much an
  unverified claim as leaving it public. `check.py` prints it on every run.
  Confirming it with engineering is in **Residue**, below.

### 4 and 5 — moved out of Phase 1

Request-body `required` and the cURL code samples. Both are in the **Phase 3**
section below, with their findings intact — they were moved to Phase 2 and
renumbered with it when the admin plane took that slot. The numbering gap here
is left as-is because these numbers are referred to from `PLAN.md` and from
commit messages.

### 6. ~~Version and provenance~~ — done 2026-09-15
- [x] ~~`info.version` → `3.0.0`~~ — pinned in `build.py`, no longer inherited from the base

### 7. ~~Cut the cord from the base~~ — done 2026-09-15 (Q-C)
- [x] ~~Keep `check_shape.py` working through tasks 1–6~~ — final run: every operation and component identical, 0 reshaped
- [x] ~~Delete `.source/`, `scripts/check_shape.py`, `scripts/fetch-base.sh`, `_project/base-delta.yaml`~~
- [x] ~~Drop the "Fidelity to the base" CI job~~ — replaced by `build.py --check`
- [x] ~~README: Portkey becomes a historical note~~

**`build.py` was inverted, not deleted.** It generated `openapi.yaml` *from* the
base; with the base gone it would have been a script that cannot run, which four
others import from. It now reads `openapi.yaml`, reapplies what lives in
`_project/` and `tags-map.yaml`, and writes it back. Idempotent: the rebuild
produced a byte-identical document, so the whole rewrite diffs as three lines of
header comment.

Five one-shot steps became checks, each negative-tested and confirmed to fire:
the prose strip (`check.py`), the tag rename and the drops (`build.py`), the
prose inventory (frozen), and the overlay (add-only, so a rebuild cannot delete
grounded prose). Full reasoning in `PLAN.md`, "Phase 1 close-out".

Two things found while doing it:
- **`gen_drop_list.py` had quietly broken.** It classified paths from the
  `SELF_HOSTED_*_URL` placeholders task 2 deleted, so it had gone from 23
  unclassified paths to 95 without failing. Repointed at `planes.yaml`, which is
  what the build reads, so the inventory cannot drift from the document.
- **`tags-map.yaml` lost 13 entries** — the 11 dropped groups, plus `Analytics`
  and `Prompt Collections`, which no operation ever used.

### 8. ~~Catch-up~~ — done 2026-09-15
- [x] ~~README: layout, counts, naming, known gaps~~ — counts were stale throughout
- [x] ~~`build-report.txt` regenerates~~ — now derived from `openapi.yaml`, reporting what wants engineering rather than what the build removed
- [x] ~~`PROSE-INVENTORY.csv`~~ — **frozen, not regenerated.** It could only ever be derived by diffing the base. Recorded as such in the README
- [x] ~~Final full run of all checks~~ — `build --check`, `check.py`, `lint.py` all green

Five known gaps added to the README that were not written down anywhere a reader
would find them: no code samples, the five unfilled `required` bodies, the
unauthenticated pricing endpoint, the 91 inherited plane classifications, and
the absent self-hosted control plane.

---

## Engineering drop list — 2026-09-15

Engineering sent a list of capabilities dropped from their current API, to
verify against ours. Described as the first of several updates, so the drop set
should not be treated as closed.

| Engineering named | Status here |
|---|---|
| Prompts | Already dropped |
| Audit Logs | Already dropped |
| Users | Already dropped |
| User Invites | Already dropped |
| Workspace Members | Already dropped, as `Workspaces > Members` — the base's tag name for `/admin/workspaces/{id}/users*` |
| **Workspaces** | **Was still shipping. Dropped now** — 5 `/admin/workspaces*` operations |
| **SCIM Workspace Mappings** | **Was still shipping.** No such tag in the base: `/scim/workspaces*` carries the `Workspaces` tag, so the one drop removed both — 3 operations |

Removed **4 paths, 8 operations, 5 components**, in nine overlay actions.

Two things this left open, both flagged rather than assumed, and **both
answered on 2026-09-15**:

- **Seven capabilities we drop that engineering did not name** — Collections,
  Deployments, Labels, Log Exports, Prompt Partials, Virtual Keys and
  `Workspaces > Members`. Our list is a superset. The last is covered by their
  "Workspace Members" and `Prompt Partials` is plausibly inside their "Prompts",
  but the other five are ours alone. Left dropped; nothing here says to restore
  them, and restoring is the reversible direction.
- **Four operations that mention workspaces but are not the Workspaces
  capability** — `Integrations > Workspaces` (2) and `MCP Integrations >
  Workspaces` (2). Separate tags, and they attach workspaces to an integration
  rather than manage them.
  → **They stay.** Confirmed. Engineering also named `Agent Integrations >
  Workspaces` as staying; there is no such tag in this specification, and
  nothing tagged "Agent" at all. Either it is a capability their API has that
  the base did not, or it is `MCP Integrations > Workspaces` under another
  name. Resolving it is in **Residue**, below.

`build.py` grew `--apply-drops` for this, because it will happen again. See the
README section on `_project/drops.yaml`.

### `organisation_id` as a parameter — dropped 2026-09-15

Engineering: not needed as a parameter anywhere. It was a query parameter in
exactly two places, `GET /guardrails` and `GET /mcp-integrations`, both inline
rather than a shared `components/parameters` entry.

`drops.yaml` grew a third key, `parameters:`, for this. It matches on parameter
`name` anywhere in the document rather than listing the two sites, because the
objection is to the parameter itself — a site list would let it reappear on a
new operation and pass. Same two-invocation shape as the rest of the file: the
build checks, `--apply-drops` removes.

**Scoped to parameters, as asked.** `organisation_id` is still a property on 15
component schemas, 3 of which have it in `required`. That is a different
question — dropping a response field breaks readers, dropping a request
parameter does not — and it has not been asked. It is in **Residue**, below.

One unrelated tidy-up rode along: `POST /fine_tuning/jobs` carried
`parameters: []`, which says nothing, and the same code path that empties a
parameter list now removes it.

---

## Phase 1.5 — what docs asked for — **complete, 2026-09-15**

Five asks from docs (`_project/docs-note.md`). All five done. The note counted
181 operations and 53 without an `operationId`; both numbers predate the
engineering drop list, and the real figures are **173** and **45**.

### 1. ~~`x-mint.href` on every operation~~ — done
- [x] ~~173 hrefs, one per operation, `/aigw/api-reference/{tag-path}/{operation-slug}`~~
- [x] ~~Slugs for the 45 with no `operationId`~~ — from method and path, `{id}` → `by-id`
- [x] ~~**No `operationId` back-filled from a slug**~~ — the two stay separate
- [x] ~~Recorded in `_project/hrefs.yaml`, stamped by `build.py`~~
- [x] ~~CI check: presence, uniqueness, tag consistency, agreement with the record~~ (ask 6)

This unblocks the 122-link repoint, and it needed no KB access — a URL slug is
structural and asserts nothing about behaviour, so the grounding gate does not
apply. Docs were right about that.

**The derivation is not the source of truth; `_project/hrefs.yaml` is.** A tag
rename changes the derived href of every operation under it, silently, and these
are public URLs about to be written into 122 link sites. So the build re-derives
each one and **fails** on a difference, with two ways past it that mean
different things: `--apply-hrefs` adopts the new URLs (a docs migration — tell
them), or a `pinned:` entry holds the old URL through the rename.

That mechanism is also the answer to ask 4. A tag rename cannot ship quietly
because it stops the build, which is a better guarantee than a note in a README.

One thing found by testing it: a pinned href is *deliberately* inconsistent with
its tag, so the tag-consistency check had to exempt pinned keys or pinning could
never be used.

### 2. ~~Own the prose, and publish the resolved artifact~~ — done
- [x] ~~`openapi.yaml` is now the published document, prose included~~
- [x] ~~`build.py` strips prose and reapplies the overlay on every run~~
- [x] ~~`check_no_prose_in_spec` re-scoped, not deleted~~ — see below
- [x] ~~Spectral's `airs-no-prose-in-spec` replaced by `airs-prose-is-grounded`~~
- [x] ~~`docs-navigation.json`: `overlays` key removed, source URL pinned to `refs/heads/main`~~

**Decided by Vrushank: flatten, rather than publish a second file.** The URL
docs already read is the one that has to serve resolved pages.

The grounding gate survives intact, and the invariant got *stronger* rather than
weaker. It was "there is no prose in `openapi.yaml`". It is now "the prose in
`openapi.yaml` is exactly what the overlay produces" — strip it, reapply the
overlay, and the result has to be the document again. Prose typed directly into
`openapi.yaml` fails the check and does not survive the next build. The overlay
is still the only place prose is authored and still the only file the gate
reviews; what changed is that reviewing it is now equivalent to reviewing what
ships.

**Docs were right that this was about to break, and it was already broken.**
`docs-navigation.json` carried `overlays: ["overlays/docs-prose.yaml"]` — a path
in *this* repository, resolved against the *docs* repository, where no such file
exists. The overlay was never being applied. It cost nothing while every
description was empty and would have cost everything the day one was written.

Two things found while doing it:
- **The first version of the prose strip deleted `description` keys.** A
  Response Object *requires* `description`, so it produced a document that did
  not validate. Prose strings are now emptied in place rather than removed —
  which also keeps keys where their author put them, so a rebuild reorders
  nothing and the diff shows the prose that changed instead of the whole file.
- **`emit_change_event.py` would have reported an href move as
  `structure_changed`** and told the KB to re-review claims about behaviour that
  had not moved. `x-mint` is now stripped before the shape comparison.

### 3. ~~Drop `x-server-groups`~~ — done
- [x] ~~Removed. Nothing consumes it~~ — grepped; the only other mention was `reorder()`
- [x] ~~`DROP_ROOT_KEYS` in `build.py`, and `check.py` fails if it returns~~

Three stale `api.portkey.ai` URLs and two unsubstituted `SELF_HOSTED_*`
placeholders, in a non-standard field. The docs team had already moved every
base URL in their corpus off `api.portkey.ai`; this was the last copy anywhere, and it
was public. Popped on every build rather than deleted once, so a re-import
cannot bring it back.

### 4. ~~Tag renames as coordinated changes~~ — done
Covered by the href machinery above rather than by a promise: a rename changes
the derived hrefs and stops the build. Written up in the README under *How the
docs consume it*, alongside their `check_nav_matches_remote.py`.

### 6. ~~CI check for href presence, uniqueness and tag consistency~~ — done
In `check.py`, plus `airs-mint-href-present` in Spectral so a lint run on its own
still catches a missing one. Every new gate was negative-tested and confirmed to
fire: hand-written prose, a returning `x-server-groups`, a missing href, two
operations claiming one URL, an href under the wrong tag, an href that disagrees
with the record, a tag rename, a stale record, ungrounded prose.

**What none of this proves is that the pages exist.** Docs are right that
verification needs a real Mintlify preview and that PR #1076's check came back
SKIPPED. Everything short of that is now checked; the page render is not, and a
green build should not be read as evidence that it is.

---

## Phase 2 — the admin plane — **complete, 2026-09-15**

The control plane became two, and both moved off Portkey. Everything here was
decided by Vrushank on 2026-09-15; the reasoning is in `PLAN.md`, "Addendum —
Phase 2".

| | | |
|---|---|---|
| gateway | `https://aigw.portkey.ai/v1` | unchanged |
| control-plane | `https://api.apps.paloaltonetworks.com/ai_gw/v2` | was `mp.us.prod.airs-gw.portkey.ai/api/v1` |
| admin | `https://api.apps.paloaltonetworks.com/ai_gw/admin/v2` | new |
| admin-in-path | `https://api.apps.paloaltonetworks.com/ai_gw` | new; the same admin plane, prefix in the path key |

### 1. ~~Two management planes instead of one~~ — done
- [x] ~~`_project/servers.yaml` gains `admin` and `admin-in-path`; `control-plane` repointed~~
- [x] ~~`_project/planes.yaml` gains an `admin` section — 14 paths~~
- [x] ~~`build.py` writes a block per plane instead of per control-plane path~~ — `apply_servers` no longer knows the plane names
- [x] ~~`check.py` compares each block against the plane that path is on~~
- [x] ~~Both files are cross-checked~~ — a plane in one and not the other fails the build

**The host and the version both moved and no path needed touching.** That is
the return on Phase 1 task 2: one edit in `servers.yaml`, rebuild, 70 blocks
follow. The data plane stays on `aigw.portkey.ai`, so the document now publishes
two vendors' hostnames — a fact about the deployment, not an oversight.

### 2. ~~Which capabilities are administered~~ — done
- [x] ~~Integrations (+ Models, + Workspaces), MCP Integrations (+ Capabilities, Metadata, Workspaces), Secret References~~ — 11 paths
- [x] ~~Deployments~~ — 3 paths, recovered; see task 4
- [x] ~~Org Guardrails~~ — 4 paths, new; see task 3
- [x] ~~MCP **Servers** stays on `/ai_gw/v2`~~ — the ask named MCP Integrations, and they are different tags

**A new check: a tag sits on one plane.** The split was decided by capability
and `planes.yaml` can only record paths, so nothing in that file knows
`/integrations/{slug}/models` belongs with `/integrations`. Tags carry the
capability, so `check_planes` compares those. `Models` is the one legitimate
exception — listing the models available to a caller is a gateway concern,
administering one is not — and it is declared in `planes.yaml` under
`tags-spanning-planes` with the reasoning. An allowance that stops being used is
also a failure, so the licence cannot outlive the case for it.

### 3. ~~Org Guardrails — the same operations on the admin host~~ — done
- [x] ~~4 paths, 8 operations, identical payloads~~ — copied from `/guardrails*`
- [x] ~~Its own tag, in the Administration group~~
- [x] ~~Its own `operationId`s~~ — `createOrgGuardrail` and so on
- [x] ~~Its own docs URLs~~ — `/aigw/api-reference/org-guardrails/…`, 8 new records in `hrefs.yaml`

**OpenAPI cannot key one document by two paths spelled the same**, and the API
serves this surface at `/ai_gw/v2/guardrails` *and* `/ai_gw/admin/v2/guardrails`.
So for these four, and only these four, the server stops at `/ai_gw` and the
`/admin/v2` prefix moves into the path key. The rendered URL is identical either
way; what changes is which file the prefix is written in. Keeping it in
`servers.yaml` for the rest of the admin plane is what stopped 14 existing paths,
their `operationId`s and their published docs URLs from all moving to accommodate
one collision. The three options weighed are in `PLAN.md`.

A separate tag rather than eight more entries under `Guardrails`: two pages that
read identically apart from the host in the sample is how a reader calls the
wrong one. It is also what lets `check_planes` hold the two surfaces apart.

### 4. ~~Deployments, un-dropped~~ — done
- [x] ~~Recovered from `d9d380b`, the revision before the Phase 1 drop~~ — 3 paths, 6 operations, 10 schemas
- [x] ~~Removed from `drops.yaml`, with the reason and the revision~~
- [x] ~~`organisation_id` stripped on the way in~~ — 2 parameters; it is still dropped everywhere else
- [x] ~~Tag restored to `tags-map.yaml`, in the Administration group~~

**What came back is the inherited Portkey shape and nothing has checked it
against the API now serving `/ai_gw/admin/v2/deployments`.** It carried
`api.portkey.ai` code samples and a `Portkey-Key` security override, both of
which the build strips — but the request and response schemas are unexamined,
and they are the part that matters. This is the first thing to confirm with
engineering.

### 5. ~~Keep the derived files honest~~ — done
- [x] ~~`gen_drop_list.py` reads all four planes~~ — it asked for two keys by name and would have silently called the 18 admin paths unclassified
- [x] ~~`_project/classification.yaml` marked historical~~ — three of its entries are now finer-grained in `planes.yaml`; left as written, because its value is the reasoning at the time
- [x] ~~`docs-navigation.json`, `drop-list.md`, `build-report.txt` regenerated~~

Seven negative tests, each confirmed to fire: a plane named in `planes.yaml` and
not `servers.yaml`; a path in two planes; an admin path classified control-plane
(caught as a tag spanning planes); a hand-edited server block on a control-plane
path; an admin path with its block deleted; a gateway path given one; and a
`tags-spanning-planes` entry for a tag that no longer spans.

### Still unverified

- **The Deployments schemas.** Inherited, unexamined, on an admin API nobody
  here has called. Ranked ahead of everything in Phase 3.
- **That the new hosts answer.** Same as every other URL in this document:
  nothing in this repository has made a request to any of them.
- **The 14 new docs pages.** Same caveat as Phase 1.5 — an href is a claim that
  Mintlify renders a page there, and that needs a preview deployment.

---

## Phase 3 — open

*Was Phase 2. Renumbered 2026-09-15 when the admin plane took the slot; the
contents and their findings are unchanged.*

- [ ] **Confirm the recovered Deployments shape with engineering** — carried in from Phase 2
- [ ] **Agent Integrations and Plugins** — named in the admin ask, absent from this document; they need an endpoint list before they can be classified
- [ ] `operationId` on the **45** operations that lack one — first, because SDK generation depends on it and nothing else does
- [ ] cURL `x-codeSamples` for all **187** operations (task 5)
- [ ] `required` on the five request bodies (task 4) — a contract question for engineering
- [ ] Descriptions, once KB access lands — the grounding gate is already built and empty by design
- [ ] Code samples in languages beyond cURL
- [ ] Decide the JSON Schema constraint question: `default`, `maximum`, `minLength` are inherited unverified
- [ ] Schemathesis against a credentialled non-prod endpoint, once one exists
- [ ] SDK generation (Stainless / Speakeasy), which needs `operationId` first

### Request bodies that can generate a minimal sample

*Was Phase 1 task 4.*
- [x] ~~Re-count after the drops~~ — **5, not 13.** The other 8 were inside dropped groups
- [ ] Fill in `required` — **not done, deliberately. See below.**

`required` is a claim about the API contract, and there is nothing in this
repository that establishes it. Getting it wrong is not a cosmetic error: a
reader omits a field the API rejects, or sends one it does not want. This is the
same standard the grounding gate applies to prose — `required` is structural so
the gate does not formally cover it, but "inventing them is not the same as
recovering them" applies just as well.

The five, with what a guess would look like:

| | Properties | A guess would say |
|---|---|---|
| `POST /configs` | name, config, workspace_id | `name`, `config` |
| `POST /admin/workspaces` | name, description, defaults, users, usage_limits, rate_limits | `name` |
| `PUT /configs/{slug}` | name, config, status | possibly none — partial update |
| `PUT /providers/{slug}` | name, note, usage_limits, rate_limits, expires_at, reset_usage | possibly none — partial update |
| `PUT /admin/workspaces/{workspaceId}` | name, description, defaults, usage_limits, rate_limits | possibly none — partial update |

For the three `PUT`s, declaring nothing required may well be correct already:
a partial update where every field is optional is a normal design. So this may
be two fields to confirm, not five bodies to fill in.

**Moved out of Phase 1, 2026-09-15** — to what is now Phase 3. This task only existed to make a minimal
generated sample possible, and the task 5 experiment showed Mintlify ignores
`required` when generating one — so it cannot deliver what it was for, and it
follows the code samples rather than standing ahead of them. It is still worth
doing on its own merits, as a contract question: **engineering confirming the
five**, or a decision to ship them as they are.

### cURL code samples

*Was Phase 1 task 5. The experiment is done; the authoring is not.*
- [x] ~~Run the Mintlify experiment~~ — local `mint 4.2.893`, real spec, 2026-09-15
- [x] ~~Found and fixed a live bug~~ — see below
- [x] ~~Answer: **it dumps all 24 properties and ignores `required`**~~
- [x] ~~State the gap in the README so it does not read as an omission~~ — done, "Known gaps"
- [ ] Hand-write `x-codeSamples` for all **187** operations
- [ ] cURL only; a single entry suppresses the other language tabs
- [ ] Samples live in `overlays/docs-prose.yaml` with `x-airs-provenance`

**Decided 2026-09-15: every operation, not a curated set.** A reader landing on
a long-tail endpoint gets the 24-property dump, and "the endpoints that matter
read well" is a judgement that ages badly. For the record, the three options
weighed were: all operations (chosen); ship Mintlify's generated sample, which
is free but is the dump; or a curated set, which leaves the long tail verbose.

**The bug.** 106 operations still carried the base's `x-code-samples`.
`DROP_ROOT_KEYS` only popped the root key, so the per-operation ones survived
every build. They hardcode `api.portkey.ai`, `x-portkey-api-key` and
`x-portkey-virtual-key` — and Mintlify renders a supplied sample *instead of*
the generated one, so they silently overrode both the new base URL and the new
auth. A reader would have been told to call the old host with headers this API
does not read. Code samples are now in `PROSE_KEYS` (both spellings), stripped
at every level, and `check.py` fails if one reappears.

**Answer to the experiment.** `CreateChatCompletionRequest` declares
`required: [model, messages]`. Mintlify emitted all 24 properties —
`temperature`, `top_p`, `logit_bias`, `seed`, `functions`, everything. It does
not use `required` to trim the request example. So there is no way to get the
minimal sample by annotating the schema, and **task 4 would not have helped
here either**.

Confirmed working: auth renders as `Authorization: Bearer <token>`.

---

## Answered — 2026-09-15

| | Question | Answer |
|---|---|---|
| Q-A | `Prompts` spans both planes; only the control-plane side was marked | **Drop the two gateway paths too.** The whole Prompts surface goes together |
| Q-B | Control-plane base URL, since the control-plane paths survive | **A different host:** `https://mp.us.prod.airs-gw.portkey.ai/api/v1`. Confirmed 2026-09-15 |
| Q-C | When to retire the base linkage | **End of Phase 1**, so the guardrail covers the drops |
| Q-D | Is 31 paths the intended drop, not 97? | **Yes.** The control-plane paths stay by design |

---

## Residue

Carried out of closed phases. Each is small, unowned by any current task, and
safe to leave — listed so it is not mistaken for something nobody noticed.

- [ ] **Get the drops graded by `breaking-changes.yml`.** Phase 1 task 1 assumed
  this would happen on its own. It cannot: the workflow triggers on
  `pull_request`, not `push`, and every Phase 1 commit went straight to `main`,
  so there was never a PR for it to grade. The only run it has ever had is the
  deliberate `ci-verify-breaking-changes` PR that proved the workflow works. To
  get the audit trail, run it by `workflow_dispatch` against the pre-drop
  revision, or land the next drop batch through a PR. Doing neither is also
  defensible — the drops are recorded in `drops.yaml` and in commit history —
  but then task 1's intended audit trail does not exist, and that should be a
  decision rather than an oversight.
- [ ] **Confirm the unauthenticated pricing endpoint** with engineering.
  `GET /model-configs/pricing/{provider}/{model}` inherits `security: []`.
  Preserved rather than reversed, because requiring auth is as much an
  unverified claim as leaving it public. `check.py` prints it on every run.
- [ ] **Resolve `Agent Integrations > Workspaces`.** Engineering named it as
  staying; no such tag exists here, and nothing is tagged "Agent" at all. Either
  their API has a capability the base did not, or it is `MCP Integrations >
  Workspaces` under another name. Nothing to do either way — worth settling
  before the next drop batch.
- [ ] **`organisation_id` as a schema property.** Still on 15 component schemas,
  3 with it in `required`. Out of scope for the parameter drop and not asked
  for; dropping a response field breaks readers in a way dropping a request
  parameter does not.
