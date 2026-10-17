# AGASTYA — AI-Powered Crop Lifecycle Intelligence

*Grow Smarter. Harvest Safer. Waste Less.*

AGASTYA is a decision-support platform that connects four farm workflows on one crop record:

| Module | What works today |
|---|---|
| Smart pollination | Flowering calendar, transparent provider matching, booking lifecycle (request → accept / decline / propose dates → complete / cancel) with per-day colony capacity checks |
| Crop health | Leaf-photo upload with server-side validation, **real ONNX model inference**, uncertainty / unsupported-input / failure states, agronomist review stored separately from model output, crop timeline |
| Harvest safety | Deterministic pre-harvest-interval (PHI) engine using **verified label rules only**, timezone-aware dates, multi-application logic, unverified/expired/conflicting data flagged, admin label verification, assessment history |
| Produce rerouting | Batches with traceable quantities, rule-based buyer ranking with reasons and trade-offs, transactional destination changes, assignment history, shipments, buyer cancellation, idempotent confirmation |

Five roles (farmer, pollination provider, buyer, agronomist reviewer, administrator) each have their own workspace. Authorisation is enforced on the backend for every request.

---

## Repository layout

```
backend/            FastAPI app, SQLAlchemy models, Alembic migrations, seed data, tests
  app/core/         config, db, auth/CSRF, errors, storage, audit + notifications, idempotency
  app/modules/      identity, farms, monitoring, pesticide, pollination, produce, notifications, admin, dashboard
  app/ml/           crop-vision inference service (onnxruntime)
  ml_models/        crop_vision/model.onnx + model_card.json + ood_guard.npz
  seed_assets/      PlantVillage leaf photos used by the seed (CC BY-SA 3.0)
frontend/           Main React 19 + TypeScript + Vite + Tailwind CSS v4\nplant-portal/       Separately buildable Plant Intelligence monitoring portal
e2e/                Playwright end-to-end tests that drive the real UI
ml_training/        Reproducible scripts that built the crop-vision model
AGASTYA_PRD.md  ARCHITECTURE.md  DESIGN_SYSTEM.md  MODEL_CARDS.md  IMPLEMENTATION_PLAN.md
```

## Prerequisites

- Python 3.11 – 3.13
- Node.js 20+ and npm
- PostgreSQL 14+ (or `docker compose up -d` using the included `docker-compose.yml`). SQLite works for a quick look but PostgreSQL is the supported database.

## Windows quick start (recommended)

Use Python 3.11, 3.12, or 3.13, Node.js 20+, and PostgreSQL 14+ (Docker Desktop is supported). From PowerShell:

```powershell
cd D:\ANOMALY\Projects\Agastya
.\scripts\setup-windows.ps1
```

The script creates a backend virtual environment, installs the declared dependencies, applies migrations, runs read-only diagnostics, and seeds sample records **only if the database has no users**. It does not run `--reset` or drop existing records. If setup stops, fix the printed diagnostic before starting the app.

Start the backend and frontend in two separate PowerShell windows:

```powershell
.\scripts\start-backend.ps1
```

```powershell
.\scripts\start-frontend.ps1
```

Then open `http://localhost:5173`. Backend health diagnostics are available at `http://localhost:8000/api/health`; run `python -m app.doctor` from `backend` for a detailed local check.

### Login returns HTTP 500 (root cause and fix)

The 500 came from the database layer, not from authentication: on a database where `alembic upgrade head` had not been run, the first query in `/auth/login` raised PostgreSQL's *undefined table* error (a SQLAlchemy `ProgrammingError`), which had no handler and fell through to the generic 500. Database errors now return 503 with a specific code (`database_schema_error`, `service_unavailable`, `database_error`); in development the message includes the setup step, in production it is a neutral "temporarily unavailable". `/api/health` reports whether the database is reachable and migrated, and the sign-in page shows a notice when it is not. Windows also needs the `tzdata` package (now in `requirements.txt`) because farm-local dates use the IANA time-zone database, which Windows does not ship.

If you still see a failure:

1. Check `http://localhost:8000/api/health`. If `database.available` is false, verify PostgreSQL is running and `DATABASE_URL` in the root `.env` matches the database credentials.
2. If `database.schema_ready` is false or `missing_tables` is non-empty, run `alembic upgrade head` from `backend`.
3. Run `python -m app.doctor` from `backend`. If it reports zero sample accounts and this is a fresh development database, run `python -m app.seed` (without `--reset`).
4. Reproduce login and inspect the backend terminal for the full exception. Never paste `.env` secrets or session cookies into bug reports.

`python -m app.seed --reset` is destructive: it drops and recreates the schema and removes locally stored observation uploads. Use it only for a disposable development database.

## 1. Configure

```bash
cp .env.example .env        # Windows: copy .env.example .env
```
Set `SECRET_KEY` to a long random value and `DATABASE_URL` to your database.

