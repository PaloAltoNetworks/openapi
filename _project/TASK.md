# TASK — bring the Prisma AIRS updates into the spec

Working notes. Not published, not part of the build. Delete or gitignore when
the work lands.

Status: **steps 0 and 1 done** (commit `aea10de`). Steps 2–7 blocked on Q1–Q4.
See the progress log at the bottom.

---

## What you asked for

1. **Operations stay the same.** The set of paths and methods is not being
   redesigned.
2. **Some control-plane operations get dropped.** You will supply the list.
3. **Code samples**: we have simplified, correct ones. cURL only for now.
   Preferably Mintlify renders a *minimal* sample itself — `model` on
   `/chat/completions`, not `temperature` — so we write no samples at all.
4. **Base URL changes**, and you want one place at the top to change it that
   drives everything below.

Read and understood. My comments follow, then open questions, then a proposed
order of work.

---

## What I found before commenting

Four things I checked, because each one changes how an item should be done.

### There is no single place to change the base URL today

This is the important one, and it is worse than it looks.

| Entries | URL |
|---|---|
| 132 | `https://api.portkey.ai/v1` |
| 81 | `SELF_HOSTED_CONTROL_PLANE_URL` |
| 46 | `SELF_HOSTED_GATEWAY_URL` |
| 4 | `https://SELF_HOSTED_CONTROL_PLANE_URL` |
| 1 | `https://api.portkey.ai` (no `/v1`) |

264 `servers[].url` entries in total: 1 at the root, **130 at path level**, 2 at
operation level. Editing `servers[0].url` at the top of the file changes the
base URL for **21 of 151 paths**. The other 130 override it locally and would
silently keep pointing at Portkey.

Three of those five values are not URLs at all — bare placeholder tokens the
base author never substituted. `https://SELF_HOSTED_CONTROL_PLANE_URL` is a
syntactically valid URL pointing at a hostname that does not exist, which is the
worst kind: it renders, it is clickable, and it fails at request time.

This is inherited defect, not something we introduced. But item 4 cannot be done
by editing a line — it needs the generator.

### The base spec already labels which operations are control plane

A useful accident. Those per-path server overrides partition the API:

| Paths | Signal | Meaning |
|---|---|---|
| 83 | `SELF_HOSTED_CONTROL_PLANE_URL` | control plane |
| 46 | `SELF_HOSTED_GATEWAY_URL` | data plane / gateway |
| 21 | inherits root | unclassified — `/guardrails*` and friends |
| 1 | bare `https://api.portkey.ai` | unclassified, malformed |

So there is a **starting inventory for item 2 already in the file**. I will
generate it as a checklist for you to strike through rather than making you
write 80 paths from memory.

Caveat, and I want to be plain about it: this is Portkey's classification,
inherited and unverified. It is a draft to react to, not a source of truth. 22
paths are unclassified and need a human call regardless.

### `/chat/completions` is exactly the case you described

`CreateChatCompletionRequest`: **24 properties, 2 required** — `model` and
`messages`. Your "say the model name, but no need to add temperature" maps
precisely onto *required-only*. That is encouraging: if Mintlify can be made to
render required-only, the rule is already in the schema and we write nothing.

Body shapes across all 242 operations:

| Count | Request body |
|---|---|
| 154 | none (GET/DELETE) |
| 55 | `$ref` to a component |
| 23 | inline properties |
| 5 | inline but empty |
| 5 | non-JSON or no schema |

Of the 23 inline bodies, **13 declare no `required` at all**. So required-only
is not a universal lever — for those 13 it would render an empty body. They need
`required` lists filled in, which is a real (and correct) engineering fix, or
they need hand-written samples.

### Auth is still Portkey-branded

Security schemes: `Portkey-Key`, `Virtual-Key`, `Provider-Auth`,
`Provider-Name`, `Config`, `Custom-Host`. Root security is `Portkey-Key`. The
header parameters are `x-portkey-*` throughout.

