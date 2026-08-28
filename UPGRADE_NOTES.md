# CivicOS Upgrade Notes — 28 Aug 2026

## Problems fixed

1. Admin sidebar items previously jumped to sections of one long page. The admin area is now split into dedicated page routes with a persistent sidebar and top bar.
2. The public CivicOS brand text became effectively invisible in dark mode because the brand name had a hard-coded dark text color. Dark-theme overrides now keep the logo, CivicOS name and subtitle readable.
3. The homepage felt stretched on wide screens. Core content widths, hero typography, cards and spacing are now more compact and solid while remaining responsive.
4. Browser location could fail when CivicOS was opened on another device through a plain-HTTP LAN IP. Modern browsers restrict precise geolocation outside secure contexts. Report Issue and SOS now provide GPS + server reverse geocoding + address search + map-pin fallback.
5. Direct browser reverse-geocoding requests could be affected by client/network restrictions. CivicOS now proxies reverse geocoding through `/api/reverse-geocode` and address search through `/api/geocode`.
6. Moving away from the old single-page admin view would have removed the inline complaint-update controls. Authority update controls were therefore added to complaint details, with busy field teams disabled in the assignment list.
7. Worker one-task enforcement remains intact at application and SQLite levels.

## New admin pages

- `/admin`
- `/admin/dashboard`
- `/admin/complaints`
- `/admin/departments`
- `/admin/workers`
- `/admin/analytics`
- `/admin/sla`
- `/admin/feedback`
- `/admin/reports`
- `/admin/transparency`
- `/admin/settings`
- `/admin/announcements`
- `/admin/alerts`
- `/admin/emergency`
- `/admin/export`

## Important location note

When opened as `http://10.x.x.x:5000` on a phone or another laptop, native browser GPS may still be blocked by the browser because the page is not HTTPS. CivicOS now detects that situation and automatically exposes the map/search fallback so the project remains usable during a LAN demo. For final hosting, use HTTPS to enable native phone GPS normally.
