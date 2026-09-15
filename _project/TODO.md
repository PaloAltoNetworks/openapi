# TODO

Phase-based task list. Rationale and findings live in `PLAN.md`; this is the
checklist. Strike through as they land.

Every task ends green — `build.py --check`, `check.py` and `lint.py` passing —
so work can stop at any line. Through tasks 1–6 that list also included
`check_shape.py`, the comparison against the inherited base; task 7 retired it.

All four questions answered, 2026-09-15. Control-plane base URL confirmed the
same day.

**Phase 1 is complete**, with tasks 4 and 5 moved to Phase 2 by decision rather
than left undone. Nothing is blocked.

---

## Phase 1 — the sweeping changes

### 1. ~~Drop the marked control-plane operations~~ — done 2026-09-15
- [x] ~~Delete the 11 tag groups marked `[DROPPED]`: Audit Logs, Collections, Deployments, Labels, Log Exports, Prompt Partials, Prompts, User Invites, Users, Virtual Keys, Workspaces > Members~~
- [x] ~~Also drop the two gateway `Prompts` paths — `/prompts/{promptId}/completions` and `/prompts/{promptId}/render` — so the whole Prompts surface goes together (Q-A)~~
- [x] ~~→ **33 paths, 61 operations.** Leaves **118 paths, 181 operations**~~ — exactly as forecast
- [x] ~~Prune components orphaned by the deletion, by reachability~~ — 46 orphaned
- [x] ~~Sweep the components already unreachable before any deletion~~ — 52, not 58
- [x] ~~Regenerate `docs-navigation.json` — **52 tags to 41**, 11 emptied~~
- [x] ~~Re-baseline Spectral and record the new counts~~ — 193 to 123 findings; `oas3-unused-component` 26 to 0
- [x] ~~Record every removal in `_project/base-delta.yaml` with a reason~~ — 61 operations, 98 components
- [ ] Let `breaking-changes.yml` fire and keep the comment as the audit trail — fires on push

Notes worth carrying:
- Drops are declarative in **`_project/drops.yaml`**, applied by `build.py`, so
  `openapi.yaml` stays reproducible from the base. Selection is by tag, not by
  path: that is how the decision was made, and it survives a path rename.
- `tags-map.yaml` keeps all 52 entries. The 11 dropped tags must still resolve,
  because the drop runs *after* the rename so `drops.yaml` can name tags the way
  a reader of `drop-list.md` saw them. They go when the cord is cut (task 7).
- **Components landed at 480, not the forecast 474.** The forecast followed
  `$ref`s only and so pruned the 6 `securitySchemes`, which are referenced *by
  name* from `security` blocks. Five of the six go in task 3 → 475.
- `drop-list.md` is regenerated and now shows only what still ships (66 control
  plane, 52 gateway). It carries a header saying decisions do not live there.

### 2. ~~One base URL that drives everything~~ — done 2026-09-15
- [x] ~~Delete all path-level and operation-level `servers` overrides~~ — 97 and 2, not the 130 estimated
- [x] ~~Data plane → `https://aigw.portkey.ai/v1`, prefix unchanged~~ — now the root server
- [x] ~~Control plane → `https://mp.us.prod.airs-gw.portkey.ai/api/v1`~~ — confirmed 2026-09-15
- [x] ~~The planes do **not** share a prefix: gateway `/v1`, control plane `/api/v1`.~~ Paths are declared bare (`/api-keys`), so the prefix lives entirely in the server URL — no path rewriting needed
- [x] ~~Remove the three placeholder strings that are not URLs~~
- [x] ~~Extend `check.py`~~ — four guards, each confirmed to fire
- [x] ~~Add `servers` to `normalise:` in `base-delta.yaml`~~

**The one place to change a base URL is now `_project/servers.yaml`.** Edit a
host, rebuild, and all 67 blocks follow.

Two deliberate departures from what this list originally said:

