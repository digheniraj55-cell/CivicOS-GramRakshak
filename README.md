# CivicOS — Unified Hackathon Build (Merged 30 Aug 2026)

This folder merges the **Email/OTP + citizen/worker governance build** with the **asset-management + contractor + procurement + finance + blackout-recovery build** into one Flask application. The shared routes, templates, database migrations and navigation have been reconciled so the feature sets coexist instead of overwriting each other.

## What is included

### GramRakshak foundation retained
1. Citizen complaint portal
2. Emergency / SOS
3. Location + photo evidence
4. Complaint tracking
5. Department dashboards
6. Before / after proof
7. Feedback and upvotes

### CivicOS layer retained and integrated
8. Smart Department Routing
9. Worker Assignment and Worker Dashboard
10. SLA + Automatic Escalation
11. Civic Intelligence Map
12. Ward Analytics
13. Department Performance
14. Government Command Center

### Additional merged modules
- Citizen Civic Account with **email OTP verification**
- Separate **Worker Login** and worker-only task update endpoint
- Authority **completion verification queue** before a worker completion becomes Resolved
- Resolution email + citizen satisfaction/reopen workflow
- Verified one-person-one-upvote participation
- Public Civic Intelligence and nearby civic activity
- Civic Voice complaint dictation
- Public/admin accountability workflow and audit log
- Government asset registry, asset health/maintenance, public asset view and complaint-to-asset linking
- Contractor and contract/payment/compliance management
- Procurement, inventory, purchase orders and stock movement
- Finance budgets, transactions, vendors and audit logs
- Blackout/recovery snapshot and integrity workflow


### Reliability additions in this build
- **One active task per field team** at both application and SQLite database level.
- **Automatic priority queue:** when a worker resolves a task, CivicOS assigns that worker the next suitable queued complaint.
- **Complaint ID recovery** using the same citizen name + phone number used while reporting, plus recent complaint IDs remembered on the same browser session.
- **Citizen notification center** for registration, assignment, status, evidence and SLA/escalation updates.
- **Browser update alerts** from the tracking page using the browser Notification API.
- **Optional email notifications** when SMTP environment variables are configured.
- **Optional OpenAI-assisted routing** when `OPENAI_API_KEY` is present; the project always has a local rule-based fallback and does not depend on an AI API to work.
- **Location confirmation fallback:** GPS coordinates can still be confirmed if reverse geocoding is temporarily unavailable.
- **Improved responsive UI** inspired by the supplied CivicOS design, with desktop/tablet/mobile navigation and layouts.
- **Safer uploads:** complaint evidence accepts PNG/JPG/JPEG/WEBP with a 16 MB request limit.
- **Hashed authority passwords** for new databases; an older plaintext demo password is automatically upgraded after a successful login.
- **Configuration separated** in `civicos_config.py` so departments, workers, skills and routing keywords can be changed without digging through route logic.

## Quick start on Windows

1. Extract this ZIP into a normal folder. Do **not** keep editing files inside the ZIP preview.
2. Open the extracted folder in VS Code.
3. Double-click `START_CIVICOS.bat`, or run the commands below in the VS Code terminal.

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
py app.py
```

Open `http://127.0.0.1:5000/` in the browser.

### Demo authority login
- Username: `admin`
- Password: `admin123`

### Demo worker login
Worker usernames are generated from the configured worker ID by removing punctuation and lowercasing it. Example: `WTR-01` → `wtr01`.
- Default worker password: `worker123`
- Change it with `CIVICOS_WORKER_DEFAULT_PASSWORD` before the database seeds worker accounts.

### Citizen login
Citizens create an account with email and verify a 6-digit OTP. Configure SMTP in `.env` or from **Admin → Settings → Email & OTP Setup**.

For a deployment/final demo, replace all demo credentials and secrets.

## Main URLs

- `/` — Citizen home
- `/report` — Report an issue
- `/track` — Track a complaint
- `/find-complaint` — Recover a forgotten complaint ID
- `/notifications` — Citizen update center
- `/sos` — Emergency/SOS
- `/transparency` — Public transparency board
- `/login` — Authority login
- `/admin` — Government Command Center
- `/worker/login` — Worker login
- `/worker/portal` — authenticated worker dashboard
- `/workers` — admin Worker Operations Center
- `/assets` — public municipal assets and amenities
- `/admin/assets` — government asset management
- `/admin/contractors` — contractor operations
- `/admin/procurement` — procurement and inventory
- `/admin/finance` — finance workspace
- `/admin/recovery` — blackout/recovery workspace
- `/admin/verification` — completion verification queue
- `/admin/accountability` — authority accountability moderation
- `/department/<department>` — Department dashboards

## One-task worker policy

A field team can hold **only one unresolved complaint at a time**.

The rule is enforced twice:
1. Business logic refuses a second active assignment.
2. SQLite creates the partial unique index `ux_worker_one_active_task`, so even an accidental code path cannot give one worker two unresolved tasks.

