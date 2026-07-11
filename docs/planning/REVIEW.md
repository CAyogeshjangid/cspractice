# Praxis PRD v2 + Engineering Charter — Review & Recommendations

Date: 11 July 2026
Inputs reviewed: `PRD_v2_Praxis_CS_Platform.md`, `CLAUDE_CODE_INSTRUCTIONS.md` (the
engineering charter), and the retired v1 exploration document (reviewed for context
only; per PRD §13 it is **not** committed to any repository, including this one).

> **Repo placement note.** This review lives in `nycaglobal/docs/praxis/` because that
> is where the planning conversation happened. Praxis itself should be built in a
> **separate repository** with the charter's exact `praxis/` tree — do not mix it with
> the NYCA content-automation codebase.

---

## 1. Verdict in one paragraph

The v2 PRD + charter pair is strong: the thesis (a practitioner-signed rules dataset,
with software as the delivery mechanism) is a real moat; the phasing discipline is
correct; the charter is specific and testable. The material risks are not in the code
plan — they are (a) the professional-liability exposure the sign-off model creates,
(b) the editorial operation behind the rules dataset, which is the actual critical
path and has no owner yet, and (c) a rules schema that has not been validated against
the messiness of real obligations. Items (a)–(c) should be resolved/underway before
or alongside milestone M1, not after M4.

## 2. Strengths to protect (do not trade these away under schedule pressure)

- **Accuracy as the product.** Versioned immutable rules; calendars reference a
  `rule_version`, never head; extensions stored beside (never over) computed dates;
  recompute flags `needs_review` instead of silently rewriting. This is what makes a
  date *defensible* — it is the wedge.
- **Charter C1–C12** encode a prior audit's findings as testable rules (fail-fast
  settings, no wildcard CORS, append-only audit via Postgres grants, `firm_id` at the
  repository layer with a permanent cross-tenant test suite). Treat as load-bearing.
- **Explicit non-goals with reasons** — especially "no MCA automation pending legal
  opinion." Keep the "scope addition requires equivalent removal, in writing" rule.

## 3. Findings and recommendations (priority order)

### F1 — The sign-off model is a liability decision, not just a feature (BLOCKING)
A named professional signs the dataset; subscriber firms rely on it across portfolios
NYCA has no engagement letter with. A stale rule → client penalty → exposure on the
sign-off. **Decide before code:** is the dataset (a) a verified *reference* the
subscriber professionally confirms for each entity (shared responsibility), or (b) a
guarantee? The ToS, UI copy, and the `needs_review` gate must all encode the same
answer. Fold this into the legal brief already being commissioned for Open Question
#1 (MCA terms), together with DPDP posture — one engagement, three answers.

### F2 — The editorial operation is the critical path (BLOCKING)
CLAUDE.md §6 correctly forbids inventing rule content, so the engine ships empty
until a named owner authors and maintains the ROC/IT/GST dataset (monthly cadence,
48-hour circular turnaround). That is Open Question #3, still unowned.
**Recommendation:** name the owner and stand up the authoring pipeline (YAML in PRs,
professional review as the merge gate) in parallel with M1, not after M4. The code is
the cheap part.

### F3 — Validate the rules schema against real obligations before the calendar UI
Real obligations are gated on attributes the Phase 1 company master does not hold
(turnover, net worth, borrowings, MSME dues), recur within a FY (GSTR-3B, TDS
returns, MSME-1), and anchor on events (BEN-2). **Done in this repo:** see
`rules-schema-spike.md` alongside this file — 16 real obligations pushed through the
proposed schema, with the schema gaps and proposed fixes enumerated. Headline: the
§5/§6 schema needs (i) a recurrence construct or an explicit Phase 1 exclusion of
periodic returns, (ii) an "applicability unknown → needs_review" tri-state, and
(iii) a small set of per-FY financial attributes on the company master.

### F4 — Timeline realism
10–12 weeks must cover tenancy/auth/RBAC/TOTP, atomic Excel import, the rules engine
with recompute, an arq reminder pipeline with dead-letter, five stamped docx
generators, security suite, ZAP, Playwright E2E, and tested backup/restore — and the
charter deliberately adds rigor. Unless staffing is 3–4 engineers, plan ~16–20 weeks
or pre-agree the cut list: Tasks (§4.8) first, then document generators 5 → 3
(AGM Notice, Minutes, Lists) — neither weakens the wedge.

### F5 — Onboarding narrative vs. engine behavior
"Calendar auto-populated and verified in an afternoon" collides with the (correct)
engine rule that missing anchors/attributes emit `needs_review` rows without dates. A
real first import produces a calendar heavy with review rows. Keep the engine
behavior; fix the narrative: onboarding = import **plus a guided review-queue
resolution session**. Measure the 4-hour target against that full flow.

### F6 — "Filed" is self-reported; say so
With MCA integration deferred, filed-with-SRN is a manual mark and will drift.
Acceptable for v1. Add a lightweight periodic reconciliation nudge ("N rows marked
filed this quarter — spot-check against MCA"), and do not market certainty the system
cannot observe.

### F7 — Defense-in-depth for tenancy
C10 (repository-layer `firm_id`) is good but one forgotten filter is a cross-tenant
leak. Add **Postgres row-level security** keyed on a per-request `firm_id` setting as
a second wall. Complements, does not replace, the repository discipline and the
cross-tenant test suite. No conflict with C5 (one database).

### F8 — Specify re-import × soft-delete now
M3: "re-import is idempotent on CIN"; companies soft-delete with CIN unique per firm.
Define before M3: re-importing a soft-deleted CIN → propose **restore-and-update with
an activity-log entry** (not a new row, not a hard conflict). Also define whether the
partial unique index excludes soft-deleted rows.

## 4. Recommended sequence

1. Separate `praxis` repo; charter file at root; v1 exploration doc stays out of git.
2. Legal brief covering: MCA terms (already planned) + sign-off liability model (F1)
   + DPDP fiduciary posture.
3. Name the rules-dataset owner; start the editorial pipeline alongside M1 (F2).
4. Adopt the schema changes from the spike (F3) into CLAUDE.md §5/§6 before M4.
5. Confirm staffing; set the cut list in writing (F4).
6. Proceed M1 → M7 per the charter.
