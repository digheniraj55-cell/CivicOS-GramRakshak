# Challenge 2 Integration — Civic Trust & Verification Layer

## Challenge addressed
False information can move faster than official corrections. CivicOS must not become another amplifier for a fake scheme notice, health/water warning, transport rumor, food recall claim, or coordinated reputational attack submitted through the platform itself.

## What was integrated

### 1. Public Civic Trust Center — `/trust`
Citizens can paste a forwarded message before sharing it. CivicOS compares the wording against the published authority bulletin registry and returns one of these clear states:
- **True**
- **False**
- **Misleading**
- **Official Update**
- **Unverified**

A weak/no match is never treated as proof that a claim is true.

### 2. Authority truth bulletin registry
Admins can publish an official correction with:
- circulating claim
- verdict
- correction/context
- responsible authority/source
- primary-source link
- matching keywords
- optional citizen announcement push

Each public bulletin has a stable page: `/truth/<id>`.

### 3. Share-the-correction workflow
Public fact-check pages include:
- Copy verified correction
- Share to WhatsApp

The shared text carries the verdict, claim, correction, source and CivicOS bulletin link so users send the corrected version—not only a screenshot of the rumor.

### 4. Community rumor reporting
When CivicOS cannot confidently match a message, citizens can submit it to the authority Trust Queue. It remains labelled **Unverified** until reviewed.

### 5. Complaint information-integrity triage
Every new complaint is assessed independently from login/OTP identity verification. The local explainable engine considers:
- verified account linkage
- photo evidence presence
- high-impact/reputational language
- forwarded/viral-message language
- near-identical recent text
- same wording across different citizen identities
- same wording across multiple wards
- legitimate same-area issue clustering

The score is a **review priority**, not a truth verdict.

### 6. Coordinated fake-submission quarantine
A highly suspicious complaint can be temporarily withheld from:
- public transparency complaint list
- public/home civic map feed
- nearby citizen activity feed
- home recent-activity feed

Operational handling, the complaint record, timeline and audit history remain intact. This means CivicOS can reduce reputational amplification without accidentally deleting a genuine emergency/service request.

### 7. Authority Trust & Verification Center — `/admin/trust`
The admin workspace includes:
- rumor review queue
- authority bulletin publisher
- high-risk complaint queue
- risk signals and similarity references
- public visibility/quarantine decision
- Cleared / Needs Review / Coordinated Abuse / False Submission review states
- public correction publishing

### 8. Safe coordinated-attack simulation
`/api/admin/trust/simulate-coordination` runs a zero-side-effect in-memory attack scenario containing four near-identical accusatory submissions from different accounts/wards. It shows the score, signals and quarantine policy without changing real CivicOS data.

### 9. Offline-capable verification core
Claim matching and coordinated-submission triage use `civicos_trust.py` and Python standard-library logic. They do not require an external AI service, so basic integrity protection still works during network degradation/blackout conditions.

## Important design principle
**Identity verified ≠ information verified.**

Email OTP proves control of an email/account. It does not prove that the content submitted by that account is factual. CivicOS therefore stores identity trust and information trust as separate layers.

## Judge demo — 90 seconds
1. Open `/trust`.
2. Paste: `WhatsApp says Route 7 bus has been permanently cancelled`.
3. CivicOS matches the demo authority bulletin and shows **False** with the correction/source.
4. Open the shareable correction and click **Share to WhatsApp** or **Copy verified correction**.
5. Paste an unknown rumor such as: `Viral message claims an unnamed crop treatment is officially approved and guarantees 100% yield.`
6. CivicOS returns **Unverified**; submit it to the Trust Queue.
7. Login as admin → open **Trust & Verification**.
8. Review the submitted rumor and publish an official correction.
9. Click **Run Coordination Attack Simulation**. Show the high risk score, cross-account/cross-ward copy signals, and automatic quarantine decision.

## Demo-data warning
The bundled authority bulletins are explicitly labelled **HACKATHON DEMO**. Replace them with real department/official-source records before any real deployment.

## Files added/changed
- `civicos_trust.py`
- `templates/trust_center.html`
- `templates/truth_detail.html`
- `templates/admin_trust_center.html`
- `app.py`
- `templates/base.html`
- `templates/admin_base.html`
- `templates/index.html`
- `templates/report.html`
- `templates/track.html`
- `templates/complaint_detail.html`
- `static/style.css`
- `static/admin.css`
- `tools/preflight.py`
- bundled SQLite demo/recovery databases
