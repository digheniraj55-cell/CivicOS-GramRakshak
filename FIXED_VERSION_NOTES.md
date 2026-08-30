# CivicOS Fixed Version

## Fixed crash

The `/admin/recovery` route was passing `recovery_events` twice to Flask's `render_template()`:

- once explicitly (`recovery_events=events`)
- once through `**context`, because `admin_common_context()` already returned `recovery_events`

Flask 3 raises:
`TypeError: flask.templating.render_template() got multiple values for keyword argument 'recovery_events'`

The route now loads the 12 most recent recovery events and replaces `context["recovery_events"]` before rendering, so the template receives exactly one `recovery_events` keyword.

## Validation

- `app.py` passes Python compilation (`py_compile`).
- AST parsing succeeds.
- Static duplicate-key scan for calls using `**context` found no duplicate literal keyword names.

## Run on Windows

1. Open a terminal in this folder.
2. Install dependencies:
   `py -m pip install -r requirements.txt`
3. Start the app using `START_CIVICOS.bat`, or run:
   `py app.py`
