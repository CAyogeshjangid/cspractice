# Product Requirements Document — v2.0
## Praxis — CS Practice Management Platform (working codename; rename before launch)

Version 2.0 — 11 July 2026
Supersedes v1.0. All references to the observed competitor product and the word "clone" are removed by policy (see §13, Legal Posture). This document defines what we build, in what order, and what we explicitly refuse to build in v1.

---

## 0. Product Thesis (read this before anything else)

**Problem.** Practicing Company Secretaries and CA firms in India manage 30–300 client entities using Excel sheets, WhatsApp reminders, and memory. Missed statutory due dates mean client penalties and professional liability. Existing software tools compute due dates from static formulas that go stale the moment CBDT or MCA issues an extension circular — and the practitioner carries the risk of that staleness.

**Wedge.** We are not selling software features. We are selling a **practitioner-maintained compliance calendar whose dates are verified by a working CA firm**, wrapped in the minimum workflow needed to act on those dates (entity masters, reminders, and document generation). Accuracy is the product. Everything else is delivery mechanism.

**Why us.** NYCA & Co. practices tax and corporate law daily. A pure software vendor must hire consultants to keep due-date rules current; we already do this work for our own clients. Our rules dataset is a by-product of our practice, versioned and published with a named professional's sign-off. No software company can credibly match that without becoming a firm.

**Who pays.** PCS firms and CA firms with 20+ corporate clients. Secondary: in-house compliance officers at single companies (lighter tier, later).

**Switching trigger.** Onboarding in one afternoon: bulk Excel import of the entity portfolio, calendar auto-populated and verified, first reminder emails flowing the same day.

**Provisional pricing hypothesis (to be validated in Phase 1 pilot).**
- Free: 3 entities, calendar + reminders only, single user.
- Professional: ₹X per entity per year (target band ₹300–600/entity/yr), all Phase 1 + 2 modules, 5 team seats.
- Firm: custom, unlimited seats, priority rules-update SLA, white-label letterheads.
Financial Information and portfolio-level reports gate at Professional.

**Success criteria (the definition of "worked").**
- 5 paying firms within 90 days of Phase 1 launch; 25 within 180 days.
- Zero missed statutory dates attributable to a stale rule in the dataset (measured against a monthly audit of circulars vs dataset versions).
- Median onboarding time from signup to populated calendar: under 4 hours.
- 60% weekly active rate among paid accounts at day 90.
If the first two fail, we stop and rethink before building Phase 2.

---

## 1. Goals and Non-Goals

### Goals (Phase 1)
1. A firm can import its full company portfolio from Excel/MCA master-data files in one sitting.
2. Every imported entity gets a compliance calendar (ROC, Income Tax, GST categories) computed from a versioned, professionally signed-off rules dataset.
3. Email reminders dispatch reliably N days before each due date, per row, per assignee.
4. The five highest-frequency annual documents generate correctly on selected letterhead from entity master data.
5. Every write action is captured in an immutable activity log.

### Non-Goals for Phase 1 (explicit, with reasons)
1. **No MCA portal integration of any kind** — no captcha sessions, no cookie injection, no VPD payment flow, no filing-status scraping. Blocked pending a written legal opinion on MCA terms of use (§13). Manual entry + Excel import is the v1 data path.
2. **No LLP module.** Companies only. LLPs are a parallel data model that doubles surface area; Phase 2.
3. **No event wizards** (director appointment, share capital change, etc.). Phase 3, built on a step-engine.
4. **No statutory registers module.** Phase 2, because it requires the append-only integrity architecture (§8) and we will not ship registers as generic CRUD.
5. **No AI assistant.** Phase 3. AI-drafted statutory documents require a mandatory human-review gate we have not designed yet.
6. **No Telegram, no Google Drive provisioning, no subscription billing engine.** Phase 1 pilot is invoiced manually.
7. **No Reports hub.** One export (Excel/Word) per screen is sufficient for v1.

Any scope addition to Phase 1 requires an equivalent scope removal, in writing.

---

## 2. Target Users and Stories (Phase 1)

