# CivicOS Worker Route Hotfix — 2026-08-30

Fixed the Worker Login BuildError caused by the redesigned worker login template referring to a non-existent Flask endpoint `emergency`.

Correct route: `url_for('sos')` -> `/sos`.

Validation performed:
- Worker Login template endpoints: PASS
- Worker Portal template endpoints: PASS
- Python compile: PASS
- No remaining `url_for('emergency')` references in worker templates

This hotfix changes only `templates/worker_login.html` in the safe patch.
