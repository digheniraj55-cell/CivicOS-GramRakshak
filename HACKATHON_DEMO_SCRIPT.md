# CivicOS 5-Minute Judge Demo

## 0:00–0:35 — Problem + Citizen Report
“Most civic systems stop at complaint registration. CivicOS closes the entire operational loop and then learns from it.”

Open **Report a Civic Issue**. Show citizen details, auto/manual category, exact GPS/map selection, location confirmation and photo evidence. Submit one issue and point out the complaint ID/recovery option.

## 0:35–1:20 — Command Center
Login to the Authority Command Center. Show the live device location in the top bar, live complaint queue, map, SLA alerts and department/worker capacity.

Open the new complaint and show:
- smart department routing,
- priority + SLA,
- one-task-per-field-team rule,
- Reserve Capacity Guard.

## 1:20–2:55 — The winning difference: Civic Intelligence
Open **Civic Intelligence**.

Use this sequence:
1. **Civic Memory + Causal Graph** — “These are not isolated tickets anymore; CivicOS connects symptoms and suggests a probable root cause.”
2. **Digital Twin Lite** — “If we wait seven days, this is the estimated added cost and danger.”
3. **Blind-Spot Radar** — “Low complaints do not always mean low distress; these areas deserve proactive inspection.”
4. **Risk Forecast + Civic Health** — show preventive maintenance direction.
5. **Service Equity** — “We compare operational service outcomes without profiling citizens.”
6. **Civic Debt + Chronic Failure** — explain repeated repair waste.

## 2:55–3:35 — Optimize scarce resources
Open **Public Value Optimizer**. Change budget/workers/vehicles and run the plan.

Say: “Government never has unlimited money or teams. CivicOS ranks interventions by expected public value under real constraints.”

Show **Never spend the last resource** and toggle **Disaster Operations Mode**.

## 3:35–4:15 — Coordinate, don’t duplicate
Open **Cross-Department Sweeps**. Create a suggested sweep from a connected multi-department cluster.

Show **One Trip, Multiple Problems** route batching. Clarify that inspection batching does not violate the one-active-repair-task rule.

## 4:15–4:50 — Field execution + proof
Open Worker Center without admin login. Take the assigned task → In Progress → upload after-work photo → Resolve.

Track the complaint as a citizen. Show timeline/notification and click **I confirm this issue is resolved**. Explain the proof score and visual-change signal.

## 4:50–5:00 — Closing line
“CivicOS is not another complaint portal. It is an operating and intelligence layer for local government: detect, understand, predict, prioritize, allocate, resolve, verify, learn and prevent.”

## Judge questions to be ready for
- **Is the AI making government decisions?** No. Numerical engines are transparent decision-support heuristics; optional AI helps natural-language classification/explanation. Authorities remain in control.
- **Is your risk model production-ready?** No claim of that. It is a hackathon MVP showing architecture and workflow. Production needs calibration/validation on municipal GIS, asset, weather and historical repair data.
- **How do you prevent double assignment?** Application checks plus a SQLite partial unique index enforce one unresolved task per worker/team.
- **Why is your location different on phone LAN?** Browser GPS requires HTTPS on non-localhost origins; the deployed HTTPS URL works, while CivicOS provides exact map/search fallback for LAN demos.

## Released Challenge — The Blackout (LIVE)

**Goal:** prove that CivicOS keeps operating when its primary data store is corrupted mid-operation.

1. Log in as `admin` / `admin123` and open **Blackout Recovery** from the left navigation.
2. Show **PRIMARY HEALTHY**, **Backup integrity PASS**, and the protected complaint/inventory record counts.
3. Click **Simulate Live Blackout**. This is not a visual animation: CivicOS intentionally makes the real primary SQLite file unreadable, preserves the damaged artifact, detects the failure through its normal database access path, restores the independent snapshot, verifies SQLite integrity, and logs the incident.
4. Point to the **Recovery Event Ledger**: incident ID, recovery duration, records protected, integrity result, and status.
5. Return to **Complaints** or **Procurement & Inventory** and perform a normal action to prove operations resumed after recovery.

**Judge line:** “The blackout button corrupts the real primary store. The application then recovers itself from a separate known-good snapshot before continuing. We preserve the damaged evidence and verify the data instead of merely showing a recovery animation.”

---

## Challenge 2 add-on demo — False information & coordinated fake submissions

**Say:** “CivicOS should not become a trusted-looking amplifier for unverified information. So we added a separate Civic Trust layer.”

1. Open **Trust Center** from the public navbar.
2. Paste: **WhatsApp says Route 7 bus has been permanently cancelled**.
3. Show the **False** result, authority correction and source.
4. Open the bulletin and click **Copy verified correction** / **Share to WhatsApp**.
5. Return to Trust Center and paste the demo crop-treatment rumor. Show **Unverified**, then submit it to the Trust Queue.
6. Admin → **Trust & Verification**. Show the rumor inbox and publish/review controls.
7. Click **Run Coordination Attack Simulation**.
8. Point at the cross-account, cross-ward, repeated-text signals and automatic public-quarantine policy.

**Say:** “The important part is that a risk score never automatically declares a complaint fake. Service processing continues, but CivicOS can stop suspicious content from being amplified publicly until evidence is reviewed.”