Personas: **Partner** (firm owner, CS/CA), **Manager** (qualified staff), **Executive** (articled assistant/support staff), **Viewer** (client or auditor, read-only).

Priority-ordered stories:
1. As a Partner, I want to bulk-import my client companies from Excel so that onboarding does not require weeks of data entry.
2. As a Manager, I want each company's FY-based due dates computed automatically so that I never build a compliance calendar by hand again.
3. As a Partner, I want to know which rule version and which circular produced each due date so that I can defend the date to a client or regulator.
4. As an Executive, I want reminder emails for rows assigned to me so that nothing slips while I handle 40 companies.
5. As a Manager, I want to generate an AGM Notice on the client company's letterhead from master data so that document prep takes minutes, not hours.
6. As a Partner, I want an activity trail of who changed what so that I can supervise articled staff with confidence.
7. As a Partner, I want to mark a calendar row as filed with an SRN reference so that the calendar reflects reality, not just theory.
8. As an Executive, I must NOT be able to delete a company or edit firm settings (negative requirement — enforced by RBAC).

---

## 3. Core Concepts and Multi-Tenancy

- **Firm (tenant)**: the paying account. All data rows carry `firm_id`. Cross-firm access is impossible at the query layer, not just the UI layer.
- **User**: belongs to exactly one firm, holds one role (Partner / Manager / Executive / Viewer).
- **Working Company selector**: persistent global context switcher; every downstream screen is scoped to the selected entity. Selection is a UI convenience only — authorization is always checked server-side per request.
- **Professional Group / Industry tags**: user-extensible taxonomies for portfolio filtering.

---

## 4. Phase 1 Functional Requirements

### 4.1 Authentication & Firm Setup (P0)
- Email + password with mandatory strong-password policy; TOTP 2FA available from day one for Partner role.
- No seeded accounts. First user registers and becomes Partner. Invitation-only for additional users.
- JWT in httpOnly cookies; CSRF protection active and tested (see Engineering Charter — this is a named lesson).

### 4.2 Companies Master (P0)
- CRUD with role gating (Executive: create/edit; Partner only: delete — soft delete with reason, never hard delete).
- Fields: CIN, name, registration number, incorporation date, category/status, registered address, email, phone, professional group, industry, FY end, AGM date, capital structure.
- Excel import: downloadable template; validation report before commit (row-level errors listed, nothing partially imported); MCA master-data Excel format accepted as-is.
- Excel export of the portfolio.

### 4.3 Directors Register (master data) (P0)
- Per-company: name, DIN, DIN status, designation, appointment/cessation dates, active flag, disclosure flags (MBP-1, DIR-8, DIR-2) per FY.
- FY filter. Excel import/export.

### 4.4 Shareholders Register (master data) (P0)
- Per-company cap table: name, folio, shares, %, category. Totals row with validation (percentages must sum to ~100 with tolerance warning). Excel import/export.

### 4.5 Compliance Calendar (P0 — the core)
- Per entity, per FY. Categories in Phase 1: **ROC, Income Tax, GST** only (FEMA/PF/ESIC/ESOP in Phase 2 once the rules process is proven).
- Each row: category, obligation name, form number, computed due date, rule reference (rule ID + version + source citation), custom override date, extension date (with circular reference), assignee, status (pending / in progress / filed / not applicable), SRN reference, remarks.
- Due dates come ONLY from the Rules Engine (§7). The UI never contains a hardcoded date formula.
- Overrides and extensions never destroy the computed date — both are stored, both displayed.
- Bulk Excel download/upload of calendar rows. Word export of the calendar per entity.
- "Filed" status requires an SRN or an explicit "filed offline" acknowledgment.

### 4.6 Reminders (P0)
- Per row: days-before-due (multi-value, e.g. 30/15/7/1), recipient = assignee plus optional extra emails.
- Dispatch via SMTP or Resend (firm-configurable). Every dispatch logged. Failed sends retried with backoff and surfaced in a dead-letter view — silent failure is a defect.

