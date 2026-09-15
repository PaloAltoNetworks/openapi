1. x-mint.href — the thing we're actually blocked on

Problem. 122 links across 53 aigw/ pages still point at the old Portkey-branded Latest version. We can't repoint them, because the target pages are generated from your spec and have no stable URL: every operation summary is '' and no operation carries x-mint. Titles and slugs are unpinned, so anything we hardcode today gets invalidated when prose lands.

Ask: Set x-mint.href on every operation.

Why this isn't blocked on the KB. A URL slug is structural, not prose. It asserts nothing about behaviour, so the grounding gate doesn't apply and Q2 doesn't gate it.

Suggested scheme — systematic and machine-checkable:

/aigw/api-reference/{tag-path}/{operation-slug}

- {tag-path}: tag name kebab-cased, with the > hierarchy becoming path segments. Integrations > Models → integrations/models; Analytics > Graphs → analytics/graphs.
- {operation-slug}: operationId kebab-cased. createChatCompletion → create-chat-completion.

On the 53 operations with no operationId. Your build report rightly refuses to invent them — an operationId is a client-facing contract key and a fabricated one is worse than a missing one. An href slug is a different kind of object. It's a docs URL, it binds nothing in client code, and choosing one is not the same as inventing a contract. So please do pick slugs for those 53 rather than leaving them unpinned — just don't back-fill operationId from them.

One caution. Published hrefs become the public URL contract; changing them later breaks inbound links and anything we write into 122 link sites. Worth getting right in one pass rather than iterating.

2. Please own the prose as well

Vrushank's decision: prose ownership moves to your repo. Summaries, descriptions at every level, tag descriptions, info.description, example prose. Docs will not author or patch spec prose, and will not hand-edit anything downstream of you.

Two things follow.

Today openapi.yaml on main is structure-only — its own header says "see overlays/docs-prose.yaml for every field a reader reads." We verified this costs nothing right now: bare and overlay-flattened publish 68 non-empty description/summary strings, because the overlay's 223 actions currently only blank inherited Portkey prose rather than supply new prose.

That stops being true the moment you populate the overlay against the KB — at which point the URL we read would silently serve prose-free pages, with no build error. Rather than have docs resume mirroring (we just removed that), please publish the resolved artifact to a stable path on main on the same YAML.

https://raw.githubusercontent.com/PaloAltoNetworks/openapi/refs/heads/main/openapi.yaml


Grounding stays yours. Everything you put in summary, description, tag descriptions and x-mint.content/pre/post renders as public prose on the docs site and into llms.txt / llms-full.txt. 

3. x-server-groups — stale, please drop

The published spec still carries:

x-server-groups:
  ControlPlaneServers:
  - url: https://api.portkey.ai/v1
  - url: SELF_HOSTED_CONTROL_PLANE_URL
  DataPlaneServers:
  - url: https://api.portkey.ai/v1
  - url: SELF_HOSTED_GATEWAY_URL
  PublicServers:
  - url: https://api.portkey.ai

Three stale api.portkey.ai URLs. It's not a standard OpenAPI field, nothing reads it, and the real servers[] and per-operation servers are already correct (aigw.portkey.ai/v1, the self-hosted placeholder, mp.us.prod.airs-gw.portkey.ai). It reads as inherited residue. Phase 2 moved every base URL in the docs corpus off api.portkey.ai, so this is the last place it survives — and it's public.

Please remove it, or if something does consume it, say what, and we'll leave it alone.

4. Tag names are now a load-bearing join key

Your handoff left tags[].name as an open judgement call. It's resolved by how we consume you: tags are the join between your spec and our navigation. A renamed tag silently empties a docs nav group; a new tag goes unrendered.

We've added aigw/scripts/check_nav_matches_remote.py on our side, which fails on drift in either direction (currently 40/40, in sync). But it only catches drift after you ship. Please treat a tag rename or addition as a coordinated change and give us a heads-up — it's a docs migration, not a spec edit, the same way a path rename was under the old stub-file scheme.


Verify:

- You cannot verify x-mint.href locally either. Don't assume a green mint validate means the hrefs render.
- Verification needs a real Mintlify preview deployment. PR #1076's Mintlify check came back SKIPPED, so nothing has proved the generated pages exist yet.
- Worth adding to your own CI: assert every operation has an x-mint.href, that hrefs are unique, and that each is consistent with the operation's tag. That's checkable in your repo without a Mintlify build, and it's the only verification available until the preview works.

Summary of asks

1. x-mint.href on all 181 operations, including the 53 without an operationId — unblocks our 122-link repoint, needs no KB access.
2. Take ownership of prose, and update the YAML with that.
3. Drop x-server-groups.
4. Treat tag renames/additions as coordinated changes.
6. Add a CI check for href presence, uniqueness and tag consistency.