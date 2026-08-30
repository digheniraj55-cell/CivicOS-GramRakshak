# CivicOS Location Guide

## What the project now does

CivicOS no longer relies on a hard-coded city label. The Command Center requests the current device location, reverse-geocodes the coordinates, stores the latest confirmed device location, and can center the intelligence map on it.

Citizen Report and SOS pages use a **best-fix GPS capture**: instead of accepting the first coarse browser position, CivicOS watches location briefly and keeps the most accurate reading it receives. The latitude, longitude and reported accuracy are shown before confirmation.

If GPS is unavailable, the citizen can still:

1. Search an address/landmark.
2. Select an exact point on the map.
3. Confirm the detected address and coordinates before submission.

## Browser security rule

Browser geolocation generally works on:
- `http://127.0.0.1:5000` / `http://localhost:5000` on the same laptop.
- Properly deployed **HTTPS** domains.

A phone opening a laptop through plain LAN HTTP such as `http://192.168.x.x:5000` may be blocked from giving precise GPS by Chrome/Edge security rules. CivicOS cannot bypass that browser policy, so it automatically keeps map/address selection as the fallback.

## Best hackathon setup

- Laptop demo: launch with `START_CIVICOS.bat` and allow location permission.
- Phone demo: use the deployed HTTPS URL whenever possible.
- If a venue network blocks OpenStreetMap/Nominatim, exact coordinates are still retained and CivicOS has an offline-safe map visualization for complaint markers.
