# M15 — Debt closure: masters import/export + mypy --strict

Date: 12 July 2026
Backend suite: **148 passed** (146 → 148). Ruff clean. **mypy --strict: 0
errors across 67 source files** — charter §9 is now fully met.

## 1. Directors & shareholders Excel import/export (the PRD §4.3/4.4 remnant)

The last unfinished Phase 1 P0 sub-item — companies got Excel import in M3;
directors and shareholders were specified to have it too and never did.

- Same all-or-nothing contract: any row error → 422 with row/column/error
  triples and NOTHING imports (a bad DIN poisons the file — tested).
- Idempotent re-import by identity (DIN+name for directors, folio+name for
  shareholders) — duplicates are counted as `skipped`, never re-created.
- Template download + export round-trip per master; per-row audit entries.
- Routes are LITERAL per master (`/directors/import`, `/shareholders/...`).
  The first cut used a generic `/{master}` segment, which silently shadowed
  sibling literal routes (`/calendar/export` started 404ing) — caught by
  the existing calendar test suite. Recorded as a route-design rule:
  **never put a catch-all segment on a shared prefix.**

## 2. mypy --strict (charter §9, deferred since M1)

110 errors → 0, no blanket ignores:
- one targeted override for `openpyxl`/`docxtpl` (no stubs published);
- one documented `type: ignore[call-arg]` where pydantic-settings fills
  required kwargs from the environment (C8's design);
- everything else properly typed: middleware `call_next` signatures, typed
  cookie kwargs (the `**dict` pattern was hiding a real Literal type),
  Redis return narrowing, `require_role`'s dependency type, worker
  `dispatch_id` now converted to UUID at the boundary (a genuine latent
  type mismatch found by the checker).
- CI now runs `mypy --strict app` on every push, alongside ruff.

## NOT covered / follow-ups

- Frontend UI buttons for the new per-master import/export (API + tests
  complete; the company detail tabs need the same upload/download controls
  the companies list has — small UI pass).
- `tests/` are not under mypy (app-only, matching the charter's wording).
