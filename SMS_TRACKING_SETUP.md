# CivicOS Citizen SMS + Live Tracking

This build sends an SMS after complaint registration and when an authority changes the complaint. The SMS includes the complaint ID and a clickable live tracking link.

## Render setup
1. Get your Fast2SMS API Authorization Key from its Dev API section.
2. Render -> your CivicOS service -> Environment.
3. Add `FAST2SMS_API_KEY` with your key.
4. Add `CIVICOS_PUBLIC_BASE_URL` with your deployed HTTPS URL, without a trailing slash.
5. Redeploy.

Never put the API key directly in app.py or GitHub.

For production messaging in India, use the provider's required DLT/entity/header/template registration and approved transactional route.