### 4.7 Document Generators (P0 — exactly five)
1. AGM Notice
2. Directors' Report (skeleton per §134 — content sections templated, financial figures manually entered in v1)
3. Board/AGM Meeting Minutes
4. Attendance Sheet
5. List of Directors / List of Shareholders (one generator, two outputs)

Requirements:
- Word (.docx) output via server-side templating; letterhead selector (company / PCS firm / none) with correct signing blocks.
- Every template carries a validation stamp: reviewing professional's name, membership number, governing section/standard (e.g., §134, SS-2), review date, template version. Templates without a current stamp cannot be used in production (enforced, not advisory).
- Generated documents saved to the Document Library with source data snapshot.

### 4.8 Tasks (P1)
- Lightweight tracker linked to entities and calendar rows; priority, due date, assignee, status tabs. Ship if time allows; cut without hesitation if Phase 1 slips.

### 4.9 Activity Log (P0)
- Append-only. Actor, firm, entity, action, before/after diff, timestamp, IP. No update or delete path exists for this table at the application layer. Partner-visible, filterable.

---

## 5. Phase 2 (build only after Phase 1 success criteria are met)

- Statutory Registers module (all 14 Companies Act registers) on the append-only architecture (§8).
- LLP entity type with parallel masters and LLP Form 11/8 working papers (manual data, no MCA fetch).
- Meeting Scheduler (combined Notice/Minutes/Attendance packs per meeting per FY).
- Annual Filing Suite expansion (Shorter Notice, Board Meeting Attendance, Auditor Appointment, MR-3 skeleton).
- Compliance categories: FEMA, PF, ESIC, ESOP.
- Charges, Auditors master, PCS master, DSC token tracker.
- Director KYC cycle tracker (computed from DIN allocation date — pure logic, no MCA dependency).
- Subscription billing (Razorpay) and plan gating.
- Competitor/spreadsheet migration importers as a first-class feature.

## 6. Phase 3 (each item gated by its own go/no-go)

- **MCA bridge** — only if the legal opinion clears it; isolated service with degradation contract, snapshot cache, staleness indicators, and a monitoring/repair SLA. If the opinion is negative, we build "assisted manual" flows instead (deep links + paste-back parsing of user-downloaded files).
- Event wizards (~18 corporate actions) as configurations of one step-engine (Event → Category → Compliance → Meeting → Subject → Review → Documents).
- Reports hub as a metadata-driven registry.
- AI drafting assistant (BYOK) with a mandatory human-review gate before any letterhead export, and a documented statement of exactly what entity data is injected into prompts.
- Google Drive folder provisioning; Telegram notifications.

---

## 7. The Rules Engine (core intellectual property)

The compliance calendar is only as good as its rules. This is an editorial operation wrapped in code.

**Data model.**
- `compliance_rule`: rule ID, category, obligation name, form number, applicability predicate (entity attributes: company category, paid-up capital thresholds, listing status), base-date anchor (FY end / AGM date / event date / fixed calendar date), offset formula, statutory source citation.
- `rule_version`: immutable versions of each rule with effective-from / effective-to dates. Calendars reference the version, never the head.
- `rule_extension`: government extensions/relaxations, each citing the circular/notification number and date, with the FYs and entity classes it applies to.

**Process (non-negotiable).**
- A named professional at the firm owns the dataset. Every version change carries their sign-off and the source document reference.
- Monthly review cadence minimum; ad-hoc within 48 hours of any CBDT/MCA/GST circular affecting a covered obligation.
- When a rule version changes, affected calendar rows are recomputed and flagged "date revised — review," never silently rewritten. Users see what changed and why.
- The dataset ships with an audit view: every date on screen traces to rule ID → version → citation.

**Why this is the moat.** Anyone can code the offset math. Nobody else publishes dates a practicing firm signs its name to.

---

## 8. Statutory Register Integrity (architecture requirement, applies from Phase 2)

Registers under §§88, 170, 189 etc. are legal records. Therefore:
- Register entries are append-first. Edits create a new version; prior versions remain queryable.
- No hard delete anywhere in register data. "Delete" = soft delete with mandatory reason, actor, timestamp — and the row remains in the register's full history view.
- Register exports include a version/as-on-date stamp.
- Retention: register data is never purged while the entity exists in the firm's account; on entity deletion, register history is archived, not destroyed, for a configurable retention period (default 8 years).

