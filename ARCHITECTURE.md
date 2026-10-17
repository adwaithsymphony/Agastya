# Architecture

```
Browser (React SPA)  ──/api/v1──▶  FastAPI (single process, modular monolith)
   cookie session + CSRF header         ├─ core: config, db, auth deps, CSRF, errors, storage, events, idempotency
                                        ├─ modules/<domain>: models · service · router
                                        ├─ ml/crop_vision: onnxruntime inference (isolated)
                                        └─ PostgreSQL (SQLAlchemy 2, Alembic)   ·   private image storage (local / S3)
```

## Backend modules
| Module | Tables | Notes |
|---|---|---|
| identity | organizations, users | role column; `token_version` invalidates sessions on role/password change |
| farms | crop_references, farms, fields, crop_cycles, growth_stage_records | ownership via organisation |
| monitoring | uploaded_images, crop_observations, model_predictions, human_reviews, model_registry | predictions never overwritten; reviews separate |
| pesticide | pesticide_products, product_labels, pesticide_applications, harvest_assessments | `engine.py` is pure and unit-tested |
| pollination | pollination_providers, provider_crops, provider_service_areas, provider_availability, pollination_bookings, pollination_booking_events | optimistic version column on bookings |
| produce | buyer_profiles, buyer_demands, produce_batches, reroute_runs, buyer_matches, batch_assignments, shipments, shipment_events | partial unique index: one active assignment per batch |
| notifications / audit | notifications, audit_events, idempotency_records | written in the same transaction as the change |

## Key decisions
- **Auth**: HS256 JWT in an httpOnly SameSite=Lax cookie; double-submit CSRF token for unsafe methods; scrypt password hashing (stdlib). Every protected lookup goes through ownership helpers that return 404 for other organisations' records.
- **Safety engine** (`modules/pesticide/engine.py`): deterministic, versioned (`phi-1`), uses only verified label rules valid on the application's local date; most restrictive date governs; conflicts/missing/expired → unresolved. Snapshots are stored when the result changes.
- **Inference isolation**: `app/ml/crop_vision.py` returns a structured result or an explicit failure; business rules (review queueing, notifications) live in `monitoring/service.py`. An out-of-distribution guard rejects images unlike single-leaf photos.
- **Rerouting integrity**: confirmation locks the batch row (`FOR UPDATE OF`), checks the version and that the recommendation run is the latest, re-validates the buyer's hard constraints against current demand, then supersedes/creates assignments and shipments in one transaction. `Idempotency-Key` makes retries safe.
- **Capacity**: per-day committed colonies vs. availability windows; accepting locks the provider row.
- **Time**: all timestamps stored UTC (`UTCDateTime`), business dates computed in the farm's time zone; `core/clock.py` allows freezing time in tests.
- **Storage**: server-generated keys, path-traversal guarded, files served only through authorised endpoints; uploads are re-encoded (strips EXIF/GPS and trailing payloads).

## API
Versioned under `/api/v1`, documented at `/api/docs`. Errors use `{"error": {"code", "message", "details"}}`. Growing collections are paginated (`page`, `page_size`).

## Frontend
React 19 + TypeScript, Tailwind v4 tokens in `src/index.css`. A small router (`lib/router.tsx`) and data hooks (`lib/data.ts`, cache + prefix invalidation) keep runtime dependencies to React only. Role-aware navigation is a convenience; the backend enforces access.

## Retention
Images carry `retain_until` (default 730 days, `IMAGE_RETENTION_DAYS`); predictions, reviews and audit events are retained with the observation. A purge job is not yet implemented.
