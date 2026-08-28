# CivicOS + GramRakshak — Integrated Hackathon Build

CivicOS extends the existing GramRakshak citizen complaint foundation into a local-government operations layer for citizens, departments, field teams and command-center analytics.

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
- **Safer uploads:** complaint evidence accepts PNG/JPG/JPEG/WEBP with an 8 MB request limit.
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

For a deployment/final demo, set your own credentials with environment variables instead of using the demo password.

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
- `/workers` — Worker Operations Center
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

For a production government deployment, replace name+phone recovery with OTP verification before exposing sensitive complaint details.

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

Before real citizen use, add OTP-based identity verification, CSRF protection, rate limiting, role-specific authentication for workers/departments, managed database storage, backups, HTTPS, audit logging and a production WSGI server. These are deployment/security steps rather than hackathon-only UI features.

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
- `/workers` and `/worker/<worker-id>` can be opened without the authority/admin login for hackathon worker demos. Worker updates are limited to the task assigned to that worker dashboard. Set `CIVICOS_DEMO_WORKER_ACCESS=0` when real worker authentication is introduced.
- Small admin labels, tables, status text, alerts, worker cards and supporting text were raised to more readable sizes without making the dashboard oversized.