---

## 9. RBAC Matrix (Phase 1)

| Capability | Partner | Manager | Executive | Viewer |
|---|---|---|---|---|
| Firm settings, billing, team invites | ✔ | — | — | — |
| Delete entity (soft) | ✔ | — | — | — |
| Create/edit entities & masters | ✔ | ✔ | ✔ | — |
| Edit calendar rows / mark filed | ✔ | ✔ | ✔ (assigned rows only) | — |
| Override/extend due dates | ✔ | ✔ | — | — |
| Generate documents | ✔ | ✔ | ✔ | — |
| Template management | ✔ | ✔ | — | — |
| View activity log | ✔ | ✔ | — | — |
| Read everything in scope | ✔ | ✔ | ✔ | ✔ |

Enforced server-side per endpoint. UI hiding is cosmetic, never the control.

---

## 10. Non-Functional Requirements

- **Tenant isolation**: every query filtered by `firm_id` at the repository layer; cross-tenant access attempts logged and alerting.
- **Data protection (DPDP Act, 2023)**: we are a data fiduciary for directors'/shareholders' personal data. Requirements: documented lawful basis (firm's professional engagement), encryption at rest and in transit, data-erasure workflow on firm request (subject to §8 retention for statutory records), breach-notification runbook, no personal data in logs, processor agreements with email/AI providers listed in a maintained register.
- **Availability**: calendar and reminders are deadline-critical; reminder dispatch must survive app restarts (queue-backed, not in-process timers).
- **Export fidelity**: Word/Excel exports match on-screen data exactly, stamped with generation timestamp and rule versions where dates appear.
- **Auditability**: activity log per §4.9; rules-engine trace per §7.
- **FY awareness**: every list screen filterable by FY; Indian FY (1 Apr–31 Mar) is the only FY convention in v1.

---

## 11. Open Questions

**Blocking (answer before Phase 1 code):**
1. Legal opinion on MCA terms of use for any future automated access — commission now so Phase 3 planning has an answer. *(Owner: Partner + external counsel)*
2. Final Phase 1 pricing bands and pilot invoicing terms. *(Owner: Partner)*
3. Named owner of the rules dataset and the monthly review calendar. *(Owner: Partner)*

**Non-blocking (resolve during build):**
4. Resend vs firm-SMTP as the default reminder channel for the pilot. *(Engineering)*
5. Whether Directors' Report financial figures integrate with any accounting export in Phase 2. *(Product)*
6. Trademark search and final product name. *(Owner: Partner)*

---

## 12. Timeline (Phase 1)

Target: 10–12 weeks to pilot with 3 friendly firms (including NYCA itself as firm zero — we dogfood our own portfolio first).
- Weeks 1–2: tenant shell, auth, RBAC, entity CRUD + import.
- Weeks 3–4: directors/shareholders masters; activity log.
- Weeks 5–7: rules engine + compliance calendar (ROC first, then IT, then GST).
- Weeks 8–9: reminders pipeline; document generators.
- Weeks 10–12: hardening, security review against the Engineering Charter, pilot onboarding.
Hard gate: no pilot invite goes out until the security checklist in the Claude Code instruction set passes in full. We do not repeat the TaxCompare audit findings.

---

## 13. Legal Posture

- This product is built from public statutory requirements (Companies Act 2013, IT Act, GST law) and our own practice knowledge. It is not a copy of any vendor's product. Feature research on competitors is limited to publicly available marketing material; no competitor templates, text, layouts, or branding are reproduced.
- The v1.0 document derived from live exploration of a competitor's paid product is retired and must not be circulated or committed to any repository.
- "Sachiv" and any competitor-adjacent naming are prohibited. Working codename: Praxis.
- Template content is drafted in-house from the statute and Secretarial Standards, validated per §4.7.

---

*End of PRD v2.0 — companion document: CLAUDE_CODE_INSTRUCTIONS.md*