- **Not a single root block.** Two root entries, one per plane, would have
  offered both hosts on every operation — a reader could pick the control-plane
  URL for a chat completion and it would look right. Instead the gateway is the
  root server (so 52 gateway paths carry no override at all) and the 66
  control-plane paths get a generated override. 67 blocks in the artifact rather
  than 1, but each operation shows exactly one correct host, and all 67 come
  from one source. The duplication is OpenAPI's — a path cannot refer back to a
  server declared at the root.
- **Literal URLs, not server variables.** Variables were built first — they are
  the mechanism OpenAPI provides, and they would have let a self-hosted reader
  substitute their own host. **Mintlify cannot resolve them.** With a templated
  `url` it renders *"A valid request URL is required to generate request
  examples"* and emits no cURL sample at all, on every operation. Found in the
  task 5 experiment and reverted.

New file: **`_project/planes.yaml`**, which plane each of the 118 paths is on.
This had to be written down *before* the overrides were deleted — they were the
only record for 95 of them, and `classification.yaml` names just 23. A path
absent from it fails the build rather than defaulting to the gateway.

#### 2a. Self-hosted gateway URL — added 2026-09-15

The variables decision above was read as "self-hosting cannot be offered". It
was narrower than that: *variables* do not work, but **a second literal entry in
`servers[]` does**, and it is the better answer anyway.

- [x] Second root entry, `https://self-hosted-gateway-url.example.com/v1`
- [x] `servers.yaml` restructured: each plane is now an ordered list, not one entry
- [x] `check.py` compares whole lists, root included; four negative tests fire
- [x] `servers` exempted from the no-prose walk, because `check_servers` now owns it

Verified against `mint 4.2.893` with the real specification, not a mock:

| | |
|---|---|
| Gateway operation | `<select aria-label="Select base URL">` with both hosts |
| Default | Managed — Mintlify builds the sample from the **first** entry |
| Control-plane operation | No dropdown; the self-hosted entry does **not** leak |
| Samples | Generate normally. No *"A valid request URL"* error |

The path-level override *replaces* the root list rather than extending it, which
is the finding that makes this safe — it is why a second root entry no longer
risks offering a chat completion against the control-plane host, which is the
exact objection that produced the "not a single root block" decision above.

**The placeholder is under `example.com` on purpose.** The proposed spelling,
`self-hosted-gateway-url.com`, is an ordinary registrable domain and was
unregistered when checked. Publishing it in a document that also says
`Authorization: Bearer <token>` would hand whoever registers it live credentials
from every reader who copies the sample and forgets to change the host. RFC 2606
reserves `example.com` and IANA will never delegate it, so it fails closed.

No self-hosted **control plane** entry. A hybrid deployment — self-hosted data
plane, managed control plane — is normal, and nothing here establishes that a
self-hosted control plane exists or where it sits. Two lines in `servers.yaml`
if it does. **Worth confirming with engineering.**

### 3. ~~Authorization header only~~ — done 2026-09-15
- [x] ~~Drop the five alternative `security` combinations~~ — 85 operation-level overrides removed
- [x] ~~Drop the now-unused security schemes~~ — 6 schemes to 1
- [x] ~~Single `Authorization` bearer scheme, and show only that~~ — `type: http, scheme: bearer`
- [x] ~~Amend the README's "never renamed" rule~~ — both exemptions now written down
- [x] ~~Record the change in `base-delta.yaml`~~ — normalised, same reasoning as `servers`
- [x] New `check_security` in `check.py`; three negative tests all fire

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
  **Worth confirming with engineering.**

### 4 and 5 — moved to Phase 2

Request-body `required` and the cURL code samples. Both are now in the Phase 2
section below, with their findings intact. The numbering gap is left as-is
because these numbers are referred to from `PLAN.md` and from commit messages.

### 6. ~~Version and provenance~~ — done 2026-09-15
- [x] ~~`info.version` → `3.0.0`~~ — pinned in `build.py`, no longer inherited from the base

