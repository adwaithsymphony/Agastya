# AGASTYA Feature Continuation Handover

## Source baseline
This package was built from the uploaded `Agastya(2).zip`. It intentionally excludes `.env`, `backend/agastya-dev.db`, Python virtual environments, and `node_modules` so that private settings and existing records are not replaced.

## Implemented in this continuation

### Plant Intelligence API and separate portal
- Added a separately buildable `plant-portal/` React + TypeScript + Vite application.
- Added authenticated API endpoints under `/api/v1/plant-intelligence` for crop cycles, persisted observations, care activities, combined timeline, and evidence-based recommendations.
- Reuses the existing crop-health inference workflow and displays actual existing inference history; it does not invent model results.
- The portal timeline reads active pesticide applications from AGASTYA's existing pesticide application table, without copying or changing those records.
- Added admin-managed crop-care guidance with explicit source references and bounds for soil-moisture and sunlight thresholds. Water/light recommendations only appear when both a configured threshold and a recorded measurement exist. Fertilizer and plant-health follow-up text comes only from configured guidance.
- Added `PORTAL_DIST` serving support and Vite base-path configuration for `/plant-portal/` hosting.
- Added a Windows start script: `scripts/start-plant-portal.ps1`.

### Regional languages
- Added language selector support for English, Malayalam, Tamil, Punjabi and Hindi.
- Added persistent browser preference and a `preferred_language` account field, with migration and API validation.
- Translated shared navigation, common account/notification controls, and the Plant Intelligence portal.
- **Known remaining work:** the existing feature-specific pages in the main AGASTYA app still contain English strings. The localization framework is present, but the whole main app is not yet fully translated screen-by-screen. Do not market it as complete localization until this is finished and reviewed.

### Clean-up and safety
- Removed `frontend/public/assets/README.txt` from the source package; delete the existing copy manually if it remains after overlay extraction.
- Removed the sample-account badge from the administrator user list.
- Displayed seeded product names without the development-only `Demo` prefix while retaining the safety-critical `Fictional sample, not for field use` warning.
- Kept pesticide provenance warnings, backend seed fixtures, and safety restrictions. These must not be removed because they prevent fictional label data from being mistaken for real harvest guidance.
- Existing `.env`, database, uploaded photos, model files and role/authorization rules were not modified in the supplied source baseline.

## Migration
A new Alembic migration `0002_plant_intelligence.py` follows `0001`. It adds the language preference and plant-intelligence tables. It is forward-only in normal use; it does not reset or drop existing application tables.

From PowerShell:
```powershell
cd D:\ANOMALY\Projects\Agastya-fixed\Agastya\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Local development
Start the main backend and main frontend as usual. In a third PowerShell window:
```powershell
cd D:\ANOMALY\Projects\Agastya-fixed\Agastya\plant-portal
npm.cmd install
npm.cmd run dev
```
Open `http://localhost:5174`. Sign in to AGASTYA in the same browser profile first, then refresh the portal. The Vite proxy forwards `/api` to the existing backend at `127.0.0.1:8000`.

For a same-process portal build:
```powershell
cd D:\ANOMALY\Projects\Agastya-fixed\Agastya\plant-portal
$env:VITE_PORTAL_BASE="/plant-portal/"
npm.cmd run build
```
Then configure `PORTAL_DIST=../plant-portal/dist` in the backend process environment. For separate hosting, use the default Vite base `/` and configure the portal URL in the main frontend at build time using `VITE_PLANT_INTELLIGENCE_URL`.

## Verification performed in the build workspace
- `python -m pytest tests/test_plant_intelligence.py -q`: passed (7 tests).
- Selected existing backend regression suites plus new tests: passed; two tests were skipped by the suite.
- `alembic upgrade head` against a temporary SQLite database: passed.
- TypeScript check for `frontend`: passed.
- TypeScript check for `plant-portal`: passed.
- Vite production bundle was not verified in this Linux workspace: the uploaded archive contained Windows-specific Rollup optional dependencies and the Linux Rollup package was unavailable; npm registry access was unavailable here. Run `npm.cmd ci` and `npm.cmd run build` on the target Windows environment before relying on a production bundle.
- ONNX Runtime was not installed in this verification workspace. These tests did not validate the actual ML inference engine; keep the existing installed model/runtime setup on the user's Windows machine.

## Next work required
1. Complete translations for every existing main-app screen, including forms, errors, safety warnings and admin workflows, with human review of safety-critical translations.
2. Verify the production build of both frontends on Windows.
3. Run the full backend regression suite on the actual project virtual environment with ONNX Runtime installed.
4. Browser-test the separate portal using the user's existing account, and confirm the API's cross-origin/cookie configuration for the intended deployment domain.
5. If live environmental monitoring is desired, integrate a real weather provider or sensor gateway. This version only records explicit measurements and source labels; it does not claim to have live sensors.