You did not raise this, and I am not treating it as in scope. Flagging it
because **a code sample shows the auth header**, so items 3 and 4 both collide
with it. If the AIRS header is not `x-portkey-api-key`, every sample we write
now is wrong, and we should settle auth before writing samples rather than
after. See open question Q4.

---

## Comments on each item

### (1) Operations stay the same — comment: let's make that checkable

Agreed, and I want to hold us to it. Right now I can prove our spec is
structurally identical to the base (strip prose from both, compare trees →
`True`). Once we start dropping operations that proof stops being a single
boolean.

Proposal: replace it with a check that says *for every operation that still
exists, its shape is byte-identical to the base*, plus an explicit allow-list of
removals. Then "we only dropped things, we never quietly reshaped anything"
stays a machine-checked claim instead of an intention. Cheap to build, and it is
the guardrail that makes items 2–4 safe to do quickly.

### (2) Dropping control-plane operations — comment: mostly about the blast radius

The deletion itself is trivial. What follows it is not:

- **Orphaned components.** Dropping 83 paths will strand a large number of
  schemas. `oas3-unused-component` is currently baselined at 26; it will jump.
  We should prune unreferenced components in the same change, not baseline the
  growth — otherwise the dead schemas still ship, still render in the docs, and
  still show up in MCP tool listings.
- **Tags.** Some of the 52 tags will empty out. `tags-map.yaml` and
  `docs-navigation.json` regenerate, and a navigation group may disappear
  entirely.
- **`breaking-changes.yml` will light up** with
  `api-path-removed-without-deprecation`, once per dropped path. That is
  correct. We should let it fire and record it, not suppress it — that comment
  is the audit trail for a deliberate product decision.
- **One-way door.** Re-adding a dropped operation later means recovering its
  schemas too. Worth being sure the list is final-ish before we cut.

Ordering: I would do this **first**, before samples and before the URL work.
Every downstream task is proportional to the number of operations, so shrinking
the surface first makes the rest cheaper. It also means we never write a code
sample for an operation we are about to delete.

### (3) Code samples — comment: two real problems, and one I need to test

**Problem A: a code sample is prose, and it is currently ungoverned.**

Not a pedantic point. A cURL sample asserts the base URL, the auth header name,
the content type, which fields are needed, and what a plausible value looks
like. That is four or five behavioural claims in eight lines, published
verbatim, and disproportionately the thing readers copy. Under our own rule it
belongs in `overlays/docs-prose.yaml` behind the grounding gate, not in
`openapi.yaml`.

Concretely: `x-codeSamples` goes in the overlay, with `x-airs-provenance`
alongside it and the `text_digest` covering the sample text. Then a sample that
drifts from its claim shows up in `scripts/drift.py` like any other prose. This
costs nothing to set up now and is unpleasant to retrofit.

Note also the spelling: the base used `x-code-samples` (which we dropped);
**Mintlify reads `x-codeSamples`**. Different key. Do not resurrect the old one.

**Problem B: "the samples are not wrong" is a claim I cannot check.**

I believe you. But I need to know where they come from so provenance can point
at something. If they are validated against a running AIRS endpoint, that is the
strongest grounding in this repo and I want to record it. If they are
hand-written, that is fine too — it just means `origin_kind: human` and a claim
to hang them on. See Q3.

**Problem C: whether Mintlify can do this unaided — I do not know, and I will
not guess.**

Your preferred outcome is the right one: schema drives the sample, we write
nothing, there is nothing to drift. The question is whether Mintlify's generated
request example honours `required` or dumps every property.

My recollection is that it renders the full property set, which would sink the
zero-samples plan — but my web access is blocked by org policy here, so I cannot
check the current docs, and Mintlify moves fast. **I am not willing to design
around a recollection.** This is a 30-minute experiment:

> Build a throwaway 2-operation spec — one with `required: [model, messages]`
> and 24 properties, one with no `required` — run `mintlify dev`, look at what
> renders. Repeat with `example` set on only the required properties.

