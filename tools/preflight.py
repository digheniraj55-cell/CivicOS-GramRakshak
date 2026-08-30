"""CivicOS pre-demo health check.
Run this before presenting: python tools/preflight.py
It does not modify project data.
"""
from __future__ import annotations
from pathlib import Path
import ast
import sqlite3
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(name, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}{(' — ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


# Python syntax
py_errors = []
for path in ROOT.glob("*.py"):
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        py_errors.append(f"{path.name}: {exc}")
check("Python syntax", not py_errors, "; ".join(py_errors))

# Required project files
required = [
    "app.py", "civicos_config.py", "civicos_intelligence.py", "civicos_assets.py", "civicos_trust.py", "translations.py",
    "civicos.db", "requirements.txt", "templates/index.html", "templates/admin_intelligence.html",
    "templates/admin_command_center.html", "templates/admin_verification.html", "templates/admin_accountability.html",
    "templates/citizen_login.html", "templates/citizen_verify_otp.html", "templates/worker_login.html", "templates/civic_intelligence_public.html", "templates/resolution_review.html",
    "templates/report.html", "templates/admin_assets.html", "templates/admin_asset_detail.html", "templates/public_assets.html",
    "templates/admin_contractors.html", "templates/admin_recovery.html", "templates/trust_center.html",
    "templates/truth_detail.html", "templates/admin_trust_center.html", "static/app.js",
    "static/style.css", "static/admin.css",
]
missing = [item for item in required if not (ROOT / item).exists()]
check("Required files", not missing, f"missing: {', '.join(missing)}" if missing else "all present")

# Database integrity + one-active-task policy
try:
    con = sqlite3.connect(ROOT / "civicos.db")
    con.row_factory = sqlite3.Row
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    check("SQLite integrity", integrity == "ok", integrity)
    violations = con.execute(
        """SELECT assigned_worker,COUNT(*) c FROM complaints
           WHERE status IN ('Assigned','In Progress') AND assigned_worker IS NOT NULL AND TRIM(assigned_worker)!=''
           GROUP BY assigned_worker HAVING c>1"""
    ).fetchall()
    check("One active task per team", not violations, f"violations: {len(violations)}")
    settings = dict(con.execute("SELECT setting_key,setting_value FROM system_settings").fetchall())
    check("Reserve Capacity Guard", settings.get("reserve_guard_enabled") == "1", f"state={settings.get('reserve_guard_enabled')}")
    check("Location label is not hard-coded", settings.get("civic_area_name", "").lower() not in {"pimpri chinchwad", "pcmc"}, settings.get("civic_area_name", ""))
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    trust_tables = {"truth_bulletins","misinformation_reports","complaint_trust_assessments"}
    check("Trust database layer", trust_tables.issubset(tables), f"tables={len(trust_tables & tables)}/{len(trust_tables)}")
    if trust_tables.issubset(tables):
        check("Public truth registry seeded", con.execute("SELECT COUNT(*) FROM truth_bulletins WHERE public_visible=1").fetchone()[0] > 0)
    con.close()
except Exception as exc:
    check("Database checks", False, str(exc))

# Jinja syntax when installed (Flask installs Jinja2)
try:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    errors = []
    for path in sorted((ROOT / "templates").glob("*.html")):
        try:
            env.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    check("Jinja templates", not errors, f"{len(list((ROOT/'templates').glob('*.html')))} parsed" if not errors else "; ".join(errors))
except Exception as exc:
    check("Jinja templates", False, f"Jinja2 unavailable: {exc}")


# Role-boundary checks
app_source = (ROOT / "app.py").read_text(encoding="utf-8")
check("Worker Center is admin-only", '@app.route("/workers")\n@login_required' in app_source)
check("Worker detail dashboards are admin-only", '@app.route("/worker/<worker_id>")\n@login_required' in app_source)
check("Worker portal requires worker auth", '@app.route("/worker/portal")\n@worker_required' in app_source)
check("Authority login restricted to admin role", "WHERE username=? AND role='admin'" in app_source)
check("Worker updates require worker-only auth", '@app.route("/worker/update/<int:cid>", methods=["POST"])\n@worker_required' in app_source and "demo_worker_access" not in app_source)
check("Citizen email OTP enabled", 'purpose="citizen_email_otp"' in app_source and "citizen_email_otps" in app_source)
check("Resolution feedback mail enabled", 'purpose="resolution_verification"' in app_source and "Confirm Resolution & Give Feedback" in app_source)
check("Email delivery audit enabled", "CREATE TABLE IF NOT EXISTS email_deliveries" in app_source)
check("Government asset registry enabled", "CREATE TABLE IF NOT EXISTS assets" in app_source and '@app.route("/admin/assets")' in app_source)
check("Contractor management enabled", '@app.route("/admin/contractors")' in app_source and "contractor_contracts" in app_source)
check("Procurement enabled", "@app.route('/admin/procurement')" in app_source and "purchase_orders" in app_source)
check("Finance enabled", '@app.route("/admin/finance")' in app_source and "finance_transactions" in app_source)
check("Blackout recovery enabled", '@app.route("/admin/recovery")' in app_source and "recovery_events" in app_source)
check("Asset complaint linking enabled", "linked_asset" in app_source and "asset_id" in app_source)
check("Trust Center enabled", '@app.route("/trust")' in app_source and '@app.route("/admin/trust")' in app_source)
check("Rumor verification API enabled", '@app.route("/api/trust/check", methods=["POST"])' in app_source)
check("Coordinated attack simulation enabled", '@app.route("/api/admin/trust/simulate-coordination", methods=["POST"])' in app_source)
check("Coordinated submission scoring enabled", "evaluate_submission(" in app_source and "complaint_trust_assessments" in app_source)
check("High-risk public quarantine enabled", "public_visibility" in app_source and "Quarantined" in app_source and "COALESCE(a.public_visibility,'Normal')!='Quarantined'" in app_source)
truth_template = (ROOT / "templates" / "truth_detail.html").read_text(encoding="utf-8")
check("Shareable WhatsApp correction enabled", "shareTruthWhatsApp" in truth_template and "wa.me" in truth_template)

worker_template = (ROOT / "templates" / "worker.html").read_text(encoding="utf-8")
check("Admin worker view is read-only", "{% if worker_view %}" in worker_template and "Admin view · read only" in worker_template and "worker_update" in worker_template)

# Main JavaScript syntax if Node is available
node = shutil.which("node")
if node:
    proc = subprocess.run([node, "--check", str(ROOT / "static" / "app.js")], capture_output=True, text=True)
    check("JavaScript syntax", proc.returncode == 0, proc.stderr.strip())
else:
    print("[SKIP] JavaScript syntax — Node.js not installed (browser can still run CivicOS).")

# Demo seed safety
check("Demo reset seed", (ROOT / "demo_seed" / "civicos_demo_seed.db").exists(), "ready")

print("\nCivicOS preflight:", "READY" if not failures else "ATTENTION NEEDED")
if failures:
    print("Failed checks:", ", ".join(failures))
    sys.exit(1)
