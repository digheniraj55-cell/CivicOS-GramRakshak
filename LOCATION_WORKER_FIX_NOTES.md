# CivicOS Location / Worker / Readability Fixes

## Fixed
- Removed the hard-coded Pimpri Chinchwad label from the Command Center.
- Added device live-location detection for the admin top bar.
- Added last-confirmed-location storage as a fallback.
- Added a live-location marker that can be centered from the Command Center location pill.
- Improved reverse geocoding to return a compact locality plus a more exact formatted address.
- Report Issue now shows exact coordinates, GPS accuracy and a pin preview before confirmation.
- The map picker starts from the last confirmed CivicOS location when one exists.
- Worker Center and individual worker dashboards are accessible without an admin login for hackathon/demo use.
- Worker update requests verify that the submitted worker dashboard matches the complaint's assigned worker.
- Increased only the UI text that was previously too small, especially admin tables, alerts, queue rows, status tags, settings, feedback, worker cards and supporting labels.

## Important browser behavior
Automatic browser GPS works best on HTTPS or localhost. A phone opening `http://<laptop-LAN-IP>:5000` can still be blocked by Chrome/Edge security rules. CivicOS cannot bypass the browser's security policy, so this build keeps three reliable fallbacks: last confirmed location, address search, and exact map-pin selection.

For a laptop demo, launch CivicOS using `START_CIVICOS.bat`; it opens `http://127.0.0.1:5000/` automatically.