Then we pick with evidence. The likely outcomes, ranked by how much I would like
them:

| | Approach | Cost |
|---|---|---|
| **A** | Mintlify honours `required` → do nothing | zero, self-maintaining |
| **B** | Set `example` only on the fields we want shown | small, stays in the schema, but examples are prose and need grounding |
| **C** | Hand-written `x-codeSamples` in the overlay | ~1 per operation forever, drifts, but total control |

A if we can get it, B as the realistic default, C only where B cannot express
it. And the 13 bodies with no `required` list need fixing under any of them.

**On cURL-only:** straightforward, and I would go further — say so explicitly
in the README, because "only cURL" reads as an omission unless it is stated as a
decision. `x-codeSamples` with a single entry suppresses Mintlify's other
language tabs; that is the mechanism if we end up at C.

### (4) One base URL that drives everything — comment: agreed, and it should be enforced

Given the 264 entries, "a place at the top of the file" cannot be inside
`openapi.yaml`. Three options:

**Option 1 — OpenAPI server variables.** `url: "{baseUrl}"` with a `variables`
block. Legal OpenAPI, one place, zero tooling. Rejected: the docs then render a
templated URL and the playground asks the reader to fill in a variable to make
a call. We would be solving our maintenance problem by moving it onto readers.

**Option 2 — config drives the build (recommended).** `_project/config.yaml`
holds the URL(s); `scripts/build.py` stamps every `servers` block; a new
assertion in `scripts/check.py` fails if any host string appears anywhere that
did not come from the config. You change one line, regenerate, and the spec
stays literal — no templates in the reader's face. The check is the part that
matters: it makes the invariant enforced rather than documented, so the next
person cannot hand-edit a path-level server back in.

**Option 3 — delete the per-path overrides entirely.** If AIRS gateway and
control plane are on the same host, all 130 path-level and 2 operation-level
overrides are inherited noise from Portkey's self-hosting story. Deleting them
leaves one root `servers` block, and item 4 becomes true by construction rather
than by tooling.

**I would do 3, with 2 as the backstop.** Option 3 is the real fix — the reason
there is no single place today is that someone added 130 local overrides, and no
amount of config-stamping makes that structure good. But it depends entirely on
whether AIRS has one host or two, which is Q1. If two, we keep two root servers
and still delete the per-path overrides; only if some operations genuinely need
a *third* host do the overrides earn their place.

Either way the three malformed placeholder URLs go.

---

## Open questions

Blocking:

- **Q1 — Base URL(s).** What is the AIRS base URL? Is there one host or two
  (gateway vs control plane)? Does the path prefix stay `/v1`? This decides
  between options 2 and 3 above, and it is the only thing blocking item 4.
- **Q2 — The drop list.** Resolved down to one question: all 151 paths are now
  classified (97 control plane, 54 gateway), so what is left is *how much of the
  control plane goes* — all 97, or a subset. Tick `_project/drop-list.md`.

Blocking item 3 specifically:

- **Q3 — Where do the simplified samples live**, and were they run against a
  real endpoint? A file, a doc, a PR — whatever form. Needed for grounding.
- **Q4 — Auth.** Do the AIRS headers differ from `x-portkey-*` / `Portkey-Key`?
  If yes, this is larger than the base URL change and should land before any
  sample is written, or we write them all twice. The README currently states
  these are never renamed; that rule would need an explicit exemption.

Not blocking, but decide before we ship:

- **Q5 — `info.version`.** Currently `2.0.0`, a placeholder I chose. What is the
  real one?
- **Q6 — When do we cut the cord from the base?** After dropping ~83
  operations, changing hosts and possibly changing auth, `.source/` stops being
  a meaningful reference. At some point "derived from Portkey-AI/openapi at
  `3fa53f2`" becomes a historical note rather than a live relationship, and the
  structural-equivalence check should be retired with it.

