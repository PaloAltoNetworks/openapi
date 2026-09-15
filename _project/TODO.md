# TODO

Phase-based task list. Rationale and findings live in `PLAN.md`; this is the
checklist. Strike through as they land.

Every task ends green — `check.py`, `check_shape.py` and `lint.py` passing — so
work can stop at any line.

All four questions answered, 2026-09-15. **One thing still needed before task 2
can finish: the control-plane base URL.** Everything else is unblocked.

---

## Phase 1 — the sweeping changes

### 1. Drop the marked control-plane operations
- [ ] Delete the 11 tag groups marked `[DROPPED]`: Audit Logs, Collections, Deployments, Labels, Log Exports, Prompt Partials, Prompts, User Invites, Users, Virtual Keys, Workspaces > Members
- [ ] Also drop the two gateway `Prompts` paths — `/prompts/{promptId}/completions` and `/prompts/{promptId}/render` — so the whole Prompts surface goes together (Q-A)
- [ ] → **33 paths, 61 operations.** Leaves **118 paths, 181 operations**
- [ ] Prune components orphaned by the deletion, by reachability → **578 to 474**
- [ ] Sweep the 58 components already unreachable before any deletion
- [ ] Regenerate `tags-map.yaml` and `docs-navigation.json` — **52 tags to 41**, 11 emptied
- [ ] Re-baseline Spectral and record the new counts
- [ ] Record every removal in `_project/base-delta.yaml` with a reason
- [ ] Let `breaking-changes.yml` fire and keep the comment as the audit trail

### 2. One base URL that drives everything
- [ ] Delete all 130 path-level and 2 operation-level `servers` overrides
- [ ] Single root `servers` block using an OpenAPI server variable with a `default` and an `enum` — one line to edit, and it is how the self-hosted option gets offered
- [ ] Data plane → `https://aigw.portkey.ai/v1`, prefix unchanged
- [ ] Offer `SELF_HOSTED_GATEWAY_URL` as the alternate, as today
- [ ] Second root entry for the control plane — **URL still needed (Q-B)**. 66 control-plane paths survive and sit on a different host
- [ ] Remove the three placeholder strings that are not URLs
- [ ] Extend `check.py` to fail if any host appears outside the root block
- [ ] Add `servers` to `normalise:` in `base-delta.yaml`

### 3. Authorization header only
- [ ] Drop the five alternative `security` combinations (Virtual-Key, Provider-Auth, Provider-Name, Config, Custom-Host)
- [ ] Drop the now-unused security schemes and their `x-portkey-*` parameters
- [ ] Single `Authorization` bearer scheme, and show only that
- [ ] Amend the README's "never renamed" rule — this is a deliberate exemption
- [ ] Record the added scheme in `base-delta.yaml`

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

### 6. Version and provenance
- [ ] `info.version` → `3.0.0`

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
| Q-B | Control-plane base URL, since 66 control-plane paths survive | **A different host.** URL to follow — the only outstanding blocker |
| Q-C | When to retire the base linkage | **End of Phase 1**, so the guardrail covers the drops |
| Q-D | Is 31 paths the intended drop, not 97? | **Yes.** 66 control-plane paths stay by design |

## Still needed

- **The control-plane base URL (Q-B).** Task 2 can be done except for that one
  value. Everything else in Phase 1 is unblocked.

## The shape of Phase 1

| | Now | After task 1 |
|---|---|---|
| Paths | 151 | **118** |
| Operations | 242 | **181** |
| Components | 578 | **474** |
| Tags | 52 | **41** |
