# RealTags Hackathon Submission Pack

This directory is a judge-facing narrative and an evidence checklist. It does
not replace executable verification.

Public resettable demo: <https://realtags.davidwang.space>. Deployment evidence
and its durability boundary are recorded in
[`../docs/qa/hackathon/integration/PUBLIC_DEMO_DEPLOYMENT_RECEIPT.md`](../docs/qa/hackathon/integration/PUBLIC_DEMO_DEPLOYMENT_RECEIPT.md).

## Start here

1. [`JUDGE_BRIEF.md`](JUDGE_BRIEF.md) — the product story and evidence boundary.
2. [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) — a three-minute, offline-safe walkthrough.
3. [`RUNBOOK.md`](RUNBOOK.md) — clean-worktree setup and verification commands.
4. [`ARCHITECTURE_AND_DATA_FLOW.md`](ARCHITECTURE_AND_DATA_FLOW.md) — system and privacy boundaries.
5. [`CLAIMS_LEDGER.md`](CLAIMS_LEDGER.md) — what may and may not be claimed.
6. [`EVIDENCE_CHECKLIST.md`](EVIDENCE_CHECKLIST.md) — candidate evidence still required.
7. [`LIMITATIONS.md`](LIMITATIONS.md) — known gaps and non-goals.

## Evidence classes

The pack uses four mutually exclusive labels:

- **Public Live** — a bounded, credential-free public-profile response passed
  the frozen mapper. It does not prove account ownership.
- **Fixture** — deterministic synthetic data used to demonstrate the product
  path. It is not current account data.
- **Unavailable** — intentionally disabled because no safe, useful P0 mapping
  is enabled.
- **Roadmap** — future work with no present-tense implementation claim.

QA-001 is an offline run. It did not contact public APIs and therefore does not
provide current Public Live success evidence.