If all suitable teams are busy, the complaint remains `Pending` in a priority queue. As soon as a team resolves/frees its current task, CivicOS automatically pulls the next queued complaint for that department.

## Complaint ID recovery

Normal citizen reports require:
- Citizen name
- Phone number
- Optional email

If the citizen loses the complaint ID, `/find-complaint` matches the same name and normalized phone number and returns their recent complaints. The browser session also remembers a short list of complaint IDs created on that device.

Citizen reporting now requires a verified Civic Account email OTP. The legacy complaint-ID recovery page is retained for convenience; for a real government deployment, add OTP confirmation to that recovery lookup as well.

## Notifications

CivicOS stores citizen-facing notifications in SQLite when meaningful updates happen, including:
- complaint registered
- worker assigned / queued
- authority status changes
- field-team updates
- after-photo proof uploads
- automatic SLA escalation

The tracking page can poll for updates and show a browser notification after the citizen enables browser alerts.

### Optional email notifications

Copy `.env.example` values into your deployment environment and configure SMTP:

```text
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=...
SMTP_USE_TLS=1
```

No SMTP configuration is required for the core app; in-app/browser notifications continue to work.

## Optional AI routing

Without an API key, CivicOS uses deterministic local routing rules. This is deliberate so the hackathon demo does not fail because of internet/API issues.

To enable AI-assisted classification, set:

```text
OPENAI_API_KEY=...
CIVICOS_AI_MODEL=gpt-4.1-mini
```

If the API request fails or returns invalid data, CivicOS falls back to the local routing engine automatically.

## Files you will most often edit later

- `civicos_config.py` — departments, field teams, skills, routing keywords, statuses
- `translations.py` — English/Marathi translation dictionary
- `templates/` — page structure
- `static/style.css` — visual design and responsive behavior
- `static/app.js` — maps, charts, theme, mobile navigation and live tracking behavior
- `app.py` — Flask routes, business logic, database migrations and workflow logic

## Important demo notes

- Browser notification permission works best on `localhost` or HTTPS deployments.
- The Civic Intelligence Map uses Leaflet/OpenStreetMap when available and includes UI fallbacks for weak connectivity.
- Reverse geocoding uses OpenStreetMap Nominatim; coordinate confirmation still works if the reverse-geocoding request fails.
- `civicos.db` contains demo data. Delete the database only if you intentionally want a fresh database; `app.py` will recreate the schema.
- Uploaded evidence is kept in `static/uploads/`.

## Production hardening after the hackathon

Before real citizen use, add CSRF protection, rate limiting, managed database storage, HTTPS, stronger credential lifecycle/reset flows, stricter authorization reviews, production-grade email delivery, secrets management, backup retention and a production WSGI server. Citizen OTP, worker/admin role separation and audit logging are already present in this merged hackathon build.

## 2026-08-28 Command Center UI upgrade

The admin experience is now split into real page-level workspaces instead of sidebar anchor jumps. The reference-style sidebar opens dedicated URLs:

- `/admin` — Command Center
- `/admin/dashboard` — operational dashboard
- `/admin/complaints` — searchable/filterable complaint queue
- `/admin/departments` — department comparison
- `/admin/workers` — field-team availability and one-task status
- `/admin/analytics` — complaint, ward and department analytics
- `/admin/sla` — SLA breaches and due-soon cases
- `/admin/feedback` — citizen feedback
- `/admin/reports` — reporting/export workspace
- `/admin/transparency` — authority transparency preview
- `/admin/settings` — Command Center location/settings
- `/admin/announcements` — announcement publishing
- `/admin/alerts` — authority notification broadcast to active complaint records
- `/admin/emergency` — dedicated SOS queue
- `/admin/export` — complaint CSV export

### Location reliability on laptops and phones

A browser may expose `navigator.geolocation` but still refuse precise GPS when CivicOS is opened over plain HTTP using a LAN IP such as `http://10.x.x.x:5000`. Modern browsers generally reserve geolocation for secure contexts (HTTPS) except localhost.

This build therefore uses a layered location flow on both **Report Issue** and **SOS**:

1. Browser GPS when the page is allowed to use it.
2. CivicOS server-side reverse-geocoding proxy to avoid client-side cross-origin failures.
3. Search-address fallback through `/api/geocode`.
4. Click/tap-on-map selection so a laptop or phone can still place an exact complaint pin during a local-network demo.
5. Explicit citizen confirmation before coordinates are submitted.

For a final hosted demo, use HTTPS so native browser GPS works directly on phones.

## 2026-08-28 live-location + readability refinement

This build keeps the existing UI structure and functionality, but improves the parts that were hard to read or confusing during demos:

