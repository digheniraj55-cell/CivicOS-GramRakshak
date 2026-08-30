# CivicOS Unified Merge Notes — 30 Aug 2026

## Source builds
- Email/OTP + citizen identity + worker authentication/governance build
- Fixed functional asset/contractor/procurement/finance/blackout-recovery build

## Merge strategy
The operations/asset build was used as the structural base. Newer citizen identity, OTP/email, worker-only execution, completion verification, resolution review, accountability and Civic Voice logic was merged into the shared Flask routes and templates.

## Important resolved conflicts
- Preserved recovery-aware `db()` while adding citizen/worker/accountability tables.
- Unified the `complaints` schema so both `asset_id` and citizen-resolution verification fields exist.
- Retained finance, procurement and contractor initializers.
- Retained asset seed/maintenance data and public asset pages.
- Added verified citizen reporting and asset-linked complaint creation in the same `/report` route.
- Retained strict worker login and worker-owned update permissions.
- Retained admin verification before final resolution.
- Combined admin navigation for Assets, Contractors, Procurement, Finance, Recovery, Verification and Accountability.
- Combined public navigation for Civic Accounts, Worker Login, Civic Intelligence and Public Assets.
- Combined asset CSS with citizen/worker/accountability/OTP CSS.
- Preserved English/Marathi asset translations and added the new Awaiting Admin Verification status.
- Added `/admin/assets/qr/<asset_uid>` because the supplied asset templates referenced a missing endpoint.

## Validation performed
- Python AST parse: passed.
- Python `py_compile`: passed for all project Python modules.
- Jinja template syntax parse: passed for every HTML template.
- Template `url_for()` endpoint scan: no missing endpoints.
- Route union check: all routes from both source builds are present.
- Fresh SQLite schema simulation: all citizen, worker, complaint, asset, contractor, procurement, finance and recovery tables created.
- Fresh asset seed created successfully.
- Fresh worker account seed created successfully.
- Asset-linked citizen complaint simulation successfully stored `complaints.asset_id`.

## Run
1. Extract the ZIP.
2. Open the project folder in VS Code.
3. Install `requirements.txt`.
4. Configure SMTP if you want real citizen OTP/email delivery.
5. Run `START_CIVICOS.bat` or `py app.py`.
