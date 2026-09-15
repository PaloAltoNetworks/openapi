# TODO

Phase-based task list. Rationale and findings live in `PLAN.md`; this is the
checklist. Strike through as they land.

Every task ends green — `check.py`, `check_shape.py` and `lint.py` passing — so
work can stop at any line.

**Four questions are open (Q-A to Q-D at the bottom). Two of them change what
Phase 1 contains.**

---

## Phase 1 — the sweeping changes

### 1. Drop the marked control-plane operations
- [ ] Delete the 11 tag groups marked `[DROPPED]`: Audit Logs, Collections, Deployments, Labels, Log Exports, Prompt Partials, Prompts, User Invites, Users, Virtual Keys, Workspaces > Members
- [ ] → **31 paths, 59 operations.** Leaves 120 paths, 183 operations
- [ ] Prune components orphaned by the deletion, by reachability
- [ ] Sweep the 58 components already unreachable before any deletion
- [ ] Regenerate `tags-map.yaml` and `docs-navigation.json` for emptied tags
- [ ] Re-baseline Spectral and record the new counts
- [ ] Record every removal in `_project/base-delta.yaml` with a reason
- [ ] Let `breaking-changes.yml` fire and keep the comment as the audit trail

### 2. One base URL that drives everything
- [ ] Delete all 130 path-level and 2 operation-level `servers` overrides
- [ ] Single root `servers` block using an OpenAPI server variable with a `default` and an `enum` — one line to edit, and it is how the self-hosted option gets offered
- [ ] Data plane → `https://aigw.portkey.ai/v1`, prefix unchanged
- [ ] Offer `SELF_HOSTED_GATEWAY_URL` as the alternate, as today
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
- [ ] Cut the cord from the base spec — see **Q-C**, which affects when

### 7. Catch-up
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

## Open questions

**Q-A — `Prompts` spans both planes, and only one side is marked.**
`### Prompts [DROPPED]` sits under Control Plane, covering 5 paths. Two more
paths carry the same tag but are **gateway**, so as marked they survive:

- `/prompts/{promptId}/completions`
- `/prompts/{promptId}/render`

That ships an API where a prompt can be executed but not created, listed or
versioned. Coherent if prompts are managed in the UI; a gap if not.
**Drop those two as well, or keep them?**

**Q-B — What is the control-plane base URL?**
Q1 gave the data plane (`https://aigw.portkey.ai/v1`). But 66 control-plane
paths survive the drop, and they are on a different host today. Same host, a
second server entry, or something else?

**Q-C — When do we retire the base linkage?**
You said cut the cord today. Doing it before task 1 removes
`scripts/check_shape.py` — the guardrail proving we only removed things and
never reshaped one — during the single riskiest change in this plan. **I would
retire it at the end of Phase 1, not the start.** Confirm or overrule.

**Q-D — Confirm the drop is 31 paths, not 97.**
11 of 36 control-plane tag groups are marked, so **66 control-plane paths
stay** — including Analytics (22 paths), MCP Servers and MCP Integrations (10),
API Keys, Configs, Workspaces, Guardrails. Deliberate, or is the list still in
progress?
