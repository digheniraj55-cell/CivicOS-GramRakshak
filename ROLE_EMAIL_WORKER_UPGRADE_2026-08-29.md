# CivicOS Role + Gmail/Email Upgrade — 29 Aug 2026

## Access control

- `/admin/workers` and `/workers` are authority-only.
- `/worker/<worker_id>` is authority-only and is used by admins to inspect a specific field team.
- New `/worker/login` route provides a dedicated Worker Login tab.
- New `/worker/portal` is worker-only and automatically opens only the authenticated worker/team's own queue.
- Worker updates are rejected unless the signed-in worker matches the complaint's assigned worker. The previous demo bypass was removed.
- Authority login now explicitly requires `role='admin'`.
- Citizen, worker and admin sessions are cleared when switching roles to avoid mixed-role sessions.
- Worker accounts are seeded from `civicos_config.py`. Demo username = worker ID without hyphens (example `WTR-01 -> wtr01`). Initial password comes from `CIVICOS_WORKER_DEFAULT_PASSWORD` and defaults to `worker123` for hackathon testing.

## Citizen Gmail/email verification

1. Local Civic Account registration creates a signed 24-hour verification token.
2. CivicOS sends the verification link to the citizen email through the configured SMTP/Gmail account.
3. Clicking the link marks `email_verified=1` for that Civic Account.
4. Verified email is required for weighted public actions such as one-person-one-upvote, community resolution verification and accountability reports.
5. Google OAuth accounts use Google's `email_verified` claim for account-email verification; municipal resident verification remains a separate status.

## Resolution email lifecycle

1. Worker marks field work complete and uploads after-work evidence.
2. Complaint becomes `Awaiting Admin Verification` — it is not closed by the worker.
3. Admin reviews proof in the verification queue.
4. Only after admin approval does CivicOS mark the case resolved and send the citizen a signed 14-day resolution link.
5. Citizen can rate the field worker 1–5 stars and leave written feedback.
6. If not satisfied, the citizen must provide a reason and fresh photo evidence. The case becomes a reopen request requiring admin review.

## Email diagnostics

Admin → Settings now includes:

- Gmail/SMTP configuration
- real delivery verification button
- public URL used inside citizen email buttons
- last SMTP error
- recent email delivery audit showing purpose, recipient, success/failure and error details

For Gmail use `smtp.gmail.com`, port `587`, STARTTLS and a Google App Password. Do not use the normal Gmail password.