Still outstanding from before, unchanged:

- **KB access (Q2 in the original brief)** still blocks all descriptions. None
  of the work above depends on it — it is structural — so these can proceed in
  parallel. 0 descriptions written so far, by design.
- **84 operations have no `operationId`.** Dropping control-plane paths may
  reduce this; worth re-counting after item 2.

---

## Proposed order

Each step ends green — checks passing, spec valid — so we can stop anywhere.

| # | Step | Needs | Note |
|---|---|---|---|
| ~~0~~ | ~~Shape-equivalence check + removal allow-list~~ | — | **Done** |
| ~~1~~ | ~~Generate the drop-list checklist~~ | — | **Done** — `drop-list.md` |
| 2 | Drop the operations, prune orphaned components, regenerate tags and navigation, re-baseline Spectral | Q2 | Shrinks everything downstream |
| 3 | Base URL: delete per-path overrides, single config-driven root, add the check | Q1 | The `PLEASE` item |
| 4 | Auth rename, if any | Q4 | Before samples, not after |
| 5 | Mintlify rendering experiment → pick A / B / C | — | 30 min, decides step 6 |
| 6 | Code samples per the outcome; grounded in the overlay; cURL only | Q3, step 5 | |
| 7 | README and `build-report.txt` catch up | all | |

---

## Progress log

### Steps 0 and 1 — done, commit `aea10de`

**What landed**

| File | What it does |
|---|---|
| `scripts/check_shape.py` | Per-operation and per-component comparison against the base |
| `_project/base-delta.yaml` | The allow-list. Every accepted difference, with a reason |
| `_project/drop-list.md` | 151 paths as a checklist, with blast radius |
| `_project/classification.yaml` | Human plane decisions, overriding the inherited guess |
| `_project/gen_drop_list.py` | Regenerates the drop list |
| `scripts/fetch-base.sh` | Now pins to the recorded commit |
| `scripts/check.py` | Servers check now sees all 264 entries, not 1 |
| `.github/workflows/validate.yml` | New "Fidelity to the base" job |

Current state, all green:

```
operations  base  242   ours  242   identical  242   removed 0  added 0  reshaped 0
components  base  578   ours  578   identical  578   removed 0  added 0  reshaped 0
```

**Step 0 — the guardrail**

`scripts/check_shape.py` asserts: *every operation and component that still
exists is structurally identical to the base, and everything that differs is
listed in `base-delta.yaml` with a reason.* Removals are fine — they just have
to be written down. A removal nobody wrote down is indistinguishable from an
accident, which is what stops step 2 from quietly taking a schema somebody
still needed.

Three things worth knowing about it:

- **It compares components separately from operations, and that turns out to
  matter.** An operation that `$ref`s a schema looks untouched when the schema
  underneath it changes. Confirmed by test: editing
  `CreateChatCompletionRequest.required` is invisible at operation level and
  caught at component level. Operation-only comparison would have shipped it.
- **It catches stale allow-list entries.** An entry left behind after the thing
  came back keeps excusing a difference nobody re-checked. That is how this kind
  of guardrail rots, so it fails instead.
- **`normalise:` in `base-delta.yaml` is where intentional systematic deltas
  go** — currently prose, provenance, tags, null-defaults. Add `servers` when
  step 3 lands. Each entry is a commitment, not a convenience: it switches off
  detection for a whole class of change.

Confirmed to fire before being relied on, same standard as every other gate
here: unexplained removal (exit 1), unexplained addition, reshaped component,
stale allow-list entry, and absent base under `--require-base`.

**Two fixes found along the way**

*`fetch-base.sh` was cloning the base's HEAD, not our pinned commit.* The base
is Portkey's repository and moves on its own; the shape check would have
reported their changes as our drift and gone to noise within a week. Now pinned
to `3fa53f2` from `base-delta.yaml`, with `BASE_COMMIT=HEAD` to override.
Verified a refetch reproduces the byte-identical file.

