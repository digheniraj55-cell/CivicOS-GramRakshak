# CivicOS Role & Email Validation — 29 Aug 2026

## Static/project checks

- PASS: Python source syntax
- PASS: 41 Jinja templates parsed
- PASS: JavaScript syntax
- PASS: SQLite integrity
- PASS: one-active-task-per-team policy
- PASS: `/workers` authority-only
- PASS: `/worker/<worker_id>` authority-only
- PASS: `/worker/portal` protected by worker authentication
- PASS: Authority login restricted to `role='admin'`
- PASS: old unauthenticated worker demo bypass removed
- PASS: worker update ownership check present
- PASS: citizen email verification email path present
- PASS: authority-approved resolution email path present
- PASS: email delivery audit table and Settings UI present

## Role behavior implemented

- Admin: Command Center, Worker Center, any worker inspection dashboard, verification queue.
- Worker: dedicated Worker Login -> own Worker Portal only.
- Citizen: Civic Account routes; cannot use worker/admin sessions.
- Guest: may open login pages and SOS, but cannot enter protected worker/admin portals without credentials.

## Demo worker credentials

At first startup CivicOS seeds worker users from `civicos_config.py`.

- Username: worker ID lowercased with punctuation removed, e.g. `WTR-01 -> wtr01`
- Initial hackathon password: `worker123`
- Override before first seed with `CIVICOS_WORKER_DEFAULT_PASSWORD`.

## Gmail/email verification flow

- Local citizen registration -> signed 24h email verification link.
- Admin Settings -> Verify Gmail & Send Test performs a real SMTP delivery attempt.
- Worker completion -> Awaiting Admin Verification; no resolution email yet.
- Admin approval -> signed 14-day resolution verification email.
- Citizen -> satisfied/not satisfied, 1-5 rating, written feedback, or evidence-backed reopen request.
- All email attempts -> delivery audit row with status/error.

## Environment limitation

This build environment does not currently contain Flask/Werkzeug and cannot download PyPI packages, so a live Flask HTTP run was not possible here. The project preflight and source/template/database checks pass. Run `pip install -r requirements.txt` on the hackathon machine, then `python tools/preflight.py`, then `python app.py`.
