# CivicOS Project Audit & Fixes

This build was reviewed as an integrated hackathon system rather than as isolated pages.

## Functional / data integrity fixes
- Preserved the database-level unique index enforcing **one unresolved task per field team**.
- Reserve Capacity Guard now applies to automatic first assignment, automatic next-task pull, and routine manual authority assignment unless an explicit authority override is selected.
- Admin and worker resolution now require after-work proof.
- Existing resolved records are re-evaluated through the proof engine and existing complaints receive current impact scores.
- Disaster Operations Mode protects additional capacity for non-critical automatic work.
- Cross-department sweep missions are persisted in SQLite and reflected in complaint timelines.

## Location fixes
- Removed hard-coded city labels, including the fallback-map locality label.
- Added best-fix GPS capture using a short `watchPosition` window so CivicOS keeps the most accurate reading rather than the first coarse fix.
- Reverse geocoding runs through CivicOS server endpoints.
- Exact coordinates and GPS accuracy are shown before citizen confirmation.
- Search-address and exact map-pin fallbacks remain available when browser GPS is blocked.

## Reliability fixes
- Added a real `.env` loader without an extra dependency, so `python app.py` respects local `.env` configuration.
- Evidence uploads are content-verified with Pillow, limited to supported image formats/dimensions, and the mobile-friendly request limit is 16 MB.
- Added safer session-cookie defaults (`HttpOnly`, `SameSite=Lax`) and an HTTPS secure-cookie toggle.
- Main charts and maps already include offline-safe fallbacks when external CDN/map tiles are unavailable.
- Removed a misleading “SMS” quick-action label where the hackathon build actually creates in-app citizen alerts.
- Added `PRE_HACKATHON_CHECK.bat` and `tools/preflight.py`.
- Added a protected demo database seed and `RESET_DEMO_DATA.bat` so the team can restore the judging demo after rehearsals.

## Static validation performed
- Python AST / bytecode compilation.
- Jinja syntax parsing across all templates.
- `url_for(...)` endpoint reference audit.
- JavaScript syntax check for the main app file and rendered Report/SOS inline scripts.
- SQLite `PRAGMA integrity_check`.
- Database query for any worker holding more than one active unresolved complaint.
- Intelligence-engine smoke tests against the bundled demo database.

## Known environment boundary
A full Flask browser session cannot be launched inside the packaging environment because Flask packages cannot be downloaded there. The final project includes exact pinned runtime requirements and a preflight script for the hackathon machine. Browser GPS on a phone still requires HTTPS (or localhost on the same device); a Flask app cannot bypass the browser’s secure-context policy.