*`check.py`'s servers check reported the root block only* — 1 of 264 entries. A
search and replace that missed the other 263 would have passed the check whose
only purpose is to catch exactly that. It now walks every block and flags values
that are not URLs:

```
  ok    servers -- 264 entries, 5 distinct
           132  https://api.portkey.ai/v1
            81  SELF_HOSTED_CONTROL_PLANE_URL   <- not a URL
            46  SELF_HOSTED_GATEWAY_URL   <- not a URL
             4  https://SELF_HOSTED_CONTROL_PLANE_URL
             1  https://api.portkey.ai
```

**Step 1 — the drop list**

`_project/drop-list.md`, 151 paths as tick-boxes grouped by classification then
by tag, each showing its methods and `operationId`s. Two findings:

*Blast radius is large but clean.*

| Group | Paths | Components reached | Reached **only** by this group |
|---|---|---|---|
| control plane | 97 | 245 | **243** |
| gateway | 54 | 277 | 275 |
| unclassified | 0 | — | — |

Dropping all 97 control-plane paths orphans **243 components** — 42% of the 578
in the file.

**Exactly two components are shared between the planes: `schemas/Error` and
`schemas/Model`.** That is the entire risk surface for the prune. Everything
else belongs to one side or the other, so step 2 can delete by reachability and
be confident it is not cutting into the gateway.

What survives if every control-plane path goes and nothing else changes:

| | Now | After |
|---|---|---|
| Paths | 151 | **54** |
| Components | 578 | **277** |

Worth sanity checking against your expectation before we cut. If 54 paths feels
too small for the AIRS surface, the drop list is wrong somewhere and now is the
time to find out.

Separately: **58 components are already unreachable from any path**, before we
drop anything. Spectral's `oas3-unused-component` baseline is 26 because it
counts differently (a schema referenced only by another dead schema still looks
used). Worth sweeping in step 2 while we are in there.

*The unclassified paths needed human calls, so there is now a place to record
them.* `_project/classification.yaml` overrides the inherited classification
with fnmatch patterns, and `drop-list.md` marks decided paths with **✓** — a
guess and a call should not look identical once both are on the page. A pattern
that matches nothing is a hard error, because the usual cause is a renamed path
and a rule that silently stops applying is worse than no rule. Confirmed to fire.

**All 151 paths are now classified — nothing is left to the inherited guess.**
23 decided by hand, 22 of which the inherited data had wrong or missing.

**Decided — Vrushank, 2026-09-15:**

| Pattern | Paths | Plane |
|---|---|---|
| `/guardrails*` | 4 | control plane |
| `/policies/*` | 6 | control plane |
| `/integrations/{slug}/models`, `/integrations/{slug}/workspaces` | 2 | control plane |
| `/model-configs/*` | 1 | control plane |
| `/models/{model}` | 1 | control plane |
| `/models` | 1 | gateway (confirming the inherited value) |
| `/vector_stores*` | 8 | gateway |

Two of my readings were wrong and are corrected above: I had guessed
`/model-configs/pricing/...` and `/models/{model}` were data plane. They are not.

**`/models` and `/models/{model}` sit on opposite sides of the split**, which is
a live trap: fnmatch's `*` crosses slashes, so a `/models*` rule under
control-plane silently swallows the gateway path too. `/models` is therefore
pinned explicitly even though the inherited data already had it right, and
`classification.yaml` now rejects any path claimed by both planes rather than
resolving it by order. Confirmed to fire:

```
classification.yaml: 1 path(s) claimed by both planes: /models (via /models* and /models)
```

Nothing is undecided. **Q2 is now down to one question: does every
control-plane path go, or only some of them?** The list is classified; what
remains is the product call about how much of it to cut.

---

**Next:** step 2 needs the ticked drop list (Q2); step 3 needs the base URL and
host count (Q1). Nothing further can start without one of those.
