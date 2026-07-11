# Rules Dataset Authoring Guide

For the named professional who owns the compliance rules dataset (PRD §7,
Open Question #3). The YAML files you sign are the product's core asset:
every due date Praxis shows traces to an entry here, with your name on it.

**Golden rule:** the engine never guesses. Anything it cannot determine —
a missing anchor date, an unknown company attribute — becomes a flagged
"needs review" row for the firm to resolve. Your job is correctness of the
rules; the engine's job is honesty about uncertainty.

---

## 1. Where rules live and how they ship

- Files: `backend/app/rules/dataset/*.yaml` — one file per category is the
  convention (`roc.yaml`, `income_tax.yaml`, `gst.yaml`).
- Workflow (the sign-off IS the process):
  1. Branch → edit YAML → cite the statute/rule/circular in the entry.
  2. Run the pre-flight locally: `python -m app.rules.check`
     (CI runs it on every PR — structural errors block the merge).
  3. PR review by you (or a second professional for your own edits).
     **Merging the PR is the professional sign-off event.**
  4. Deploy → `python -m app.rules.load` — idempotent; unchanged entries do
     nothing; changed entries create a NEW immutable version and flag every
     affected calendar row "rule revised — review". Dates are never silently
     rewritten.
- The loader **refuses unsigned entries** outside tests. `TEST-ONLY-*` codes
  are reserved for fixtures and never load into production.

## 2. Anatomy of a rule entry

```yaml
- code: ROC-AOC4                      # stable ID; never reuse or rename
  category: roc                       # roc | income_tax | gst
  obligation_name: Filing of financial statements
  form_number: AOC-4                  # optional
  effective_from: 2025-04-01          # first date this VERSION applies
  applicability:                      # omit = applies to every company
    all:
      - {attr: entity_type, op: eq, value: company}
  anchor: agm_date                    # what the clock runs from
  offset_spec: {type: offset, unit: days, amount: 30}
  source_citation: "Companies Act 2013, s.137(1)"
  signoff:
    by: "Your Name, M.No. XXXXX"
    date: 2026-07-15
    note: "optional context for the version history"
```

## 3. The constructs, and when to reach for each

### Applicability predicates (tri-state — read this twice)
Combinators `all` / `any` / `not`; leaf tests
`{attr, op: eq|ne|gt|gte|lt|lte|in, value, at: fy|fy-1}`.

An attribute the firm hasn't recorded evaluates **UNKNOWN**, not false.
UNKNOWN rows are **emitted and flagged** "confirm applicability" — never
silently dropped, because a silently missing obligation is invisible until
the penalty arrives. Write predicates on the conservative side: if the
threshold has carve-outs the schema can't express, encode the superset and
say so in `source_citation`; firms mark rows not-applicable after review.

Use `at: fy-1` when the law tests the PRECEDING year's figures (CSR-style).

Attributes available today: `entity_type, category, is_listed,
paidup_capital` (from the company master) and `turnover, net_worth,
net_profit, has_tan, has_gst_registration, has_transfer_pricing,
has_outstanding_receipts, has_msme_dues_over_45d` (per-FY facts the firm
maintains). Need a new one? That is a schema change — raise it, don't
improvise with a wrong attribute.

### Anchors — ordered fallback list
`anchor: [agm_date, {fy_end: {plus_months: 6}}]` — first resolvable wins
(e.g. MGT-7A for OPCs which hold no AGM). If nothing resolves, the row is
emitted dateless and flagged `missing anchor`. Available: `fy_end`,
`agm_date`, `fixed_date` (nominal — pair with a fixed offset_spec),
`{fy_end: {plus_months: N}}`.

### Offsets
- From the anchor: `{type: offset, unit: days|months, amount: N}`
  (month arithmetic clamps: 31 Mar + 6 months = 30 Sep).
- Fixed calendar date: `{type: fixed, month: M, day: D,
  year_ref: fy_start_year|fy_end_year|fy_end_year_plus_1}`.
  Convention: a row belongs to the FY of the period reported, even when its
  due date falls after FY end (TDS Q4-style).

### Variants — date changes by company class
```yaml
variants:
  - when: {attr: has_transfer_pricing, op: eq, value: true}
    offset_spec: {type: fixed, month: 11, day: 30, year_ref: fy_end_year}
```
First TRUE variant wins. A variant that evaluates UNKNOWN keeps the base
date but flags the row — the firm confirms which date applies.

### Occurrences — several due dates per FY
```yaml
occurrences:
  - {label: "Apr–Sep", offset_spec: {type: fixed, month: 10, day: 31, year_ref: fy_start_year}}
  - {label: "Oct–Mar", offset_spec: {type: fixed, month: 4,  day: 30, year_ref: fy_end_year}}
```
One calendar row per occurrence, labeled. Policy note: monthly GST returns
are a WRITTEN exclusion in Phase 1 — do not add them without a product
decision.

### supersedes — mutually exclusive pairs
`supersedes: [ROC-AOC4]` on the specific rule (e.g. the XBRL variant).
If the specific rule's applicability is TRUE, the general row is dropped;
if UNKNOWN, **both** rows emit flagged so the firm decides.

### subject: director
Per-director obligations (DIR-3 KYC). One row per DIN-holding director;
a director whose DIN allocation date is unrecorded gets a flagged row.

### phase
`phase: 3` excludes an entry from Phase 1 computation explicitly (event-
anchored obligations like BEN-2). Use it so exclusions are reviewable
decisions in the dataset, never silent omissions.

## 4. Government extensions (circulars)

Extensions are **not** edits to the rule — the computed date is never
overwritten. They are `rule_extension` records citing the circular, with an
optional predicate when relief is class-limited (e.g. TP cases only).
Authoring today is by ops insert (see RUNBOOK); an authoring API is on the
roadmap. Both dates show on every affected row.

## 5. Versioning discipline

- Changing any payload field of an entry = a **new version** on next load;
  the old version stays queryable forever and rows pinned to it get flagged.
- Never delete an entry that has ever shipped: set `phase: 3` or narrow its
  `applicability` instead, with a note. Codes are permanent.
- `effective_from` marks when the new version starts applying — a rule
  change effective next FY should carry next FY's start date.

## 6. Cadence (PRD §7, non-negotiable)

- Monthly review of the full dataset against MCA/CBDT/GST activity.
- **48-hour turnaround** on any circular affecting a covered obligation:
  branch → entry/extension with citation → pre-flight → PR → sign-off →
  load. The RUNBOOK has the deploy-side steps.

## 7. Pre-flight failures decoded

| Message | Meaning |
|---|---|
| `payload does not parse` | missing/invalid field — compare with §2 skeleton |
| `evaluation crashed … unsupported offset unit` | typo in offset_spec |
| `malformed predicate node` | bad combinator/op key in applicability |
| `dateless row without needs_review` | engine bug or unsupported construct — report it |
| `WARN … no signoff` | entry will be refused by the production loader |