- The Command Center no longer shows a hard-coded **Pimpri Chinchwad** label. The top location pill now tries to use the current device location, reverse-geocodes it, remembers the latest confirmed device location, and can center the Civic Intelligence Map on that point.
- When CivicOS is opened on the same laptop, use the launcher-provided `http://127.0.0.1:5000/` URL. Localhost is treated as a trustworthy browser context and gives the best chance of automatic browser geolocation permission.
- On plain HTTP LAN addresses used by phones/tablets, browsers may block automatic GPS. CivicOS therefore remembers the last confirmed location and keeps exact map-pin/search selection available instead of silently falling back to a fake city.
- Report Issue now shows the exact saved latitude/longitude, GPS accuracy, and a dedicated map preview of the precise complaint pin before confirmation.
- Worker task execution now requires the separate `/worker/login` session. Admin users can inspect worker performance from the Worker Center but cannot submit field updates through the worker endpoint.
- Small admin labels, tables, status text, alerts, worker cards and supporting text were raised to more readable sizes without making the dashboard oversized.

## 2026-08-29 Top-Tier Civic Intelligence upgrade

The project now adds a decision-and-prevention layer on top of the complete CivicOS operational workflow. See `TOP_TIER_FEATURES.md` for details.

New hackathon workspaces and engines include:
- Civic Memory + probable root-cause / causal clustering.
- Civic Blind-Spot Radar.
- 7-day Civic Risk Forecast.
- Digital Twin Lite / cost-and-danger-of-waiting simulation.
- Public Value Optimizer under budget, worker, vehicle and time constraints.
- Service Equity pressure using operational outcomes only (no demographic profiling).
- Chronic Failure Intelligence + Civic Debt.
- Proof-of-Resolution image/evidence checks + citizen confirmation.
- Complaint → Policy Intelligence.
- Civic Cascade Engine and Civic Health Index.
- Cross-Department Sweep missions.
- “One Trip, Multiple Problems” inspection batching.
- Reserve Capacity Guard — routine work should not consume the final protected response team.
- Disaster Operations Mode for more conservative non-critical allocation during surge conditions.

### New admin URLs
- `/admin/intelligence` — municipal intelligence workspace.
- `/admin/intelligence/optimizer` — constrained public-value planning.
- `/admin/intelligence/sweeps` — cross-department sweep planning.
- `/admin/emergency` — SOS queue + Disaster Operations controls.

### Demo reliability tools
- `PRE_HACKATHON_CHECK.bat` — validates Python, templates, JavaScript, SQLite and worker assignment invariants.
- `RESET_DEMO_DATA.bat` — restores the bundled judging dataset after rehearsals while saving a backup of the current DB.
- `HACKATHON_DEMO_SCRIPT.md` — 5-minute judge flow.
- `PROJECT_AUDIT_AND_FIXES.md` — audit/fix record.
- `LOCATION_GUIDE.md` — exact GPS/map behaviour and browser security limitations.
- `demo_media/` — 4K CivicOS presentation assets that are not loaded by the live site.

### Run the pre-demo check
After dependencies are installed:

```bat
PRE_HACKATHON_CHECK.bat
```

or:

```bash
python tools/preflight.py
```

The intelligence scores in this hackathon build are transparent prototype decision-support heuristics. They demonstrate the architecture and workflow; they should be calibrated and validated with real municipal GIS, asset, service-cost, weather and repair-outcome data before operational government use.

- `/admin/recovery` — Live Blackout Recovery / Resilience Control Room

### Released Challenge: The Blackout

CivicOS now includes a working resilience layer for the primary SQLite store. A separate `civicos_recovery.db` snapshot is refreshed after successful requests. Before database access, CivicOS validates the primary store; if it is missing or corrupted, the last known-good snapshot is restored automatically. Damaged primary files are quarantined under `recovery_incidents/` for evidence.

For the live judge demo, sign in as the authority admin, open **Blackout Recovery**, and click **Simulate Live Blackout**. The simulator intentionally corrupts the real primary database, triggers the same self-healing path used for accidental corruption, verifies SQLite integrity and record counts, logs the incident, and returns the system to normal operation.

## 2026-08-30 Challenge 2 — Civic Trust & Verification Layer

The merged build now also addresses the false-information / coordinated-fake-submission challenge without turning CivicOS into a simplistic “AI says true/false” tool.

### New public flow
- `/trust` — paste a WhatsApp/social claim and compare it with published authority bulletins.
- `/trust/report` — send an unmatched rumor to the authority Trust Queue as **Unverified**.
- `/truth/<id>` — shareable authority correction with verdict, context, source and WhatsApp/copy actions.
- `/api/trust/check` — JSON claim-check endpoint for future integrations.

### New authority flow
- `/admin/trust` — Civic Trust & Verification Center.
- Publish official corrections/advisories with a source-backed verdict.
- Review unknown rumors without automatically treating them as fact.
- Inspect explainable complaint-integrity scores and similarity signals.
- Quarantine suspected coordinated abuse from public feeds while preserving service processing and the full audit trail.
- Run the safe in-memory **Coordination Attack Simulation** for a judge demo without changing real complaint data.

### Core principle
A verified Civic Account proves identity/account control; it does **not** prove the user's statement is factual. CivicOS therefore separates **identity verification** from **information verification**.

See `CHALLENGE_2_TRUST_INTEGRATION.md` for the complete architecture and a 90-second judge walkthrough.
