# CivicOS OTP Hotfix — 2026-08-30

## Cause
The application was generating OTPs correctly, but the packaged project intentionally contained no Gmail/SMTP credentials. Without SMTP credentials no software can deliver a real email.

## Fixes
- Real SMTP/Gmail delivery remains the first path.
- Delivery failures are now surfaced clearly.
- On localhost/127.0.0.1 only, CivicOS exposes a temporary **Hackathon Local OTP** if SMTP fails.
- The local OTP uses the same hashed database challenge and expires in 10 minutes.
- The local fallback is disabled on deployed/public hosts unless explicitly enabled with `CIVICOS_ALLOW_LOCAL_OTP=1`.
- Successful OTP verification removes the local code from the session.
- Login, registration and resend messages now distinguish Delivered / Local Fallback / Failed states.

## Real Gmail delivery
Admin → Settings → Email & OTP Setup:
- SMTP host: smtp.gmail.com
- Port: 587
- Security: STARTTLS
- Username: Gmail address
- From: same Gmail address
- Password: Google App Password (not the normal Gmail password)

Use **Verify Gmail & Send Test** before testing citizen registration.
