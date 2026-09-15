# TODO

Phase-based task list. Rationale and findings live in `PLAN.md`; this is the
checklist. Strike through as they land.

Every task ends green — `check.py`, `check_shape.py` and `lint.py` passing — so
work can stop at any line.

All four questions answered, 2026-09-15. Control-plane base URL confirmed the
same day. **Nothing is blocked.**

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
- **No `enum`, so no `SELF_HOSTED_GATEWAY_URL` in a dropdown.** Under OpenAPI an
  `enum` means the value *must* be one of the listed options, so a self-hosted
  reader could not enter their actual host — the dropdown would show the
  placeholder and still not work. A variable with a `default` and no `enum`
  renders as an editable field, which is the thing the placeholder was gesturing
  at. Worth a second look if you specifically wanted the dropdown; it is a
  three-line change in `servers.yaml`.

New file: **`_project/planes.yaml`**, which plane each of the 118 paths is on.
This had to be written down *before* the overrides were deleted — they were the
only record for 95 of them, and `classification.yaml` names just 23. A path
absent from it fails the build rather than defaulting to the gateway.

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

### 4. Request bodies that can generate a minimal sample
- [ ] Fill in `required` on the 13 inline request bodies that declare none
- [ ] Without this, a required-only sample renders an empty body for those 13

### 5. cURL code samples
- [ ] Run the Mintlify experiment: does its generated sample honour `required`, or dump all 24 properties?
- [ ] Pick the approach from the result — schema-only, `example` on chosen fields, or hand-written `x-codeSamples`
- [ ] cURL only; single entry suppresses the other language tabs
- [ ] Samples live in `overlays/docs-prose.yaml` with `x-airs-provenance`, not in `openapi.yaml`
- [ ] Use the key `x-codeSamples` — not the base's `x-code-samples`
- [ ] State the cURL-only decision in the README so it does not read as an omission

### 6. ~~Version and provenance~~ — done 2026-09-15
- [x] ~~`info.version` → `3.0.0`~~ — pinned in `build.py`, no longer inherited from the base

### 7. Cut the cord from the base — last task of Phase 1 (Q-C)
- [ ] Keep `check_shape.py` working through tasks 1–6; it is what proves the drops removed and never reshaped
- [ ] Only then: delete `.source/`, `scripts/check_shape.py`, `scripts/fetch-base.sh`, `_project/base-delta.yaml`
- [ ] Drop the "Fidelity to the base" CI job
- [ ] README: Portkey becomes a historical note, not a live relationship

### 8. Catch-up
- [ ] README: layout, counts, naming, known gaps
- [ ] `build-report.txt` and `PROSE-INVENTORY.csv` regenerate
- [ ] Final full run of all checks

---

## Phase 2 — deferred, agreed

- [ ] `operationId` on every operation that lacks one (re-count after Phase 1; 84 today, many are in the dropped groups)
- [ ] Descriptions, once KB access lands — the grounding gate is already built and empty by design
- [ ] Code samples in languages beyond cURL
- [ ] Decide the JSON Schema constraint question: `default`, `maximum`, `minLength` are inherited unverified
- [ ] Schemathesis against a credentialled non-prod endpoint, once one exists
- [ ] SDK generation (Stainless / Speakeasy), which needs `operationId` first

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
| Components | 578 | **480** | 474 — see note above |
| Tags | 52 | **41** | 41 ✓ |
| Spectral findings | 193 | **123** | — |
