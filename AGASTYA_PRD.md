# AGASTYA — Product requirements (v1)

## Problem
Smallholder and mid-size farms make four connected decisions with disconnected information: when and from whom to rent pollinators, whether a leaf problem needs attention, when sprayed produce can be harvested, and where produce goes when a buyer pulls out. Mistakes cost yield, safety and wasted produce.

## Users
| Role | Primary job |
|---|---|
| Farmer | Manage farms, fields and crop cycles; record observations and sprays; book pollination; sell batches |
| Pollination provider | Publish crops, districts, colony availability; answer and complete bookings |
| Buyer | Post demand; receive, confirm or cancel deliveries |
| Agronomist reviewer | Review model results that are uncertain, unsupported or show a condition |
| Administrator | Users and roles, crop and pesticide reference data, label verification, model health, audit |

## Principles
1. Every recommendation leads to an action; every confirmed action persists.
2. Model outputs come from real inference and are visibly separate from rules, user data and reviews.
3. Safety status comes only from verified reference data; missing data is shown as unknown, never filled in.
4. Nothing external is faked: no invented prices, distances, sensor data or availability.

## Scope v1 (built)
- Pollination: flowering calendar, provider matching with reasons/exclusions, booking lifecycle, capacity, conflict checks.
- Crop health: validated upload, ONNX inference, statuses (completed / uncertain / unsupported_input / failed), review, timeline.
- Harvest safety: application records (void, never delete), PHI engine, label submission → admin verification, assessment history, batch creation blocked inside PHI.
- Rerouting: batches, buyer demand, ranked matches, confirmation with locking + idempotency, history, shipments, buyer cancellation.
- Shared: role dashboards from live records, notifications from events, audit log.

## Out of scope v1
OCR, SMS/email delivery, live logistics/market feeds, demand forecasting or spoilage ML (no suitable dataset), payments.

## Success criteria
The end-to-end demo in README runs without manual fixes; backend and e2e suites pass; no screen shows fabricated data.
