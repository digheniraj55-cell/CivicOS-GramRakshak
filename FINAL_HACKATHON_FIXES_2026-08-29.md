# CivicOS Final Hackathon Fixes — 2026-08-29

## Citizen identity
- Google Sign-In is removed from the citizen UI.
- Citizen registration uses password + CAPTCHA + 6-digit email OTP.
- OTP expires after 10 minutes, is stored as a password hash, has a 5-attempt limit, and resend throttling.
- A citizen must verify the account email before reporting a civic issue.
- SOS remains accessible without citizen login.

## Resolution feedback email
- If an administrator directly changes a complaint to `Resolved`, CivicOS sends the reporting citizen the secure resolution-feedback email.
- If a worker submits completion proof, the case becomes `Awaiting Admin Verification`; no citizen closure email is sent yet.
- When the administrator approves the worker completion, the complaint becomes `Resolved` and CivicOS sends the reporting citizen a signed 14-day feedback link.
- The citizen can confirm satisfaction, give a 1–5 star worker rating, write feedback, or request reopening with fresh photo evidence.
- Email delivery attempts are recorded in the Email Delivery Audit under Admin Settings.

## Worker/admin boundary
- Worker Login and `/worker/portal` are worker-only.
- Worker task updates and evidence uploads require `@worker_required` and are restricted to the authenticated worker's assigned task.
- Admin can inspect Worker Center and worker performance pages, but worker task controls are read-only in the admin worker view.
- Admin authority actions remain in Command Center / complaint controls / verification queue, not in the worker dashboard.