## 2. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head                 # create the schema
python -m app.seed                   # load sample data into an empty database (add --reset only for a disposable one)
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/api/docs

## 3. Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to :8000)
```
Production build: `npm run build` → `frontend/dist`. To serve it from the API process instead of Vite, set `FRONTEND_DIST=../frontend/dist` before starting uvicorn.

## Sample accounts (development only)

`python -m app.seed` creates fictional sample accounts that all use the development password `agastya-demo`. They are documented here only: the sign-in page never lists accounts or shows a password, and the seed refuses to run when `APP_ENV=production`. Change or remove these accounts before exposing an instance to anyone else.

| Role | Email |
|---|---|
| Farmer | ramesh@agastya.demo (second farm org: sunita@agastya.demo) |
| Pollination provider | anil@agastya.demo |
| Buyer | imran@agastya.demo |
| Agronomist | asha@agastya.demo |
| Administrator | admin@agastya.demo |

Seed dates are relative to today (or `DEMO_DATE`), so the demo never goes stale. Organisations and people are fictional. **Pesticide products and label rules in the seed are fictional samples** ("Demo …" products, source `DEMO-LBL-…`). Every screen that shows them, and every harvest calculation that uses them, carries the marker *Fictional sample, not for field use* — including after an administrator marks a rule verified for testing.

## Tests

```bash
cd backend
pytest                                    # SQLite, no setup needed
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/agastya_test pytest   # PostgreSQL (recommended; also runs the concurrency test)
```

### End-to-end tests

```bash
cd frontend && npm run build
cd ../backend && python -m app.seed --reset
FRONTEND_DIST=../frontend/dist uvicorn app.main:app --port 8000
# in another terminal
python -m playwright install chromium
pytest ../e2e -q
```
The e2e suite walks the full workflow: login validation, leaf upload with a real model result, spray record and PHI recalculation (including a refused batch inside the PHI), pollination request accepted from the provider workspace, buyer cancellation → farmer reroute → confirmed destination that survives reload, cross-role rejection by the backend, reviewer correction, and admin label verification.

## Walkthrough with the sample data

1. Sign in as **Farmer** (accounts in the table above). The overview lists what needs attention: TOM-A2 needs a buyer after a cancellation, a capsicum spray with unverified label data, mustard flowering without a booking, an uncertain leaf result.
2. **Crop health** → choose *Tomato*, upload a leaf photo → the model's reading and confidence appear; open the observation.
3. **Harvest safety** → *Tomato* is restricted; record a spray and see the eligibility date recalculated. Try *Produce & buyers → Record batch* for today: it is refused inside the PHI.
4. **Pollination** → *Mustard* → enter colonies → request Madhuban Apiaries. Sign in as **Pollination provider** → *Bookings* → accept.
5. Sign in as **Buyer** → *Deliveries* → cancel TOM-A1. Sign back in as **Farmer** → open TOM-A1 → *Find buyers* → choose → confirm. The shipment, history and notifications update; reload to see it persisted.
6. Sign in as **Agronomist** → review the uncertain observation. Sign in as **Administrator** → *Reference data* → verify the capsicum label rule; the capsicum warning disappears for the farmer.

## Model

`backend/ml_models/crop_vision/` contains a genuine, evaluated model (EfficientNet-B0 ImageNet backbone + linear head trained on PlantVillage, 97.3 % accuracy on a held-out PlantVillage test split). It is a lab-image model; field accuracy is not established. See `MODEL_CARDS.md`. If the files are removed, uploads still save and are marked "analysis unavailable" — no result is ever invented. Re-analyse once the model is restored.

## Status and known limitations

Completed: everything in the table above, role workspaces, notifications, audit log, admin user/role and reference-data management, 73 backend tests, 8 end-to-end tests.

Not implemented / optional:
- OCR for pesticide labels (labels are entered manually and always need verification).
- S3 storage adapter is written but untested against a live bucket.
- Email/SMS notification delivery (notifications are in-app).
- Buyer "purchase requests" on available batches (buyers see matching produce; farmers assign).
- No live logistics, market price or weather integrations — none are faked.
- Landing-page video: add a licensed clip at `frontend/public/assets/hero.mp4`; until then a photograph (loaded from Unsplash) is shown, with a plain colour fallback if offline.
- The official logo goes at `frontend/public/assets/agastya-logo.svg`; a neutral placeholder is shown until then.

Basic safeguards are in place (scrypt password hashing, httpOnly session cookie, CSRF double-submit, ownership checks, upload validation, audit trail); this is not a security certification.

## Licences and attribution

- PlantVillage dataset © Mohanty, Hughes & Salathé, CC BY-SA 3.0 (training data and seed photos).
- EfficientNet-B0 weights from lukemelas/EfficientNet-PyTorch (Apache-2.0).
- Icons: Lucide (ISC). Font: Manrope (SIL OFL).
