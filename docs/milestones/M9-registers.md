# M9 — Statutory Registers (Phase 2 opens)

Date: 11 July 2026
Backend suite: **131 passed** (123 → 131). Frontend TS-strict + build + Vitest clean.

> **Gate note:** the PRD gates Phase 2 on Phase 1 pilot success criteria.
> The owner explicitly directed Phase 2 to begin; that business gate is
> waived by that instruction, recorded here.

## What was built (PRD §5 item 1, on the §8 architecture — not generic CRUD)

- **All 14 Companies Act registers** as typed record schemas
  (Members §88, Debenture Holders §88(2), Share Transfers r.7/SH-6,
  Directors & KMP §170, Charges §85, Investments §187/MBP-3,
  Loans/Guarantees §186/MBP-2, Related-Party Contracts §189/MBP-4,
  Renewed/Duplicate Certificates §46/SH-2, Beneficial Interest §89/MGT-6,
  Deposits §73, Sweat Equity §54/SH-3, ESOP §62(1)(b), Buy-Back §68/SH-10)
  — each with required/optional field schemas; unknown or missing fields
  are 422s listing the exact problems.
- **Append-only engine** (`register_entry`):
  - identity = `entry_key`; every edit INSERTs version n+1 — priors stay
    queryable forever; there is no updated_at because nothing updates.
  - **delete is a version event**: is_deleted + mandatory reason + actor,
    permanently visible in history; deleted entries cannot be amended
    (no resurrection of legal records). Partner-only (RBAC-tested).
  - **DB-level enforcement**: the app role has INSERT+SELECT only —
    UPDATE/DELETE revoked in the migration and verified live during this
    session AND permanently in the pre-launch grants test.
  - **Optimistic concurrency**: amendments state the version they edited;
    a stale amend gets 409 instead of a lost update.
  - **As-on point-in-time views**: any register can be read/exported as it
    stood at a given moment; exports carry the as-on stamp + per-row
    versions (§8 export requirement). Tested to the value.
- **UI**: registers page driven entirely by the server-exposed schemas —
  14 register cards with section refs and counts, dynamic entry forms
  (required fields marked), amend-as-new-version, history drawer showing
  every version incl. delete events, stamped export link.
- **Rider**: Phase 2 rule categories (fema/pf/esic/esop) added to the
  `rule_category` enum — the dataset can now cover them (PRD §5).
- Migration `e0efaa72d48a` generated and applied against Postgres 16.

## Decisions

1. One versioned-entry engine + declarative schemas per register type,
   rather than 14 bespoke tables — same philosophy as the PRD's step-engine
   for events. Register-specific behavior lives in the spec table.
2. Field schemas are drafted in-house from the statute's data requirements
   (charter 10.7). Refining them is a code-review event for the reviewing
   professional, exactly like rules.
3. Retention (§8): register history is never purged; company deletion is
   already soft, so histories survive it. A configurable archive window
   (default 8 years) becomes relevant only with hard-purge tooling — none
   exists, deliberately.

## NOT covered (honest gaps)

- Excel import for registers (bulk seeding an existing register) — the
  company-import service is reusable; add per-register importers when a
  pilot firm brings real data.
- Register-specific derived views (e.g. member ledger folios rolled up)
  and MGT-1-form-faithful print layouts — the professional should shape
  these during template review.
- Remaining Phase 2 items, in suggested order: Meeting Scheduler,
  Charges/Auditors/PCS masters + DSC tracker, Annual Filing Suite
  expansion, LLP entity type (largest — parallel data model),
  migration importers, Razorpay billing (needs an account).
