# Rules-Schema Spike — Findings

Date: 11 July 2026
Status: complete — 16 real obligations modeled in `rules-spike/*.yaml`
Purpose: validate the rules schema proposed in `CLAUDE_CODE_INSTRUCTIONS.md` §5/§6
**before** milestone M4 builds the calendar on top of it (REVIEW.md finding F3).

> The YAML files are **schema stress-tests, not rule content**. Every date,
> threshold, and citation is marked `[UNVERIFIED — spike]` and `signoff: null`.
> Per charter §6, only professionally signed entries may ever load into a
> non-test environment — the loader must enforce that.

## What was modeled

| Category | Obligations | Schema stress exercised |
|---|---|---|
| ROC | AGM, AOC-4, AOC-4 XBRL, MGT-7, MGT-7A, ADT-1, DIR-3 KYC, DPT-3, MSME-1, BEN-2, CSR-2 | variants, derived attributes, anchor fallback, per-director subject, multi-occurrence, event anchor, prior-FY financials |
| Income Tax | ITR-6, tax audit (3CA/3CD), TDS quarterly, advance tax | date variants (TP), unknown attributes, 4-occurrence, cross-FY due dates |
| GST | GSTR-9, GSTR-9C, GSTR-3B (monthly) | per-GSTIN identity, recurrence, deliberate-exclusion mechanism |

## Verdict

The §5/§6 schema is **directionally right but not yet sufficient**. Eight gaps,
three of which change tables and must land before M4:

## Gaps

### G1 — Applicability depends on attributes the company master doesn't hold (BLOCKING)
Turnover, net worth, net profit, borrowings, MSME dues, deposits/receipts, TAN,
GST registration, TP exposure. Affects 10 of 16 obligations.
**Fix (two parts):**
1. New table `company_fy_attributes` — `firm_id, company_id, fy, turnover,
   net_worth, net_profit, has_tan, has_gst_registration, …` — nullable
   throughout, editable by Manager+, one row per company per FY. Financial
   attributes are **per-FY facts, not company constants** (see also G8).
2. **Tri-state predicate evaluation**: `true / false / UNKNOWN`. A predicate
   touching a null attribute resolves UNKNOWN → the row is emitted with
   `needs_review = true` and reason "confirm applicability", never silently
   dropped. Silently-false is the dangerous failure mode for a product whose
   promise is "never miss a date": a missed *emission* is invisible.

### G2 — Mutually exclusive rule pairs (BLOCKING)
AOC-4 vs AOC-4 XBRL; MGT-7 vs MGT-7A. Without exclusivity both rows are
emitted, or the professional maintains four perfectly complementary predicates
by hand (fragile under threshold changes).
**Fix:** `supersedes: [ROC-AOC4]` on the specific rule — if the specific rule's
predicate is TRUE, the general row is suppressed; if UNKNOWN, emit **both**
flagged needs_review.

### G3 — Single anchor can't express fallbacks
MGT-7A for OPC: no AGM exists; the clock runs from a deemed date.
**Fix:** anchor becomes an ordered list, e.g.
`anchor: [agm_date, {fy_end: {plus_months: 6}}]` — first resolvable wins;
none resolvable → needs_review (existing rule, unchanged).

### G4 — Event-anchored obligations don't fit, and shouldn't (decision, not code)
BEN-2 (30 days from BEN-1 receipt) can't be computed from FY master data.
**Fix:** `phase: 3` field on rules so exclusions are *explicit and reviewable*
in the dataset rather than silent omissions. Event-anchored rules wait for the
Phase 3 event engine. ADT-1-style "only in appointment years" is the mild
version: emit yearly with a confirm-applicability note (documented compromise).

### G5 — Derived attributes need an engine-level registry
`is_small_company` (paid-up ≤ ₹4cr AND turnover ≤ ₹40cr AND not
holding/subsidiary/s.8), `is_first_fy`. These are *definitions in law* that
change (small-company thresholds have changed twice in recent years).
**Fix:** derived attributes are versioned entries in the dataset itself (same
sign-off flow), evaluated by the engine, usable in any predicate. Not Python
code — a threshold change must be a dataset PR, not a deploy.

### G6 — Per-subject obligations (BLOCKING — touches `calendar_row`)
DIR-3 KYC is per **director**; GST is per **GSTIN**. `calendar_row` is
per-company.
**Fix:** add `subject_type ENUM(company, director) + subject_id` to
`calendar_row`, defaulting to company. Phase 1 uses `director` only for
DIR-3 KYC; GSTIN stays a remark until Phase 2 models registrations.
Retrofitting a subject dimension after M4 ships would be painful — do it now.

### G7 — Multiple occurrences per FY
MSME-1 (×2), TDS (×4), advance tax (×4), GSTR-3B (×12).
**Fix:** optional `occurrences[]` (each with label + offset_spec) and, for
true recurrences, a `recurrence` spec. `calendar_row` gains
`occurrence_label`. **Recommendation:** Phase 1 ships occurrences (MSME-1,
TDS) but **excludes monthly GST returns** — high row-volume, low signed-value,
per-GSTIN correctness we can't guarantee. Written as a dataset exclusion with
reason (see gst.yaml).

### G8 — FY-boundary and prior-FY semantics (convention, must be written down)
TDS Q4 is due 31 May — *after* the FY it reports. CSR applicability tests the
**preceding** FY's financials.
**Fix:** two conventions in charter §9: (a) a calendar row belongs to the FY of
the *period reported*, even when the due date falls in the next FY;
(b) predicates may address attributes at `fy` or `fy-1`
(e.g. `{ attr: net_worth, at: fy-1, op: gte, ... }`).

## Concrete schema deltas to fold into CLAUDE.md §5

- `compliance_rule`: `anchor` → ordered list; add `variants[]`, `occurrences[]`
  / `recurrence`, `supersedes[]`, `phase`.
- New: `derived_attribute` (versioned, signed-off, same flow as rules).
- New: `company_fy_attributes` (per-FY financial/registration facts, nullable).
- `calendar_row`: add `subject_type`, `subject_id`, `occurrence_label`,
  `needs_review_reason ENUM(missing_anchor, applicability_unknown, rule_revised)`.
- Engine: tri-state predicate evaluation; UNKNOWN → emit + needs_review.

## Effect on Phase 1 UX (feeds REVIEW.md F5)

With tri-state evaluation, a fresh MCA-Excel import (no turnover, no AGM date,
no GST facts) correctly yields a calendar dominated by needs_review rows.
That is the honest state — so onboarding must include a **review-queue
resolution step**: a screen that walks the firm through unknown attributes
company-by-company ("Does X have GST registration? Turnover band?") and
watches rows resolve. Recommend making this queue an explicit M4 deliverable;
it is the difference between "the import worked" and "the calendar is usable."

## Suggested next step

Fold the deltas into charter §5/§6 (one focused edit), then have the named
professional (Open Question #3) review the *shape* of the YAML — not the dates —
so the authoring format is settled before the editorial pipeline starts.
