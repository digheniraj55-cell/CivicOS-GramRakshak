# CivicOS Governance Upgrade — 29 Aug 2026

## Product direction
CivicOS is being evolved from a complaint-centric system into a local-government operations, civic intelligence and accountability platform. Complaints remain one operational input, but the product now exposes civic activity, public intelligence, worker QA, administration accountability and verified citizen participation.

## Implemented in this build

1. **Civic Account authentication** — local account + CAPTCHA + 6-digit email OTP, profile/locality fields, separate account-email and resident-verification indicators.
2. **Nearby Civic Activity** — browser geolocation, radius filtering, civic status/location cards and one-account-one-upvote enforcement in SQLite.
3. **Public Civic Intelligence after citizen login** — ward health, department performance, civic news, authority QA delay, verified closures, reopen signals and accountability review counts.
4. **SOS before login** — emergency access remains unauthenticated.
5. **Public Board is a direct navigation tab** rather than buried in a dropdown.
6. **Closed-loop resolution** — worker completion submission → admin QA → citizen secure email → 1–5 star rating / written feedback / evidence-backed reopen request.
7. **Civic Voice** — English, Hindi and Marathi speech input on Report Civic Issue using supported browser speech recognition.
8. **Administrative Accountability** — structured citizen reports, evidence upload, moderated public status and dedicated authority review queue.
9. **Admin completion verification queue** — a worker cannot independently close a case; admin approval is the closure gate.
10. **Worker Performance Engine** — balanced 100-point score, benchmark band and incentive eligibility.
11. **Audit trail** — important citizen, worker and authority actions are recorded in `audit_log` and the case timeline.
12. **Email diagnostics** — Admin Settings shows non-secret SMTP configuration state/public link base and can send a real delivery test.

## Resolution lifecycle

```text
Reported
  ↓
Assigned / In Progress
  ↓
Worker submits completion proof
  ↓
Awaiting Admin Verification
  ├─ Return for more work → Pending
  └─ Approve → Resolved
                 ↓
        Secure citizen email
                 ↓
        Satisfied + rating
             OR
        Reopen request + fresh proof
                 ↓
          Admin reopen review
```

## Email troubleshooting checklist

- Set `CIVICOS_PUBLIC_URL` to the deployed HTTPS domain. Otherwise email buttons may point to localhost when generated locally.
- Gmail: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_SECURITY=starttls`.
- Use a Google App Password after enabling 2-Step Verification. Do not use the normal Gmail password.
- Ensure `SMTP_FROM` is permitted by the SMTP account/provider.
- Open **Admin → Settings → Email & Citizen Action-Link Diagnostics** and send a test email before presenting.
- In-app notifications remain available if SMTP delivery is not configured.

## Email OTP verification

CivicOS does not require Google Cloud OAuth in this build. New citizen accounts receive a six-digit OTP through the configured SMTP/Gmail account. The OTP expires after 10 minutes, is stored only as a secure hash, allows a maximum of five incorrect attempts, and resend is throttled.

Email verification proves ownership of the email address; it does **not** prove municipal residency. CivicOS therefore keeps `email_verified` and `resident_verified` as separate fields.

## Participation-integrity rule
Local password accounts begin with `email_verified=0`. CivicOS sends a 6-digit OTP when SMTP is configured. A verified email is required before reporting civic issues and for actions that carry public weight: issue upvotes, community resolution verification and submitting administration-accountability reports. SOS never requires login. This reduces throwaway-account manipulation while keeping `resident_verified` separate for future municipality/OTP/government-ID verification.
