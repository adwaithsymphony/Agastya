# Implementation plan and status

| Phase | Status |
|---|---|
| 1. Inspect and plan — empty repository; stack chosen per brief; docs written | Done |
| 2. Foundation — FastAPI, SQLAlchemy, Alembic, auth/RBAC/CSRF, design tokens, shell, landing, dashboards, seed | Done |
| 3. Core business logic — PHI engine, pollination lifecycle and capacity, batch integrity | Done, unit + API tested |
| 4. Model integration — EfficientNet-B0 + PlantVillage head, ONNX, OOD guard, registry, failure states | Done, evaluated |
| 5. Full workflows — role workspaces, rerouting, notifications, timelines, reviewer and admin tools | Done |
| 6. Verification — backend tests (SQLite + PostgreSQL), Playwright e2e, screen review desktop and mobile | Done |

## Next steps
1. Field-photo evaluation set for Indian conditions; retrain or fine-tune before any field claims.
2. OCR-assisted label entry (output stays unverified until an admin verifies).
3. Image retention purge job; S3 adapter integration test.
4. SMS / WhatsApp delivery of critical notifications.
5. Buyer-initiated purchase requests on matching batches.
6. Frontend component tests (Vitest) alongside the e2e suite.