### 7. ~~Cut the cord from the base~~ — done 2026-09-15 (Q-C)
- [x] ~~Keep `check_shape.py` working through tasks 1–6~~ — final run: 181/181 operations and 474/474 components identical, 0 reshaped
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
the prose strip (`check.py`), the tag rename and the 61 drops (`build.py`), the
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
- [x] ~~README: layout, counts, naming, known gaps~~ — counts were stale throughout (151/242, 535 schemas, 52 tags, 4,075 prose fields, 193 findings)
- [x] ~~`build-report.txt` regenerates~~ — now derived from `openapi.yaml`, reporting what wants engineering rather than what the build removed
- [x] ~~`PROSE-INVENTORY.csv`~~ — **frozen, not regenerated.** It could only ever be derived by diffing the base. Recorded as such in the README
- [x] ~~Final full run of all checks~~ — `build --check`, `check.py`, `lint.py` all green

Five known gaps added to the README that were not written down anywhere a reader
would find them: no code samples, the five unfilled `required` bodies, the
unauthenticated pricing endpoint, the 95 inherited plane classifications, and
the absent self-hosted control plane.

---

## Phase 2 — deferred, agreed

- [ ] `operationId` on the **53** operations that lack one — first, because SDK generation depends on it and nothing else does
- [ ] cURL `x-codeSamples` for all 181 operations (task 5)
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

**Moved to Phase 2, 2026-09-15.** This task only existed to make a minimal
generated sample possible, and the task 5 experiment showed Mintlify ignores
`required` when generating one — so it cannot deliver what it was for, and it
follows the code samples rather than standing ahead of them. It is still worth
doing on its own merits, as a contract question: **engineering confirming the
five**, or a decision to ship them as they are.

### cURL code samples

*Was Phase 1 task 5. The experiment is done; the authoring is not.*
- [x] ~~Run the Mintlify experiment~~ — local `mint 4.2.893`, real spec, 2026-09-15
- [x] **Found and fixed a live bug** — see below
- [x] Answer: **it dumps all 24 properties and ignores `required`**
- [x] ~~State the gap in the README so it does not read as an omission~~ — done, "Known gaps"
- [ ] **Phase 2:** hand-write `x-codeSamples` for all 181 operations
- [ ] cURL only; single entry suppresses the other language tabs
- [ ] Samples live in `overlays/docs-prose.yaml` with `x-airs-provenance`

**Decided 2026-09-15: option A, all 181, in Phase 2.** Not the curated set —
a reader landing on a long-tail endpoint gets the 24-property dump, and "the
endpoints that matter read well" is a judgement that ages badly.

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

**The options:**

| | What it means | Cost |
|---|---|---|
| A | Hand-write `x-codeSamples` for all 181 operations | Exactly the ask; 181 samples to author and ground |
| B | Ship Mintlify's generated sample | Free; it is the 24-property dump you did not want |
| C | Hand-write a curated set, generated elsewhere | The endpoints that matter read well; the long tail is verbose but correct |

C looks right, but which operations are in the curated set is your call.

---

## Answered — 2026-09-15

| | Question | Answer |
|---|---|---|
| Q-A | `Prompts` spans both planes; only the control-plane side was marked | **Drop the two gateway paths too.** The whole Prompts surface goes together |
| Q-B | Control-plane base URL, since 66 control-plane paths survive | **A different host:** `https://mp.us.prod.airs-gw.portkey.ai/api/v1`. Confirmed 2026-09-15 |
| Q-C | When to retire the base linkage | **End of Phase 1**, so the guardrail covers the drops |
| Q-D | Is 31 paths the intended drop, not 97? | **Yes.** 66 control-plane paths stay by design |

## The shape of Phase 1

| | Base | After task 1 | Forecast was |
|---|---|---|---|
| Paths | 151 | **118** | 118 ✓ |
| Operations | 242 | **181** | 181 ✓ |
| Components | 578 | **475** | 474 — see note above |
| Tags | 52 | **41** | 41 ✓ |
| Spectral findings | 193 | **123** | — |

Components read 480 immediately after task 1 and 475 after task 3 dropped five
of the six security schemes. The forecast of 474 was one out for the reason
noted under task 1: schemes are referenced by name, not by `$ref`.

Servers ended at **3 hosts across 67 blocks** — managed gateway, self-hosted
gateway, control plane — all generated from `_project/servers.yaml`.
