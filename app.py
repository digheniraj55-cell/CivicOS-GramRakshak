import csv
import io
import json
import html as html_lib
import os
import re
import secrets
import shutil
import time
import uuid
import smtplib
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from html import escape
from math import atan2, cos, radians, sin, sqrt

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    session,
    url_for,
    flash,
    send_file,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from civicos_assets import (
    ASSET_CATEGORIES,
    ASSET_STATUS_OPTIONS,
    calculate_condition_index,
    evaluate_maintenance_due,
    get_demo_assets_seed,
    summarize_asset_portfolio,
)

from civicos_trust import (
    evaluate_submission,
    find_best_bulletin_match,
    trust_label,
    trust_tone,
    verdict_tone,
)

from civicos_intelligence import (
    blind_spots,
    build_civic_memory,
    build_sweep_suggestions,
    cascade_for,
    causal_clusters,
    chronic_failures,
    civic_debt,
    civic_health,
    cost_of_delay,
    impact_score,
    intelligence_bundle,
    optimize_public_value,
    policy_insights,
    proof_verification,
    reserve_capacity,
    route_batches,
    ward_risk,
)

from civicos_config import (
    ALLOWED_IMAGE_EXTENSIONS,
    CATEGORY_LABELS,
    DEPARTMENTS,
    ROUTING_RULES,
    STATUS_ORDER,
    WORKERS,
)

from translations import (
    CATEGORY_TRANSLATION_KEYS,
    DEPARTMENT_TRANSLATION_KEYS,
    STATUS_TRANSLATION_KEYS,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_local_env(path):
    """Load a local .env file without adding another runtime dependency.

    Existing OS environment variables always win, which keeps Render/production
    secrets authoritative while making the bundled .env.example genuinely useful
    for a hackathon laptop.
    """
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key or key in os.environ:
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
                    value = value[1:-1]
                os.environ[key] = value
    except OSError:
        pass


load_local_env(os.path.join(BASE_DIR, ".env"))

INTEGRATION_CONFIG_PATH = os.path.join(BASE_DIR, "instance", "integrations.json")
os.makedirs(os.path.dirname(INTEGRATION_CONFIG_PATH), exist_ok=True)
DB = os.path.join(BASE_DIR, "civicos.db")
# The recovery store is intentionally separate from the primary SQLite file.
# A blackout can therefore destroy/corrupt the primary DB without destroying
# the last known-good snapshot used for automatic recovery.
RECOVERY_DB = os.path.join(BASE_DIR, "civicos_recovery.db")
RECOVERY_META = os.path.join(BASE_DIR, "civicos_recovery_meta.json")
RECOVERY_CORRUPT_DIR = os.path.join(BASE_DIR, "recovery_incidents")
UPLOAD = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(RECOVERY_CORRUPT_DIR, exist_ok=True)
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-before-production")
app.config["UPLOAD_FOLDER"] = UPLOAD
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("CIVICOS_SECURE_COOKIES", "0") == "1"
app.jinja_env.filters["from_json"] = lambda s: json.loads(s) if (s and isinstance(s, str)) else (s or {})

# New strings are added as updates so the original multilingual dictionary stays reusable.
TRANSLATIONS["en"].update(
    {
        "find_complaint": "Find Complaint ID",
        "forgot_complaint_id": "Forgot complaint ID?",
        "notification_center": "Notifications",
        "my_updates": "My Updates",
        "browser_alerts": "Browser Alerts",
        "enable_alerts": "Enable update alerts",
        "one_task_policy": "One active task per field team",
        "available": "Available",
        "busy": "Busy",
        "queued": "Queued",
        "current_assignment": "Current Assignment",
        "completed_history": "Completed History",
        "email_optional": "Email (optional)",
        "recovery_help": "Use the same name and phone number used while reporting the complaint.",
        "no_recovered_complaints": "No matching complaints were found.",
        "recent_on_device": "Recent complaints on this device",
        "open_tracking": "Open tracking",
        "notification_help": "View status, assignment and SLA updates for your complaints.",
        "no_notifications": "No updates are available yet.",
        "how_civicos_works": "How CivicOS Works",
        "popular_issue_categories": "Popular Issue Categories",
        "view_all_categories": "View all categories",
        "report_now": "Report now",
        "about_us": "About Us",
        "dashboards": "Dashboards",
        "home_subtitle": "Smarter Cities. Stronger Communities.",
    }
)
TRANSLATIONS["mr"].update(
    {
        "find_complaint": "तक्रार क्रमांक शोधा",
        "forgot_complaint_id": "तक्रार क्रमांक विसरलात?",
        "notification_center": "सूचना",
        "my_updates": "माझे अपडेट्स",
        "browser_alerts": "ब्राउझर सूचना",
        "enable_alerts": "अपडेट सूचना सुरू करा",
        "one_task_policy": "प्रत्येक फील्ड टीमकडे एकावेळी एकच सक्रिय काम",
        "available": "उपलब्ध",
        "busy": "व्यस्त",
        "queued": "प्रतीक्षेत",
        "current_assignment": "सध्याचे काम",
        "completed_history": "पूर्ण कामांचा इतिहास",
        "email_optional": "ईमेल (ऐच्छिक)",
        "recovery_help": "तक्रार नोंदवताना वापरलेले तेच नाव आणि फोन क्रमांक द्या.",
        "no_recovered_complaints": "जुळणाऱ्या तक्रारी सापडल्या नाहीत.",
        "recent_on_device": "या डिव्हाइसवरील अलीकडील तक्रारी",
        "open_tracking": "ट्रॅकिंग उघडा",
        "notification_help": "तुमच्या तक्रारींचे स्थिती, नियुक्ती आणि SLA अपडेट्स पहा.",
        "no_notifications": "अजून कोणतेही अपडेट उपलब्ध नाहीत.",
        "how_civicos_works": "CivicOS कसे कार्य करते",
        "popular_issue_categories": "लोकप्रिय तक्रार प्रकार",
        "view_all_categories": "सर्व प्रकार पहा",
        "report_now": "आता नोंदवा",
        "about_us": "आमच्याबद्दल",
        "dashboards": "डॅशबोर्ड",
        "home_subtitle": "स्मार्ट शहरे. सक्षम समुदाय.",
    }
)


def _integrity_ok(path):
    """Return True only when SQLite can fully validate the database file."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    con = None
    try:
        con = sqlite3.connect(path, timeout=5)
        result = con.execute("PRAGMA integrity_check").fetchone()
        return bool(result and str(result[0]).lower() == "ok")
    except (sqlite3.DatabaseError, OSError):
        return False
    finally:
        if con is not None:
            con.close()


def _load_recovery_meta():
    default = {"incidents": [], "active_incident": None}
    try:
        with open(RECOVERY_META, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return default
        data.setdefault("incidents", [])
        data.setdefault("active_incident", None)
        return data
    except (OSError, ValueError, TypeError):
        return default


def _save_recovery_meta(data):
    temp = RECOVERY_META + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(temp, RECOVERY_META)
    except OSError:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass


def create_recovery_snapshot(source_con=None):
    """Create a consistent SQLite backup without relying on filesystem copying."""
    if not os.path.isfile(DB) or os.path.getsize(DB) == 0:
        return False
    own_source = source_con is None
    source = source_con
    destination = None
    temp = RECOVERY_DB + ".tmp"
    try:
        if own_source:
            source = sqlite3.connect(DB, timeout=15)
        destination = sqlite3.connect(temp, timeout=15)
        source.backup(destination)
        destination.close()
        destination = None
        os.replace(temp, RECOVERY_DB)
        return _integrity_ok(RECOVERY_DB)
    except (sqlite3.DatabaseError, OSError):
        return False
    finally:
        if destination is not None:
            destination.close()
        if own_source and source is not None:
            source.close()
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass


def restore_primary_from_recovery(reason="automatic integrity recovery"):
    """Restore the primary store from the last good snapshot."""
    if not _integrity_ok(RECOVERY_DB):
        return False
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    quarantine = os.path.join(RECOVERY_CORRUPT_DIR, f"primary_before_restore_{stamp}.db")
    try:
        if os.path.isfile(DB) and os.path.getsize(DB) > 0:
            shutil.copy2(DB, quarantine)
        temp = DB + ".restore.tmp"
        shutil.copy2(RECOVERY_DB, temp)
        os.replace(temp, DB)
        meta = _load_recovery_meta()
        active = meta.get("active_incident")
        if active:
            active["restored_at"] = iso()
            active["status"] = "Recovered"
            active["reason"] = reason
            active["quarantined_file"] = os.path.relpath(quarantine, BASE_DIR) if os.path.exists(quarantine) else None
            active["duration_ms"] = round((time.time() - float(active.get("started_epoch", time.time()))) * 1000, 1)
            active.pop("started_epoch", None)
            meta["incidents"] = ([active] + meta.get("incidents", []))[:20]
            meta["active_incident"] = None
            _save_recovery_meta(meta)
        return _integrity_ok(DB)
    except (OSError, sqlite3.DatabaseError):
        return False


def ensure_primary_store():
    """Self-heal before every DB connection when the primary store is missing/corrupt."""
    if _integrity_ok(DB):
        return False
    return restore_primary_from_recovery("Primary store missing/corrupt; self-heal triggered before DB access")


def db():
    ensure_primary_store()
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    # Detect corruption even when the file still exists and SQLite opens it.
    try:
        result = con.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            con.close()
            restore_primary_from_recovery("SQLite quick_check detected corruption")
            con = sqlite3.connect(DB, timeout=15)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
    except sqlite3.DatabaseError:
        con.close()
        if not restore_primary_from_recovery("SQLite could not read the primary store"):
            raise
        con = sqlite3.connect(DB, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
    return con


def get_language():
    lang = session.get("lang", "en")
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def t(key, **kwargs):
    lang = get_language()
    text = TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def department_label(department):
    key = DEPARTMENT_TRANSLATION_KEYS.get(department)
    return t(key) if key else DEPARTMENTS.get(department, department or "—")


def category_label(category):
    key = CATEGORY_TRANSLATION_KEYS.get(category)
    return t(key) if key else CATEGORY_LABELS.get(category, category or "—")


def status_label(status):
    key = STATUS_TRANSLATION_KEYS.get(status)
    return t(key) if key else status


def timeline_step_label(step):
    mapping = {
        "Reported": {"en": "Reported", "mr": "तक्रार नोंदवली"},
        "Location Confirmed": {"en": "Location Confirmed", "mr": "स्थान निश्चित झाले"},
        "Location Added": {"en": "Location Added", "mr": "स्थान जोडले"},
        "AI Analysis": {"en": "Smart Analysis", "mr": "स्मार्ट विश्लेषण"},
        "Smart Department Routing": {"en": "Smart Department Routing", "mr": "स्मार्ट विभागीय रूटिंग"},
        "SLA Assigned": {"en": "SLA Assigned", "mr": "SLA निश्चित केला"},
        "Worker Assigned": {"en": "Worker Assigned", "mr": "कर्मचारी नियुक्त केला"},
        "Queued for Worker": {"en": "Queued for Worker", "mr": "कर्मचारी प्रतीक्षेत"},
        "Queue Auto-Assignment": {"en": "Queue Auto-Assignment", "mr": "प्रतीक्षा यादीतून स्वयंचलित नियुक्ती"},
        "Assignment Queue Correction": {"en": "Assignment Queue Correction", "mr": "नियुक्ती यादी दुरुस्ती"},
        "In Progress": {"en": "In Progress", "mr": "काम सुरू आहे"},
        "Worker Completion Submitted": {"en": "Worker Completion Submitted", "mr": "कर्मचाऱ्याने पूर्णत्व पडताळणीसाठी सादर केले"},
        "Authority Verified Completion": {"en": "Authority Verified Completion", "mr": "प्राधिकरणाने काम पूर्ण झाल्याची पडताळणी केली"},
        "Authority Returned Work": {"en": "Authority Returned Work", "mr": "प्राधिकरणाने काम परत पाठवले"},
        "Citizen Verified": {"en": "Citizen Verified", "mr": "नागरिकाने पडताळले"},
        "Reopen Requested": {"en": "Reopen Requested", "mr": "पुन्हा उघडण्याची विनंती"},
        "Reopen Approved": {"en": "Reopen Approved", "mr": "पुन्हा उघडण्यास मंजुरी"},
        "Reopen Rejected": {"en": "Reopen Rejected", "mr": "पुन्हा उघडण्याची विनंती नाकारली"},
        "Community Resolution Verification": {"en": "Community Resolution Verification", "mr": "समुदाय समाधान पडताळणी"},
        "Resolved": {"en": "Resolved", "mr": "निकाली काढले"},
        "SLA Escalated": {"en": "SLA Escalated", "mr": "SLA वरिष्ठ स्तरावर पाठवला"},
        "Duplicate / Cluster Flag": {"en": "Duplicate / Cluster Flag", "mr": "समान / क्लस्टर तक्रार"},
        "Community Upvote": {"en": "Community Upvote", "mr": "समुदाय समर्थन"},
        "Citizen Feedback": {"en": "Citizen Feedback", "mr": "नागरिक अभिप्राय"},
        "After Photo Uploaded": {"en": "After Photo Uploaded", "mr": "नंतरचा फोटो अपलोड केला"},
        "Emergency Reported": {"en": "Emergency Reported", "mr": "आपत्कालीन तक्रार नोंदवली"},
    }
    item = mapping.get(step)
    return item.get(get_language(), item["en"]) if item else step


def display_time(value=None):
    if value is None:
        value = datetime.now()
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d %b %Y, %I:%M %p")


def iso(value=None):
    return (value or datetime.now()).replace(microsecond=0).isoformat()


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits


def valid_phone(value):
    digits = normalize_phone(value)
    return 8 <= len(digits) <= 15


def valid_email(value):
    if not value:
        return True
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()))


def try_ai_analysis(title, description):
    """Optional OpenAI routing. The application works fully without an API key."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    payload = {
        "model": os.environ.get("CIVICOS_AI_MODEL", "gpt-4.1-mini"),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Classify local-government civic complaints. Return JSON only with keys "
                    "category, department, required_skill, problem_summary, reason. "
                    "Allowed categories: water,electricity,road,safety,health,fire. "
                    "Allowed departments: water,electricity,road,police,health,fire."
                ),
            },
            {"role": "user", "content": f"Title: {title}\nDescription: {description}"},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        return json.loads(data["choices"][0]["message"]["content"])
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return None


def infer_required_skill(department, text):
    text = text.lower()
    skill_rules = {
        "water": [
            ("drainage", ["drain", "sewage", "drainage"]),
            ("pipeline leakage", ["pipeline", "pipe", "leak"]),
            ("water supply", ["water", "tap", "pump"]),
        ],
        "electricity": [
            ("transformer", ["transformer"]),
            ("streetlight", ["streetlight", "light", "pole"]),
            ("wiring", ["wire", "spark", "short circuit"]),
        ],
        "road": [
            ("pothole repair", ["pothole", "खड्डा"]),
            ("footpath repair", ["footpath"]),
            ("road repair", ["road", "bridge", "street"]),
        ],
        "police": [
            ("women safety", ["women", "harassment", "महिला"]),
            ("accident response", ["accident"]),
            ("public safety", ["crime", "theft", "danger", "fight"]),
        ],
        "health": [
            ("ambulance", ["ambulance", "medical", "hospital"]),
            ("sanitation", ["garbage", "waste", "sanitation", "कचरा"]),
            ("health response", ["health", "disease", "sick"]),
        ],
        "fire": [("fire rescue", ["fire", "smoke", "burn", "flame", "आग"])],
    }
    for skill, words in skill_rules.get(department, []):
        if any(word in text for word in words):
            return skill
    return "general maintenance"


def smart_route(title, description, selected="auto"):
    text = f"{title} {description}".lower()
    if selected and selected != "auto":
        if selected not in CATEGORY_LABELS:
            raise ValueError("Invalid category")
        dept = "police" if selected == "safety" else selected
        skill = infer_required_skill(dept, text)
        return (
            selected,
            dept,
            skill,
            f"Citizen selected {CATEGORY_LABELS.get(selected, selected)}; CivicOS confirmed routing to {DEPARTMENTS.get(dept, dept)}.",
        )

    ai = try_ai_analysis(title, description)
    if ai:
        category = str(ai.get("category", "")).lower().strip()
        dept = str(ai.get("department", "")).lower().strip()
        if category in set(CATEGORY_LABELS) - {"auto"} and dept in DEPARTMENTS:
            skill = str(ai.get("required_skill") or infer_required_skill(dept, text)).strip()
            summary = str(ai.get("problem_summary") or "civic issue").strip()
            reason = str(ai.get("reason") or "AI classification matched the issue.").strip()
            return category, dept, skill, f"AI detected {summary}. Required skill: {skill}. {reason}"

    scores = {key: 0 for key in ROUTING_RULES}
    for dept, words in ROUTING_RULES.items():
        for word in words:
            if word in text:
                scores[dept] += 1
    dept = max(scores, key=scores.get)
    if scores[dept] == 0:
        dept = "road"
        reason = "No strong category keyword was detected; CivicOS routed the issue to Roads & Public Works for triage."
    else:
        matched = [w for w in ROUTING_RULES[dept] if w in text][:3]
        reason = f"Smart routing matched {', '.join(matched)} and selected {DEPARTMENTS[dept]}."
    category = "safety" if dept == "police" else dept
    skill = infer_required_skill(dept, text)
    return category, dept, skill, reason


def service_priority(title, description, category, emergency=False, upvotes=0, escalated=False):
    text = f"{title} {description} {category}".lower()
    score = 25
    critical = ["emergency", "women", "fire", "medical", "ambulance", "spark", "danger", "accident", "help", "आग", "महिला"]
    high = ["leak", "pipeline", "pothole", "transformer", "hospital", "school", "garbage", "water", "road", "light"]
    score += sum(11 for keyword in critical if keyword in text)
    score += sum(6 for keyword in high if keyword in text)
    score += min(int(upvotes or 0) * 2, 24)
    if emergency or category in ["fire", "health", "safety"]:
        score += 28
    if escalated:
        score += 12
    return max(1, min(score, 100))


def sla_hours(priority, emergency=False):
    if emergency or priority >= 90:
        return 6
    if priority >= 70:
        return 24
    if priority >= 45:
        return 48
    return 72


def sla_label(row):
    if row["status"] == "Resolved":
        return "Completed"
    if row["escalated"]:
        return "Escalated"
    deadline = parse_dt(row["sla_deadline"])
    if not deadline:
        return "On Track"
    remaining = deadline - datetime.now()
    if remaining.total_seconds() < 0:
        return "Overdue"
    if remaining <= timedelta(hours=6):
        return "Due Soon"
    return "On Track"


def get_worker(worker_id):
    return next((worker for worker in WORKERS if worker["id"] == worker_id), None)


def worker_label(worker_id):
    worker = get_worker(worker_id)
    return f"{worker['id']} · {worker['name']}" if worker else (worker_id or "Unassigned")


def workers_by_department():
    grouped = {key: [] for key in DEPARTMENTS}
    for worker in WORKERS:
        grouped.setdefault(worker["department"], []).append(worker)
    return grouped


def worker_active_task(con, worker_id, exclude_complaint_id=None):
    sql = "SELECT * FROM complaints WHERE assigned_worker=? AND status IN ('Assigned','In Progress')"
    params = [worker_id]
    if exclude_complaint_id is not None:
        sql += " AND id!=?"
        params.append(exclude_complaint_id)
    sql += " ORDER BY emergency DESC, escalated DESC, priority DESC, id ASC LIMIT 1"
    return con.execute(sql, params).fetchone()


def worker_skill_score(worker, required_skill):
    if not required_skill:
        return 0
    required = required_skill.lower()
    score = 0
    for skill in worker.get("skills", []):
        skill_l = skill.lower()
        if required in skill_l or skill_l in required:
            score += 30
        elif any(token in skill_l for token in required.split() if len(token) > 3):
            score += 8
    return score


def select_best_worker(con, department, required_skill=None, exclude_complaint_id=None, emergency=False, priority=0):
    """Select an idle team while protecting emergency reserve capacity.

    One team still receives only one unresolved complaint. For departments with at
    least two configured teams, CivicOS keeps the final idle team in reserve for
    emergencies/critical work instead of spending the last operational resource.
    """
    candidates = []
    dept_workers = [w for w in WORKERS if w["department"] == department and w.get("available", True)]
    for worker in dept_workers:
        if worker_active_task(con, worker["id"], exclude_complaint_id):
            continue
        candidates.append((worker_skill_score(worker, required_skill), worker["id"], worker))
    if not candidates:
        return None

    reserve_enabled = get_setting(con, "reserve_guard_enabled", "1") == "1"
    disaster_mode = get_setting(con, "disaster_mode", "0") == "1"
    is_critical = bool(emergency) or int(priority or 0) >= 85
    # In disaster mode, non-critical automatic assignments are intentionally
    # conservative so emergency capacity survives a sudden surge.
    protected_slots = 1 if reserve_enabled and len(dept_workers) >= 2 else 0
    if disaster_mode and len(dept_workers) >= 3:
        protected_slots = max(protected_slots, 2)
    if protected_slots and len(candidates) <= protected_slots and not is_critical:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def reserve_assignment_blocked(con, department, worker_id, emergency=False, priority=0, exclude_complaint_id=None):
    """Return True when assigning this idle team would consume protected reserve.

    Manual authority assignment uses the same capacity principle as CivicOS auto
    routing. Critical/emergency work may consume reserve; routine work requires an
    explicit authority override when the final protected team would be used.
    """
    if not worker_id or get_setting(con, "reserve_guard_enabled", "1") != "1":
        return False
    dept_workers = [w for w in WORKERS if w["department"] == department and w.get("available", True)]
    if len(dept_workers) < 2:
        return False
    if bool(emergency) or int(priority or 0) >= 85:
        return False
    # If this worker is already attached to this complaint, changing status does
    # not consume additional capacity and should not be blocked.
    current_task = worker_active_task(con, worker_id, exclude_complaint_id=exclude_complaint_id)
    if current_task:
        return False
    idle_workers = [w for w in dept_workers if not worker_active_task(con, w["id"], exclude_complaint_id=exclude_complaint_id)]
    protected_slots = 1
    if get_setting(con, "disaster_mode", "0") == "1" and len(dept_workers) >= 3:
        protected_slots = 2
    return len(idle_workers) <= protected_slots


def save_file(field):
    file = request.files.get(field)
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Only PNG, JPG, JPEG and WEBP images are supported.")

    # Validate actual bytes instead of trusting the filename. This implementation
    # deliberately has no Pillow runtime dependency, making evidence uploads work
    # consistently on Python 3.11 through 3.14.
    try:
        file.stream.seek(0)
        header = file.stream.read(32)
        detected = _sniff_image_format(header)
        if not detected:
            raise ValueError("The uploaded file could not be verified as PNG, JPG/JPEG or WEBP.")
        expected = "jpeg" if extension in {"jpg", "jpeg"} else extension
        if detected != expected:
            raise ValueError("The image contents do not match the file extension. Please upload the original image file.")
        file.stream.seek(0, os.SEEK_END)
        byte_size = file.stream.tell()
        if byte_size < 256:
            raise ValueError("Evidence image is too small or empty. Upload a clear photo.")
        if byte_size > app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024):
            raise ValueError("Evidence image is too large. Use a file below 16 MB.")
        file.stream.seek(0)
    except (OSError, ValueError):
        try:
            file.stream.seek(0)
        except OSError:
            pass
        raise

    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", filename.rsplit(".", 1)[0])[:50] or "image"
    canonical_extension = "jpg" if detected == "jpeg" and extension == "jpg" else extension
    stored = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{stem}.{canonical_extension}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], stored))
    return stored


def add_timeline(con, cid, step, note, when=None):
    con.execute(
        "INSERT INTO timeline(complaint_id,step,note,created_at) VALUES(?,?,?,?)",
        (cid, step, note, iso(when)),
    )


def create_notification(con, cid, title, message, kind="info", when=None):
    con.execute(
        "INSERT INTO notifications(complaint_id,title,message,kind,created_at,is_read) VALUES(?,?,?,?,?,0)",
        (cid, title, message, kind, iso(when)),
    )


def send_optional_email(cid, subject, message, html=None):
    """Best-effort complaint email. In-app notifications remain the fallback."""
    con = db()
    row = con.execute("SELECT email FROM complaints WHERE id=?", (cid,)).fetchone()
    con.close()
    if not row or not row["email"]:
        return False
    return send_email_to(row["email"], subject, message, html=html, purpose="complaint_update", complaint_id=cid)


def ensure_column(con, table, name, definition):
    columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if name not in columns:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def repair_worker_assignments(con):
    """Repair older demo databases before adding the single-active-task index."""
    duplicates = con.execute(
        """
        SELECT assigned_worker, COUNT(*) AS c
        FROM complaints
        WHERE assigned_worker IS NOT NULL AND TRIM(assigned_worker)!='' AND status IN ('Assigned','In Progress')
        GROUP BY assigned_worker
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for duplicate in duplicates:
        worker_id = duplicate["assigned_worker"]
        rows = con.execute(
            "SELECT * FROM complaints WHERE assigned_worker=? AND status IN ('Assigned','In Progress')",
            (worker_id,),
        ).fetchall()
        # Keep work already in progress first, then emergency/escalated/high-priority work.
        rows = sorted(
            rows,
            key=lambda row: (
                1 if row["status"] == "In Progress" else 0,
                int(row["emergency"] or 0),
                int(row["escalated"] or 0),
                int(row["priority"] or 0),
                -int(row["id"]),
            ),
            reverse=True,
        )
        for extra in rows[1:]:
            con.execute(
                "UPDATE complaints SET assigned_worker=NULL, assigned_at=NULL, status='Pending', updated_at=? WHERE id=?",
                (iso(), extra["id"]),
            )
            add_timeline(
                con,
                extra["id"],
                "Assignment Queue Correction",
                f"{worker_label(worker_id)} already had an active task. This complaint was safely returned to the queue.",
            )
    con.execute(
        "UPDATE complaints SET status='Assigned' WHERE assigned_worker IS NOT NULL AND TRIM(assigned_worker)!='' AND status='Pending'"
    )


def init_db():
    con = db()
    con.execute(
        """CREATE TABLE IF NOT EXISTS complaints(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            department TEXT NOT NULL,
            village TEXT NOT NULL,
            ward TEXT NOT NULL,
            location TEXT NOT NULL,
            address TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT DEFAULT 'Pending',
            priority INTEGER DEFAULT 10,
            emergency INTEGER DEFAULT 0,
            upvotes INTEGER DEFAULT 0,
            before_photo TEXT,
            after_photo TEXT,
            assigned_worker TEXT,
            admin_note TEXT,
            citizen_name TEXT,
            phone TEXT,
            phone_key TEXT,
            email TEXT,
            required_skill TEXT,
            created_at TEXT,
            updated_at TEXT,
            assigned_at TEXT,
            resolved_at TEXT,
            sla_deadline TEXT,
            sla_hours INTEGER,
            escalated INTEGER DEFAULT 0,
            routing_reason TEXT,
            duplicate_group TEXT
        )"""
    )
    for name, definition in [
        ("address", "TEXT"),
        ("phone_key", "TEXT"),
        ("email", "TEXT"),
        ("required_skill", "TEXT"),
        ("verification_score", "INTEGER DEFAULT 0"),
        ("verification_status", "TEXT DEFAULT 'Pending'"),
        ("citizen_confirmed", "INTEGER DEFAULT 0"),
        ("impact_score", "INTEGER DEFAULT 0"),
        ("impact_label", "TEXT"),
        ("citizen_user_id", "INTEGER"),
        ("worker_completion_requested_at", "TEXT"),
        ("admin_verified_at", "TEXT"),
        ("citizen_resolution", "TEXT DEFAULT 'Pending'"),
        ("resolution_cycle", "INTEGER DEFAULT 0"),
        ("reopen_requested", "INTEGER DEFAULT 0"),
        ("reopen_reason", "TEXT"),
        ("reopen_photo", "TEXT"),
        ("reopen_review_status", "TEXT"),
    ]:
        ensure_column(con, "complaints", name, definition)

    con.execute(
        """CREATE TABLE IF NOT EXISTS timeline(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER,
            step TEXT,
            note TEXT,
            created_at TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS feedback(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER,
            name TEXT,
            rating INTEGER,
            message TEXT,
            created_at TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )"""
    )
    for name, definition in [
        ("email", "TEXT"),
        ("full_name", "TEXT"),
        ("provider", "TEXT DEFAULT 'local'"),
        ("email_verified", "INTEGER DEFAULT 0"),
        ("resident_verified", "INTEGER DEFAULT 0"),
        ("village", "TEXT"),
        ("ward", "TEXT"),
        ("created_at", "TEXT"),
        ("worker_id", "TEXT"),
    ]:
        ensure_column(con, "users", name, definition)

    con.execute(
        """CREATE TABLE IF NOT EXISTS citizen_email_otps(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            consumed_at TEXT,
            created_at TEXT NOT NULL,
            last_sent_at TEXT NOT NULL
        )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_citizen_email_otps_user ON citizen_email_otps(user_id,id DESC)")

    # Demo worker identities are stored as hashed accounts so field teams can
    # authenticate independently from citizens and administrators. Existing
    # accounts are preserved. Change/reset these credentials before production.
    for worker in WORKERS:
        worker_id = worker["id"]
        username = default_worker_username(worker_id)
        existing_worker = con.execute(
            "SELECT id FROM users WHERE role='worker' AND worker_id=?", (worker_id,)
        ).fetchone()
        if not existing_worker:
            # Avoid colliding with an older account that may use the same username.
            if con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
                username = f"worker_{username}"
            con.execute(
                "INSERT INTO users(username,password,role,full_name,provider,email_verified,resident_verified,created_at,worker_id) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    username,
                    generate_password_hash(os.environ.get("CIVICOS_WORKER_DEFAULT_PASSWORD", "worker123")),
                    "worker",
                    worker.get("name") or worker_id,
                    "local",
                    1,
                    0,
                    iso(),
                    worker_id,
                ),
            )
    con.execute(
        """CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            kind TEXT DEFAULT 'info',
            created_at TEXT NOT NULL,
            is_read INTEGER DEFAULT 0
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS announcements(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            priority TEXT DEFAULT 'normal',
            created_by TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS complaint_votes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(complaint_id,user_id)
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS resolution_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            user_id INTEGER,
            worker_id TEXT,
            resolution_cycle INTEGER DEFAULT 1,
            verdict TEXT NOT NULL,
            rating INTEGER,
            feedback TEXT,
            reopen_reason TEXT,
            evidence_photo TEXT,
            review_status TEXT DEFAULT 'Recorded',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            UNIQUE(complaint_id,user_id,resolution_cycle)
        )"""
    )
    ensure_column(con, "resolution_reviews", "resolution_cycle", "INTEGER DEFAULT 1")
    con.execute(
        """CREATE TABLE IF NOT EXISTS email_deliveries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT,
            subject TEXT,
            purpose TEXT DEFAULT 'general',
            complaint_id INTEGER,
            user_id INTEGER,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS admin_accountability(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            evidence_photo TEXT,
            status TEXT DEFAULT 'Submitted',
            public_visible INTEGER DEFAULT 1,
            moderation_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER,
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS system_settings(
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS recovery_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            detected_at TEXT,
            restored_at TEXT,
            duration_ms REAL,
            trigger TEXT NOT NULL,
            records_before INTEGER DEFAULT 0,
            complaints_before INTEGER DEFAULT 0,
            inventory_before INTEGER DEFAULT 0,
            integrity_after TEXT,
            status TEXT DEFAULT 'Recovered',
            notes TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS sweep_missions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            departments TEXT,
            status TEXT DEFAULT 'Planned',
            created_by TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS sweep_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            complaint_id INTEGER NOT NULL,
            UNIQUE(mission_id, complaint_id),
            FOREIGN KEY(mission_id) REFERENCES sweep_missions(id) ON DELETE CASCADE
        )"""
    )
    con.execute(
        "INSERT OR IGNORE INTO system_settings(setting_key,setting_value) VALUES('civic_area_name','Live location')"
    )
    con.execute(
        "INSERT OR IGNORE INTO system_settings(setting_key,setting_value) VALUES('map_default_lat','20.5937')"
    )
    con.execute(
        "INSERT OR IGNORE INTO system_settings(setting_key,setting_value) VALUES('map_default_lon','78.9629')"
    )
    con.execute(
        "INSERT OR IGNORE INTO system_settings(setting_key,setting_value) VALUES('reserve_guard_enabled','1')"
    )
    con.execute(
        "INSERT OR IGNORE INTO system_settings(setting_key,setting_value) VALUES('disaster_mode','0')"
    )

    # Fill backward-compatible fields in existing databases.
    con.execute("UPDATE complaints SET address=location WHERE address IS NULL OR TRIM(address)=''")
    rows = con.execute("SELECT id,phone,phone_key FROM complaints").fetchall()
    for row in rows:
        normalized = normalize_phone(row["phone"])
        if normalized and row["phone_key"] != normalized:
            con.execute("UPDATE complaints SET phone_key=? WHERE id=?", (normalized, row["id"]))

    if con.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'").fetchone()["c"] == 0:
        initial_admin = os.environ.get("CIVICOS_ADMIN_USERNAME", "admin").strip() or "admin"
        initial_password = os.environ.get("CIVICOS_ADMIN_PASSWORD", "admin123")
        con.execute(
            "INSERT INTO users(username,password,role) VALUES(?,?,?)",
            (initial_admin, generate_password_hash(initial_password), "admin"),
        )

    repair_worker_assignments(con)
    con.execute("CREATE INDEX IF NOT EXISTS idx_complaints_phone_key ON complaints(phone_key)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_complaints_status_priority ON complaints(status, priority DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_complaint ON notifications(complaint_id, id DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_complaints_geo ON complaints(latitude, longitude)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_sweep_items_complaint ON sweep_items(complaint_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_votes_complaint ON complaint_votes(complaint_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_reviews_complaint ON resolution_reviews(complaint_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_audit_complaint ON audit_log(complaint_id,id DESC)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_citizen_email ON users(email) WHERE email IS NOT NULL AND TRIM(email)!=''")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_worker_id ON users(worker_id) WHERE role='worker' AND worker_id IS NOT NULL AND TRIM(worker_id)!=''")
    con.execute("CREATE INDEX IF NOT EXISTS idx_email_deliveries_created ON email_deliveries(id DESC)")
    # A field team may hold one actively executing task. Once completion proof is submitted,
    # the case moves to authority QA and the field team can receive the next assignment.
    con.execute("DROP INDEX IF EXISTS ux_worker_one_active_task")
    con.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_one_active_task
           ON complaints(assigned_worker)
           WHERE assigned_worker IS NOT NULL AND TRIM(assigned_worker)!='' AND status IN ('Assigned','In Progress')"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS assets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_uid TEXT UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            department TEXT NOT NULL,
            ward TEXT NOT NULL,
            village TEXT NOT NULL,
            location TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            status TEXT DEFAULT 'Operational',
            condition_score INTEGER DEFAULT 100,
            install_date TEXT,
            last_inspection_date TEXT,
            next_maintenance_due TEXT,
            estimated_value REAL DEFAULT 0,
            replacement_cost REAL DEFAULT 0,
            specifications TEXT,
            photo TEXT,
            assigned_worker TEXT,
            qr_code_token TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    # Backward-compatible asset migrations for databases created by earlier CivicOS versions.
    for name, definition in [
        ("asset_uid", "TEXT"), ("name", "TEXT"), ("category", "TEXT"), ("department", "TEXT"),
        ("ward", "TEXT"), ("village", "TEXT"), ("location", "TEXT"), ("latitude", "REAL"),
        ("longitude", "REAL"), ("status", "TEXT DEFAULT 'Operational'"), ("condition_score", "INTEGER DEFAULT 100"),
        ("install_date", "TEXT"), ("last_inspection_date", "TEXT"), ("next_maintenance_due", "TEXT"),
        ("estimated_value", "REAL DEFAULT 0"), ("replacement_cost", "REAL DEFAULT 0"),
        ("specifications", "TEXT"), ("photo", "TEXT"), ("assigned_worker", "TEXT"),
        ("qr_code_token", "TEXT"), ("notes", "TEXT"), ("created_at", "TEXT"), ("updated_at", "TEXT"),
    ]:
        ensure_column(con, "assets", name, definition)

    con.execute(
        """CREATE TABLE IF NOT EXISTS asset_maintenance_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            maintenance_type TEXT,
            performed_by TEXT,
            cost REAL DEFAULT 0,
            notes TEXT,
            status_after TEXT,
            condition_after INTEGER,
            performed_at TEXT,
            complaint_id INTEGER,
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
        )"""
    )
    ensure_column(con, "complaints", "asset_id", "INTEGER")
    ensure_column(con, "asset_maintenance_logs", "complaint_id", "INTEGER")
    con.execute("CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_assets_ward ON assets(ward)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_assets_geo ON assets(latitude, longitude)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_maint_asset ON asset_maintenance_logs(asset_id)")

    # Seed demo assets if table is empty
    if con.execute("SELECT COUNT(*) AS c FROM assets").fetchone()["c"] == 0:
        for item in get_demo_assets_seed():
            con.execute(
                """INSERT OR IGNORE INTO assets(
                    asset_uid, name, category, department, ward, village, location,
                    latitude, longitude, status, condition_score, install_date,
                    last_inspection_date, next_maintenance_due, estimated_value,
                    replacement_cost, specifications, assigned_worker, notes,
                    created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item["asset_uid"], item["name"], item["category"], item["department"],
                    item["ward"], item["village"], item["location"], item["latitude"],
                    item["longitude"], item["status"], item["condition_score"],
                    item["install_date"], item["last_inspection_date"], item["next_maintenance_due"],
                    item["estimated_value"], item["replacement_cost"], item["specifications"],
                    item.get("assigned_worker"), item.get("notes"), iso(), iso()
                )
            )
        a_first = con.execute("SELECT id FROM assets WHERE asset_uid='AST-ROD-001'").fetchone()
        if a_first:
            con.execute(
                """INSERT INTO asset_maintenance_logs(asset_id, maintenance_type, performed_by, cost, notes, status_after, condition_after, performed_at)
                   VALUES(?, 'Routine Inspection', 'Road Repair Team 01', 0, 'Surface profile audit completed. No major cracks observed.', 'Operational', 88, ?)""",
                (a_first["id"], iso())
            )
        a_second = con.execute("SELECT id FROM assets WHERE asset_uid='AST-WTR-108'").fetchone()
        if a_second:
            con.execute(
                """INSERT INTO asset_maintenance_logs(asset_id, maintenance_type, performed_by, cost, notes, status_after, condition_after, performed_at)
                   VALUES(?, 'Preventive Maintenance', 'Water Field Team 01', 12500, 'Replaced joint gaskets and lubricated valve bypass.', 'Operational', 91, ?)""",
                (a_second["id"], iso())
            )

    con.commit()
    con.close()




def init_trust_db():
    """Create CivicOS Trust & Verification tables and safe hackathon demo records."""
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS truth_bulletins(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'civic',
            claim_summary TEXT NOT NULL,
            verdict TEXT NOT NULL DEFAULT 'Official Update',
            fact_text TEXT NOT NULL,
            official_source TEXT,
            evidence_url TEXT,
            keywords TEXT,
            public_visible INTEGER DEFAULT 1,
            is_demo INTEGER DEFAULT 0,
            created_by TEXT,
            published_at TEXT NOT NULL,
            expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS misinformation_reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_text TEXT NOT NULL,
            category TEXT DEFAULT 'other',
            source_channel TEXT DEFAULT 'Other',
            source_url TEXT,
            reporter_user_id INTEGER,
            reporter_name TEXT,
            status TEXT DEFAULT 'Submitted',
            auto_match_id INTEGER,
            auto_match_confidence REAL DEFAULT 0,
            verdict TEXT DEFAULT 'Unverified',
            review_note TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT
        );
        CREATE TABLE IF NOT EXISTS complaint_trust_assessments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL UNIQUE,
            risk_score INTEGER NOT NULL DEFAULT 0,
            risk_label TEXT NOT NULL DEFAULT 'Low Risk',
            signals_json TEXT,
            similar_complaints_json TEXT,
            public_visibility TEXT DEFAULT 'Normal',
            reviewer_status TEXT DEFAULT 'Automated',
            review_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_truth_public ON truth_bulletins(public_visible,published_at);
        CREATE INDEX IF NOT EXISTS idx_misinfo_status ON misinformation_reports(status,created_at);
        CREATE INDEX IF NOT EXISTS idx_trust_risk ON complaint_trust_assessments(risk_score,reviewer_status);
        """
    )
    if con.execute("SELECT COUNT(*) AS c FROM truth_bulletins").fetchone()["c"] == 0:
        demo_source = "CivicOS Hackathon Demo Authority Feed"
        demo = [
            (
                "DEMO · Kisan Support Grant deadline rumor",
                "scheme",
                "A forwarded message claims the local Kisan Support Grant closes tonight and farmers should withdraw if they cannot pay a processing fee.",
                "False",
                "Demo correction: CivicOS has no authority notice announcing an emergency closure or paid withdrawal requirement. Verify scheme deadlines only through the responsible government office or its official portal before acting.",
                demo_source,
                "kisan grant subsidy closes tonight fee withdraw farmer scheme whatsapp",
            ),
            (
                "DEMO · Ward 4 water safety message",
                "water",
                "A WhatsApp post says all Ward 4 water samples are safe after a contamination complaint.",
                "Misleading",
                "Demo correction: a clearance for one sample point does not automatically clear an entire ward. The authority should publish the tested location, sample time and lab status before a broad safety claim is shared.",
                demo_source,
                "water safe ward 4 contamination sample lab whatsapp",
            ),
            (
                "DEMO · Community health-screening result rumor",
                "health",
                "A message says a screening camp found every participant disease-free and no follow-up is required.",
                "False",
                "Demo correction: screening is not a universal diagnosis. Individual results and follow-up instructions must come from the authorized health provider; a forwarded group message cannot replace them.",
                demo_source,
                "health screening result disease free follow up camp whatsapp",
            ),
            (
                "DEMO · Bus route cancellation message",
                "transport",
                "A viral post claims the municipal Route 7 bus has been permanently cancelled.",
                "False",
                "Demo correction: no permanent cancellation is recorded in this demo authority feed. Citizens should check the latest transport bulletin before changing travel plans.",
                demo_source,
                "bus route 7 cancelled canceled transport viral whatsapp",
            ),
            (
                "DEMO · Food batch contamination warning",
                "food",
                "A forwarded alert says every batch from a local food supplier is contaminated.",
                "Unverified",
                "Demo guidance: contamination claims require a traceable batch number, test report or authorized recall notice. Until that evidence exists, CivicOS labels the broad claim unverified rather than amplifying it as fact.",
                demo_source,
                "food batch contaminated contamination recall supplier lab report",
            ),
        ]
        now = iso()
        con.executemany(
            """INSERT INTO truth_bulletins(
                title,category,claim_summary,verdict,fact_text,official_source,keywords,
                public_visible,is_demo,created_by,published_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            [(a,b,c,d,e,f,g,1,1,"System Demo",now) for a,b,c,d,e,f,g in demo],
        )
    con.commit()
    con.close()


def trust_match_claim(con, text):
    bulletins = con.execute(
        "SELECT * FROM truth_bulletins WHERE public_visible=1 ORDER BY id DESC"
    ).fetchall()
    match, confidence = find_best_bulletin_match(text, bulletins)
    # Do not manufacture certainty from a weak text match.
    if not match or confidence < 0.42:
        return {"matched": False, "confidence": confidence, "bulletin": None, "verdict": "Unverified"}
    return {
        "matched": True,
        "confidence": confidence,
        "bulletin": match,
        "verdict": match["verdict"],
    }


def trust_summary(con):
    return {
        "published": con.execute("SELECT COUNT(*) c FROM truth_bulletins WHERE public_visible=1").fetchone()["c"],
        "pending": con.execute("SELECT COUNT(*) c FROM misinformation_reports WHERE status IN ('Submitted','Under Review')").fetchone()["c"],
        "false": con.execute("SELECT COUNT(*) c FROM truth_bulletins WHERE public_visible=1 AND verdict='False'").fetchone()["c"],
        "misleading": con.execute("SELECT COUNT(*) c FROM truth_bulletins WHERE public_visible=1 AND verdict='Misleading'").fetchone()["c"],
        "high_risk": con.execute("SELECT COUNT(*) c FROM complaint_trust_assessments WHERE risk_score>=60 AND reviewer_status NOT IN ('Cleared','False Submission')").fetchone()["c"],
        "quarantined": con.execute("SELECT COUNT(*) c FROM complaint_trust_assessments WHERE public_visibility='Quarantined'").fetchone()["c"],
    }


def store_complaint_trust(con, complaint_id, assessment):
    visibility = "Quarantined" if assessment.get("auto_quarantine") else "Normal"
    reviewer_status = "Needs Review" if assessment.get("score", 0) >= 60 else "Automated"
    con.execute(
        """INSERT OR REPLACE INTO complaint_trust_assessments(
            complaint_id,risk_score,risk_label,signals_json,similar_complaints_json,
            public_visibility,reviewer_status,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            complaint_id,
            int(assessment.get("score",0)),
            assessment.get("label") or trust_label(assessment.get("score",0)),
            json.dumps(assessment.get("signals") or []),
            json.dumps(assessment.get("similar_ids") or []),
            visibility,
            reviewer_status,
            iso(),
            iso(),
        ),
    )


def ensure_complaint_trust(con, complaint):
    existing = con.execute(
        "SELECT * FROM complaint_trust_assessments WHERE complaint_id=?", (complaint["id"],)
    ).fetchone()
    if existing:
        return existing
    assessment = evaluate_submission(
        con,
        complaint["title"],
        complaint["description"],
        complaint["citizen_user_id"] if "citizen_user_id" in complaint.keys() else None,
        bool(complaint["before_photo"]),
        complaint["ward"],
        complaint["category"],
        exclude_id=complaint["id"],
    )
    store_complaint_trust(con, complaint["id"], assessment)
    return con.execute(
        "SELECT * FROM complaint_trust_assessments WHERE complaint_id=?", (complaint["id"],)
    ).fetchone()



def init_procurement_db():
    """Create and seed the CivicOS procurement + inventory control layer."""
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS inventory_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        category TEXT NOT NULL, department TEXT NOT NULL, unit TEXT DEFAULT 'units',
        on_hand REAL NOT NULL DEFAULT 0, reorder_level REAL NOT NULL DEFAULT 0,
        reorder_qty REAL NOT NULL DEFAULT 0, unit_cost REAL NOT NULL DEFAULT 0,
        warehouse TEXT DEFAULT 'Central Store', location TEXT, supplier_id INTEGER,
        batch_no TEXT, expiry_date TEXT, status TEXT DEFAULT 'Active',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(supplier_id) REFERENCES finance_vendors(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS procurement_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, request_no TEXT UNIQUE NOT NULL,
        requested_by TEXT NOT NULL, department TEXT NOT NULL, priority TEXT DEFAULT 'Normal',
        purpose TEXT NOT NULL, status TEXT DEFAULT 'Pending', total_estimate REAL DEFAULT 0,
        needed_by TEXT, vendor_id INTEGER, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(vendor_id) REFERENCES finance_vendors(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS procurement_request_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER NOT NULL, item_id INTEGER,
        item_name TEXT NOT NULL, qty REAL NOT NULL, estimated_unit_cost REAL DEFAULT 0,
        FOREIGN KEY(request_id) REFERENCES procurement_requests(id) ON DELETE CASCADE,
        FOREIGN KEY(item_id) REFERENCES inventory_items(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS purchase_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, po_no TEXT UNIQUE NOT NULL, request_id INTEGER,
        vendor_id INTEGER NOT NULL, department TEXT NOT NULL, status TEXT DEFAULT 'Draft',
        order_date TEXT NOT NULL, expected_date TEXT, subtotal REAL DEFAULT 0, tax REAL DEFAULT 0,
        total REAL DEFAULT 0, delivery_status TEXT DEFAULT 'Not Received', notes TEXT,
        created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(request_id) REFERENCES procurement_requests(id) ON DELETE SET NULL,
        FOREIGN KEY(vendor_id) REFERENCES finance_vendors(id) ON DELETE RESTRICT
    );
    CREATE TABLE IF NOT EXISTS purchase_order_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, po_id INTEGER NOT NULL, item_id INTEGER,
        item_name TEXT NOT NULL, qty REAL NOT NULL, unit_cost REAL DEFAULT 0, received_qty REAL DEFAULT 0,
        FOREIGN KEY(po_id) REFERENCES purchase_orders(id) ON DELETE CASCADE,
        FOREIGN KEY(item_id) REFERENCES inventory_items(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS stock_movements(
        id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, movement_type TEXT NOT NULL,
        qty REAL NOT NULL, reference_type TEXT, reference_id INTEGER, from_location TEXT, to_location TEXT,
        reason TEXT, actor TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(item_id) REFERENCES inventory_items(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_inventory_low ON inventory_items(on_hand,reorder_level);
    CREATE INDEX IF NOT EXISTS idx_pr_status ON procurement_requests(status);
    CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
    CREATE INDEX IF NOT EXISTS idx_stock_item ON stock_movements(item_id,created_at);
    """)
    now=iso()
    # Demo inventory is intentionally useful for the judge walkthrough.
    if con.execute("SELECT COUNT(*) c FROM inventory_items").fetchone()["c"]==0:
        seed=[
            ('INV-WTR-001','HDPE Pipe 110mm','Water','water','meters',420,150,500,185,'Central Store','Rack A-01',None,'LOT-W24','2027-06-30'),
            ('INV-ELC-014','LED Streetlight 90W','Electrical','electricity','units',34,20,50,3200,'Central Store','Rack B-03',None,'LED-26-14','2029-01-31'),
            ('INV-ROAD-022','Cold Mix Asphalt 25kg','Road Maintenance','road','bags',68,30,100,780,'Central Store','Yard C-02',None,'CM-2026-08','2027-08-31'),
            ('INV-HLT-008','PPE Safety Kit','Safety & Health','health','kits',12,25,60,1450,'Central Store','Rack D-04',None,'PPE-26-08','2028-08-31'),
            ('INV-FIR-003','Fire Hose 30m','Emergency','fire','units',18,8,20,6100,'Emergency Depot','Bay E-01',None,'FH-2026','2031-12-31'),
        ]
        con.executemany("""INSERT INTO inventory_items
          (sku,name,category,department,unit,on_hand,reorder_level,reorder_qty,unit_cost,warehouse,location,supplier_id,batch_no,expiry_date,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",[x+(now,now) for x in seed])
    if con.execute("SELECT COUNT(*) c FROM procurement_requests").fetchone()["c"]==0:
        cur=con.execute("""INSERT INTO procurement_requests
          (request_no,requested_by,department,priority,purpose,status,total_estimate,needed_by,notes,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",('PR-2026-0001','Water Field Team','water','High','Emergency stock replenishment for leak response','Pending',92500,(datetime.now()+timedelta(days=10)).strftime('%Y-%m-%d'),'Auto-created from low-stock demonstration',now,now))
        rid=cur.lastrowid
        item=con.execute("SELECT id,name,unit_cost FROM inventory_items WHERE sku='INV-WTR-001'").fetchone()
        con.execute("INSERT INTO procurement_request_items(request_id,item_id,item_name,qty,estimated_unit_cost) VALUES(?,?,?,?,?)",(rid,item['id'],item['name'],500,item['unit_cost']))
    con.commit(); con.close()

def finance_validate_amount(raw):
    try:
        amount=float(raw)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid amount.")
    if amount <= 0 or amount > 1_000_000_000_000:
        raise ValueError("Amount must be greater than zero and within a safe limit.")
    return round(amount,2)


def finance_parse_date(raw):
    raw=(raw or "").strip()
    try:
        datetime.strptime(raw,"%Y-%m-%d")
        return raw
    except ValueError:
        raise ValueError("Use a valid transaction date.")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            flash(t("login_required"), "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


PROCUREMENT_DEPARTMENTS=dict(DEPARTMENTS)
PROCUREMENT_PRIORITIES=('Low','Normal','High','Critical')
PROCUREMENT_REQUEST_STATUSES=('Pending','Approved','Rejected','Converted')
PO_STATUSES=('Draft','Issued','Partially Received','Received','Cancelled')

def procurement_ref(con,prefix,table,col):
    y=datetime.now().strftime('%Y')
    row=con.execute(f"SELECT {col} x FROM {table} WHERE {col} LIKE ? ORDER BY id DESC LIMIT 1",(f'{prefix}-{y}-%',)).fetchone()
    n=int(str(row['x']).split('-')[-1])+1 if row else 1
    return f'{prefix}-{y}-{n:04d}'


def procurement_summary(con):
    inv=con.execute("SELECT COUNT(*) c,COALESCE(SUM(on_hand*unit_cost),0) value FROM inventory_items WHERE status='Active'").fetchone()
    low=con.execute("SELECT COUNT(*) c FROM inventory_items WHERE status='Active' AND on_hand<=reorder_level").fetchone()['c']
    pending=con.execute("SELECT COUNT(*) c FROM procurement_requests WHERE status='Pending'").fetchone()['c']
    open_po=con.execute("SELECT COUNT(*) c FROM purchase_orders WHERE status IN ('Issued','Partially Received')").fetchone()['c']
    po_value=con.execute("SELECT COALESCE(SUM(total),0) x FROM purchase_orders WHERE status NOT IN ('Cancelled') AND order_date>=?",(f'{datetime.now().year}-01-01',)).fetchone()['x']
    return {'sku_count':inv['c'],'stock_value':inv['value'],'low_stock':low,'pending_requests':pending,'open_pos':open_po,'po_value':po_value}

def load_integration_config():
    """Load local admin-entered integration settings.

    Real environment variables always take precedence. This file is intended for
    local/hackathon laptops so SMTP and citizen email OTP delivery can be configured from the
    Command Center without editing shell environment variables. It is git-ignored.
    """
    try:
        with open(INTEGRATION_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}

def integration_value(env_key, config_key=None, default=""):
    env_value = os.environ.get(env_key)
    if env_value is not None and str(env_value).strip() != "":
        return str(env_value).strip()
    config = load_integration_config()
    value = config.get(config_key or env_key.lower(), default)
    return str(value).strip() if value is not None else str(default)

def save_integration_config(updates):
    current = load_integration_config()
    current.update(updates)
    tmp_path = INTEGRATION_CONFIG_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2)
    os.replace(tmp_path, INTEGRATION_CONFIG_PATH)

def issue_captcha():
    """Create a tiny server-side CAPTCHA that works offline during demos."""
    a = secrets.randbelow(8) + 2
    b = secrets.randbelow(8) + 2
    session["citizen_captcha_answer"] = str(a + b)
    return f"{a} + {b} = ?"

def validate_captcha(answer):
    expected = session.pop("citizen_captcha_answer", None)
    return bool(expected and secrets.compare_digest(str(answer or "").strip(), expected))

def current_citizen():
    citizen_id = session.get("citizen_id")
    if not citizen_id:
        return None
    con = db()
    row = con.execute("SELECT * FROM users WHERE id=? AND role='citizen'", (citizen_id,)).fetchone()
    con.close()
    return row

def current_worker_account():
    worker_user_id = session.get("worker_user_id")
    worker_id = session.get("worker_id")
    if not worker_user_id or not worker_id:
        return None
    con = db()
    row = con.execute(
        "SELECT * FROM users WHERE id=? AND role='worker' AND worker_id=?",
        (worker_user_id, worker_id),
    ).fetchone()
    con.close()
    return row

def worker_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        account = current_worker_account()
        if not account:
            session.pop("worker_user_id", None)
            session.pop("worker_id", None)
            flash("Worker sign-in is required to open the field-work portal.", "warning")
            return redirect(url_for("worker_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def citizen_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("citizen_id"):
            flash("Sign in with a Civic Account to use this citizen service. SOS remains available without login.", "warning")
            return redirect(url_for("citizen_login", next=request.full_path if request.query_string else request.path))
        return fn(*args, **kwargs)
    return wrapper

def verified_participation_required(fn):
    """Require a verified email for actions that carry civic weight.

    Reporting and emergency access stay inclusive, but votes, community validation
    and administrative-accountability submissions should not be driven by throwaway
    unverified accounts. Municipal resident verification remains a separate layer.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("citizen_id"):
            flash("Sign in with a Civic Account to use this citizen service.", "warning")
            return redirect(url_for("citizen_login", next=request.full_path if request.query_string else request.path))
        citizen = current_citizen()
        if not citizen or not citizen["email_verified"]:
            flash("Verify your account email before voting, community-verifying work or filing an accountability report.", "warning")
            return redirect(url_for("citizen_profile"))
        return fn(*args, **kwargs)
    return wrapper

def email_verification_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="civicos-citizen-email-verification-v1")

def make_email_verification_token(user_id, email):
    return email_verification_serializer().dumps({"uid": int(user_id), "email": (email or "").strip().lower()})

def read_email_verification_token(token, max_age=60 * 60 * 24):
    try:
        return email_verification_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

def resolution_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="civicos-resolution-verification-v1")

def make_resolution_token(cid, email):
    return resolution_serializer().dumps({"cid": int(cid), "email": (email or "").lower().strip()})

def read_resolution_token(token, max_age=60 * 60 * 24 * 14):
    try:
        return resolution_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

def public_base_url():
    configured = integration_value("CIVICOS_PUBLIC_URL", "public_url", "").rstrip("/")
    if configured:
        return configured
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return "http://127.0.0.1:5000"

def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return radius * 2 * atan2(sqrt(a), sqrt(max(0.0, 1 - a)))

def audit_action(con, action, details, complaint_id=None, actor_type=None, actor_id=None):
    if actor_type is None:
        if session.get("admin"):
            actor_type, actor_id = "admin", session.get("admin")
        elif session.get("citizen_id"):
            actor_type, actor_id = "citizen", str(session.get("citizen_id"))
        else:
            actor_type, actor_id = "system", "system"
    con.execute(
        "INSERT INTO audit_log(complaint_id,actor_type,actor_id,action,details,created_at) VALUES(?,?,?,?,?,?)",
        (complaint_id, actor_type, actor_id, action, details, iso()),
    )

def default_worker_username(worker_id):
    return re.sub(r"[^a-z0-9]", "", (worker_id or "").lower())

def _sniff_image_format(header):
    """Return png/jpeg/webp from magic bytes without requiring Pillow.

    CivicOS previously imported Pillow inside save_file(). On machines where Pillow
    was missing or incompatible (notably some Python 3.14 setups), that import could
    fail and then the exception handler itself referenced UnidentifiedImageError,
    causing the UnboundLocalError shown by Flask. Header validation avoids that
    dependency while still rejecting renamed non-image files.
    """
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None

def record_email_delivery(recipient, subject, purpose, status, error="", complaint_id=None, user_id=None):
    """Best-effort delivery audit. Email problems must never crash the civic workflow."""
    try:
        con = db()
        con.execute(
            "INSERT INTO email_deliveries(recipient,subject,purpose,complaint_id,user_id,status,error,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (recipient, subject, purpose or "general", complaint_id, user_id, status, (error or "")[:500], iso()),
        )
        con.commit()
        con.close()
    except sqlite3.Error:
        pass

def send_email_to(recipient, subject, message, html=None, purpose="general", complaint_id=None, user_id=None):
    """Send SMTP mail, log delivery status, and retain a useful admin diagnostic."""
    recipient = (recipient or "").strip()
    host = integration_value("SMTP_HOST", "smtp_host", "")
    if not recipient:
        app.config["LAST_EMAIL_ERROR"] = "Recipient address is empty."
        record_email_delivery(recipient, subject, purpose, "Failed", app.config["LAST_EMAIL_ERROR"], complaint_id, user_id)
        return False
    if not host:
        app.config["LAST_EMAIL_ERROR"] = "SMTP server is not configured. Open Command Center → Settings → Email & OTP Setup."
        record_email_delivery(recipient, subject, purpose, "Failed", app.config["LAST_EMAIL_ERROR"], complaint_id, user_id)
        return False

    try:
        port = int(integration_value("SMTP_PORT", "smtp_port", "587") or "587")
    except ValueError:
        app.config["LAST_EMAIL_ERROR"] = "SMTP port must be a number (Gmail normally uses 587)."
        record_email_delivery(recipient, subject, purpose, "Failed", app.config["LAST_EMAIL_ERROR"], complaint_id, user_id)
        return False
    username = integration_value("SMTP_USERNAME", "smtp_username", "")
    password = integration_value("SMTP_PASSWORD", "smtp_password", "")
    if "gmail.com" in host.lower() and password:
        password = password.replace(" ", "")
    sender = integration_value("SMTP_FROM", "smtp_from", username or "civicos@example.com")
    mode = integration_value("SMTP_SECURITY", "smtp_security", "starttls").lower() or "starttls"
    if os.environ.get("SMTP_USE_TLS", "1") == "0" and not integration_value("SMTP_SECURITY", "smtp_security", ""):
        mode = "none"

    mail = EmailMessage()
    mail["From"] = sender
    mail["To"] = recipient
    mail["Subject"] = subject
    mail.set_content(message)
    if html:
        mail.add_alternative(html, subtype="html")

    try:
        if mode in {"ssl", "smtps"} or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(mail)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.ehlo()
                if mode == "starttls":
                    smtp.starttls()
                    smtp.ehlo()
                if username:
                    smtp.login(username, password)
                smtp.send_message(mail)
        app.config["LAST_EMAIL_ERROR"] = ""
        record_email_delivery(recipient, subject, purpose, "Delivered", "", complaint_id, user_id)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        detail = f"{type(exc).__name__}: {exc}"
        app.config["LAST_EMAIL_ERROR"] = detail[:500]
        record_email_delivery(recipient, subject, purpose, "Failed", detail, complaint_id, user_id)
        app.logger.warning("CivicOS email delivery failed for %s: %s", recipient, exc)
        return False

def local_otp_fallback_allowed():
    """Allow a visible OTP fallback only on a local hackathon/dev machine.

    This is deliberately blocked on normal deployed hosts unless the operator
    explicitly opts in with CIVICOS_ALLOW_LOCAL_OTP=1. It keeps the demo
    usable when SMTP is temporarily unavailable without weakening production.
    """
    explicit = os.environ.get("CIVICOS_ALLOW_LOCAL_OTP")
    if explicit is not None:
        return explicit.strip() == "1"
    try:
        host = (request.host or "").split(":", 1)[0].lower()
    except RuntimeError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}

def set_local_demo_otp(user_id, otp):
    if not local_otp_fallback_allowed():
        return False
    session["civicos_demo_otp"] = str(otp)
    session["civicos_demo_otp_user_id"] = int(user_id)
    session["civicos_demo_otp_expires"] = iso(datetime.now() + timedelta(minutes=10))
    return True

def clear_local_demo_otp():
    session.pop("civicos_demo_otp", None)
    session.pop("civicos_demo_otp_user_id", None)
    session.pop("civicos_demo_otp_expires", None)

def current_local_demo_otp(user_id):
    try:
        if int(session.get("civicos_demo_otp_user_id") or 0) != int(user_id):
            return None
    except (TypeError, ValueError):
        return None
    expires = parse_dt(session.get("civicos_demo_otp_expires"))
    if not expires or datetime.now() > expires:
        clear_local_demo_otp()
        return None
    return session.get("civicos_demo_otp")

def send_citizen_email_otp(user_id, force=False):
    """Send a six-digit OTP to verify a Civic Account email.

    Real SMTP delivery is always attempted first. On localhost only, a clearly
    labelled demo OTP is exposed if SMTP fails so a hackathon demo is never
    blocked by Wi-Fi/Gmail configuration.
    """
    con = db()
    user = con.execute(
        "SELECT id,email,full_name,email_verified FROM users WHERE id=? AND role='citizen'",
        (user_id,),
    ).fetchone()
    if not user or not user["email"]:
        con.close()
        app.config["LAST_EMAIL_ERROR"] = "Citizen account has no email address."
        return False
    if user["email_verified"]:
        con.close()
        return True
    latest = con.execute(
        "SELECT * FROM citizen_email_otps WHERE user_id=? AND consumed_at IS NULL ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if latest and not force:
        last_sent = parse_dt(latest["last_sent_at"])
        if last_sent and datetime.now() - last_sent < timedelta(seconds=60):
            con.close()
            app.config["LAST_EMAIL_ERROR"] = "Please wait 60 seconds before requesting another OTP."
            return False
    otp = f"{secrets.randbelow(900000) + 100000:06d}"
    now = datetime.now()
    expires = now + timedelta(minutes=10)
    con.execute(
        "INSERT INTO citizen_email_otps(user_id,otp_hash,expires_at,attempts,consumed_at,created_at,last_sent_at) VALUES(?,?,?,?,?,?,?)",
        (user_id, generate_password_hash(otp), iso(expires), 0, None, iso(now), iso(now)),
    )
    con.commit(); con.close()
    safe_name = html_lib.escape(user["full_name"] or "Citizen")
    subject = f"{otp} is your CivicOS verification code"
    text = (f"Hello {user['full_name'] or 'Citizen'},\n\nYour CivicOS verification code is: {otp}\n\n"
            "This code expires in 10 minutes. Do not share it with anyone.\n\nCivicOS")
    html = f"""<!doctype html><html><body style='font-family:Arial,sans-serif;background:#f4f7fb;padding:24px;color:#172131'>
    <div style='max-width:620px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden'>
      <div style='background:#071f38;color:#fff;padding:22px 26px'><div style='font-size:23px;font-weight:800'>CivicOS</div><div style='opacity:.78;margin-top:4px'>Citizen email verification</div></div>
      <div style='padding:26px'><p>Hello <b>{safe_name}</b>,</p><h2>Verify your Civic Account</h2>
      <p>Enter this one-time code in CivicOS:</p>
      <div style='font-size:34px;letter-spacing:8px;font-weight:800;background:#eef4ff;border-radius:12px;padding:18px;text-align:center;margin:22px 0'>{otp}</div>
      <p style='font-size:13px;color:#6b7280'>Expires in 10 minutes. Do not share this code.</p></div></div></body></html>"""
    delivered = send_email_to(user["email"], subject, text, html=html, purpose="citizen_email_otp", user_id=user["id"])
    if delivered:
        clear_local_demo_otp()
        return True
    # Local-only continuity fallback. Never expose OTPs on deployed hosts by default.
    if set_local_demo_otp(user["id"], otp):
        original_error = app.config.get("LAST_EMAIL_ERROR") or "SMTP delivery failed."
        app.config["LAST_EMAIL_ERROR"] = (
            f"{original_error} Local hackathon fallback is active; use the demo OTP shown on the verification page."
        )[:500]
    return False

def send_citizen_email_verification(user_id):
    con = db()
    user = con.execute("SELECT id,email,full_name,email_verified FROM users WHERE id=? AND role='citizen'", (user_id,)).fetchone()
    con.close()
    if not user or not user["email"] or user["email_verified"]:
        return bool(user and user["email_verified"])
    token = make_email_verification_token(user["id"], user["email"])
    verify_url = f"{public_base_url()}/citizen/verify-email/{token}"
    safe_name = html_lib.escape(user["full_name"] or "Citizen")
    safe_url = html_lib.escape(verify_url, quote=True)
    text = (
        f"Hello {user['full_name'] or 'Citizen'},\n\n"
        "Verify the email attached to your CivicOS Civic Account. Verified email is required for weighted civic participation such as upvotes, community resolution verification and administration accountability reports.\n\n"
        f"Verify email: {verify_url}\n\nThis link expires after 24 hours.\n\nCivicOS"
    )
    html = f"""<!doctype html><html><body style='font-family:Arial,sans-serif;background:#f4f7fb;padding:24px;color:#172131'>
    <div style='max-width:620px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden'>
      <div style='background:#071f38;color:#fff;padding:22px 26px'><div style='font-size:23px;font-weight:800'>CivicOS</div><div style='opacity:.78;margin-top:4px'>Civic Account email verification</div></div>
      <div style='padding:26px'><p>Hello <b>{safe_name}</b>,</p><h2>Verify your Civic Account email</h2><p style='line-height:1.6'>Email verification helps CivicOS enforce one-account-one-action participation. Municipal resident verification remains a separate governance check.</p><p style='margin:26px 0'><a href='{safe_url}' style='display:inline-block;background:#1768d8;color:#fff;text-decoration:none;padding:13px 18px;border-radius:9px;font-weight:700'>Verify My Email</a></p><p style='font-size:13px;color:#6b7280'>This secure link expires in 24 hours.</p></div>
    </div></body></html>"""
    return send_email_to(
        user["email"],
        "Verify your CivicOS Civic Account email",
        text,
        html=html,
        purpose="citizen_email_verification",
        user_id=user["id"],
    )

def send_resolution_email(cid):
    con = db()
    row = con.execute("SELECT id,title,email,citizen_name,assigned_worker,resolution_cycle FROM complaints WHERE id=?", (cid,)).fetchone()
    con.close()
    if not row or not row["email"]:
        return False
    token = make_resolution_token(cid, row["email"])
    verify_url = f"{public_base_url()}/resolution-review/{token}"
    worker_name = worker_label(row["assigned_worker"])
    safe_name = html_lib.escape(row["citizen_name"] or "Citizen")
    safe_title = html_lib.escape(row["title"] or "Civic issue")
    safe_worker = html_lib.escape(worker_name)
    subject = f"CivicOS #{cid}: please verify the completed civic work"
    text = (
        f"Hello {row['citizen_name'] or 'Citizen'},\n\n"
        f"The authority has marked complaint #{cid} as RESOLVED after reviewing the field team's completion proof: {row['title']}.\n"
        f"Field team: {worker_name}\n\n"
        "Please verify whether the issue is actually resolved, rate the work, and provide feedback. "
        "If the problem remains, you can request reopening with fresh photo evidence.\n\n"
        f"Verify resolution: {verify_url}\n\n"
        "This verification link expires after 14 days.\n\nCivicOS"
    )
    html = f'''<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f4f7fb;padding:24px;color:#172131">
    <div style="max-width:620px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden">
      <div style="background:#071f38;color:#fff;padding:22px 26px"><div style="font-size:23px;font-weight:800">CivicOS</div><div style="opacity:.78;margin-top:4px">Citizen resolution verification</div></div>
      <div style="padding:26px"><p>Hello <b>{safe_name}</b>,</p>
      <h2 style="margin:8px 0 10px">Complaint #{cid} was marked RESOLVED by the authority</h2>
      <p style="line-height:1.6;color:#536174">{safe_title}</p>
      <p style="line-height:1.6;color:#536174">Field team: <b>{safe_worker}</b></p>
      <p style="line-height:1.6">CivicOS does not close the accountability loop until you verify the real-world outcome.</p>
      <p style="margin:26px 0"><a href="{verify_url}" style="display:inline-block;background:#1768d8;color:#fff;text-decoration:none;padding:13px 18px;border-radius:9px;font-weight:700">Confirm Resolution & Give Feedback</a></p>
      <p style="font-size:13px;color:#6b7280;line-height:1.5">If the issue is still present, use the same page to request reopening. Fresh photo evidence is required to reduce false reopen requests. This secure link expires in 14 days.</p></div>
    </div></body></html>'''
    return send_email_to(
        row["email"],
        subject,
        text,
        html=html,
        purpose="resolution_verification",
        complaint_id=cid,
    )

@app.route("/citizen/login", methods=["GET", "POST"])
def citizen_login():
    if session.get("citizen_id"):
        return redirect(url_for("index"))
    captcha_question = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not validate_captcha(request.form.get("captcha")):
            flash("CAPTCHA verification failed. Please try the new challenge.", "danger")
            return render_template("citizen_login.html", captcha_question=issue_captcha(), google_enabled=bool(integration_value("GOOGLE_CLIENT_ID", "google_client_id", "")))
        con = db()
        user = con.execute("SELECT * FROM users WHERE email=? AND role='citizen'", (email,)).fetchone()
        con.close()
        if user and user["password"] and check_password_hash(user["password"], password):
            session.clear()
            session["citizen_id"] = user["id"]
            session["citizen_email"] = user["email"]
            if not user["email_verified"]:
                delivered = send_citizen_email_otp(user["id"])
                if delivered:
                    flash("Sign-in successful. A fresh 6-digit OTP was sent to your email.", "success")
                elif current_local_demo_otp(user["id"]):
                    flash("Email delivery is unavailable on this laptop. Local hackathon OTP fallback is active below.", "warning")
                else:
                    flash(f"OTP email could not be delivered: {app.config.get('LAST_EMAIL_ERROR') or 'Check Email & OTP Setup.'}", "danger")
                return redirect(url_for("citizen_verify_otp"))
            flash("Welcome back. Your verified Civic Account is signed in.", "success")
            destination = request.args.get("next") or request.form.get("next")
            return redirect(destination if destination and destination.startswith("/") else url_for("index"))
        flash("Invalid citizen email or password.", "danger")
        captcha_question = issue_captcha()
    if captcha_question is None:
        captcha_question = issue_captcha()
    return render_template("citizen_login.html", captcha_question=captcha_question, google_enabled=bool(integration_value("GOOGLE_CLIENT_ID", "google_client_id", "")))

@app.route("/citizen/register", methods=["GET", "POST"])
def citizen_register():
    captcha_question = None
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        village = (request.form.get("village") or "").strip()
        ward = (request.form.get("ward") or "").strip()
        if not validate_captcha(request.form.get("captcha")):
            flash("CAPTCHA verification failed. Please try again.", "danger")
            return render_template("citizen_register.html", captcha_question=issue_captcha(), google_enabled=bool(integration_value("GOOGLE_CLIENT_ID", "google_client_id", "")))
        if not full_name or not valid_email(email) or not email or len(password) < 8 or not village or not ward:
            flash("Enter your name, valid email, locality and a password of at least 8 characters.", "danger")
            return render_template("citizen_register.html", captcha_question=issue_captcha(), google_enabled=bool(integration_value("GOOGLE_CLIENT_ID", "google_client_id", "")))
        con = db()
        if con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            con.close()
            flash("A Civic Account already exists for this email.", "warning")
            return redirect(url_for("citizen_login"))
        con.execute(
            "INSERT INTO users(username,password,role,email,full_name,provider,email_verified,resident_verified,village,ward,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (email, generate_password_hash(password), "citizen", email, full_name, "local", 0, 0, village, ward, iso()),
        )
        citizen_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        audit_action(con, "Citizen Account Created", "Citizen registered a password-based Civic Account.", actor_type="citizen", actor_id=str(citizen_id))
        con.commit()
        con.close()
        session.clear()
        session["citizen_id"] = citizen_id
        session["citizen_email"] = email
        verification_sent = send_citizen_email_otp(citizen_id, force=True)
        if verification_sent:
            flash("Civic Account created. We sent a 6-digit verification OTP to your email.", "success")
        elif current_local_demo_otp(citizen_id):
            flash("Civic Account created. Gmail delivery is not configured/reachable, so local hackathon OTP fallback is active below.", "warning")
        else:
            flash(f"Civic Account created, but the OTP email could not be delivered: {app.config.get('LAST_EMAIL_ERROR') or 'Check Email & OTP Setup.'}", "danger")
        return redirect(url_for("citizen_verify_otp"))
    if captcha_question is None:
        captcha_question = issue_captcha()
    return render_template("citizen_register.html", captcha_question=captcha_question, google_enabled=bool(integration_value("GOOGLE_CLIENT_ID", "google_client_id", "")))

@app.route("/citizen/verify-otp", methods=["GET", "POST"])
@citizen_required
def citizen_verify_otp():
    citizen = current_citizen()
    if not citizen:
        return redirect(url_for("citizen_login"))
    if citizen["email_verified"]:
        flash("Your Civic Account email is already verified.", "success")
        return redirect(url_for("citizen_profile"))
    if request.method == "POST":
        otp = re.sub(r"\D", "", request.form.get("otp") or "")
        if len(otp) != 6:
            flash("Enter the complete 6-digit verification code.", "warning")
            return render_template("citizen_verify_otp.html", citizen=citizen, demo_otp=current_local_demo_otp(citizen["id"]))
        con = db()
        challenge = con.execute(
            "SELECT * FROM citizen_email_otps WHERE user_id=? AND consumed_at IS NULL ORDER BY id DESC LIMIT 1",
            (citizen["id"],),
        ).fetchone()
        if not challenge:
            con.close(); flash("No active OTP was found. Request a new code.", "warning")
            return render_template("citizen_verify_otp.html", citizen=citizen, demo_otp=current_local_demo_otp(citizen["id"]))
        expires = parse_dt(challenge["expires_at"])
        if not expires or datetime.now() > expires:
            con.close(); flash("That OTP has expired. Request a new code.", "danger")
            return render_template("citizen_verify_otp.html", citizen=citizen, demo_otp=current_local_demo_otp(citizen["id"]))
        if int(challenge["attempts"] or 0) >= 5:
            con.close(); flash("Too many incorrect attempts. Request a new OTP.", "danger")
            return render_template("citizen_verify_otp.html", citizen=citizen, demo_otp=current_local_demo_otp(citizen["id"]))
        if not check_password_hash(challenge["otp_hash"], otp):
            con.execute("UPDATE citizen_email_otps SET attempts=attempts+1 WHERE id=?", (challenge["id"],))
            con.commit(); con.close(); flash("Incorrect OTP. Please check the email and try again.", "danger")
            return render_template("citizen_verify_otp.html", citizen=citizen, demo_otp=current_local_demo_otp(citizen["id"]))
        now = iso()
        con.execute("UPDATE users SET email_verified=1 WHERE id=?", (citizen["id"],))
        con.execute("UPDATE citizen_email_otps SET consumed_at=? WHERE user_id=? AND consumed_at IS NULL", (now, citizen["id"]))
        audit_action(con, "Citizen Email OTP Verified", "Citizen verified the Civic Account email using a one-time code.", actor_type="citizen", actor_id=str(citizen["id"]))
        con.commit(); con.close()
        clear_local_demo_otp()
        flash("Email verified successfully. Your Civic Account is now active.", "success")
        return redirect(url_for("index"))
    return render_template("citizen_verify_otp.html", citizen=citizen, demo_otp=current_local_demo_otp(citizen["id"]))

@app.route("/citizen/resend-otp", methods=["POST"])
@citizen_required
def citizen_resend_otp():
    citizen = current_citizen()
    if citizen and citizen["email_verified"]:
        flash("Your Civic Account email is already verified.", "success")
        return redirect(url_for("citizen_profile"))
    delivered = send_citizen_email_otp(session["citizen_id"])
    detail = app.config.get("LAST_EMAIL_ERROR", "")
    if delivered:
        flash("A new 6-digit OTP was sent to your email.", "success")
    elif current_local_demo_otp(session["citizen_id"]):
        flash("Gmail delivery failed, but the local hackathon OTP below is valid for 10 minutes.", "warning")
    else:
        flash(detail or "OTP email could not be delivered. Check Email & OTP Setup.", "danger")
    return redirect(url_for("citizen_verify_otp"))

@app.route("/citizen/verify-email/<token>")
def citizen_verify_email(token):
    payload = read_email_verification_token(token)
    if not payload:
        flash("This email-verification link is invalid or expired. Request a new link from My Civic Account.", "danger")
        return redirect(url_for("citizen_login"))
    try:
        user_id = int(payload.get("uid") or 0)
    except (TypeError, ValueError):
        user_id = 0
    email = (payload.get("email") or "").strip().lower()
    con = db()
    user = con.execute("SELECT * FROM users WHERE id=? AND role='citizen'", (user_id,)).fetchone()
    if not user or (user["email"] or "").strip().lower() != email:
        con.close()
        flash("This verification link does not match a Civic Account.", "danger")
        return redirect(url_for("citizen_login"))
    if not user["email_verified"]:
        con.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
        audit_action(con, "Citizen Email Verified", "Citizen verified control of the Civic Account email.", actor_type="citizen", actor_id=str(user_id))
        con.commit()
    con.close()
    session.clear()
    session["citizen_id"] = user_id
    session["citizen_email"] = email
    flash("Email verified ✓ Weighted civic participation is now enabled for this account.", "success")
    return redirect(url_for("citizen_profile"))

@app.route("/citizen/resend-verification", methods=["POST"])
@citizen_required
def citizen_resend_verification():
    citizen = current_citizen()
    if citizen and citizen["email_verified"]:
        flash("Your Civic Account email is already verified.", "success")
        return redirect(url_for("citizen_profile"))
    delivered = send_citizen_email_otp(session["citizen_id"])
    flash("Verification OTP sent. Check your inbox/spam folder." if delivered else (app.config.get("LAST_EMAIL_ERROR") or "Verification OTP could not be delivered right now."), "success" if delivered else "warning")
    return redirect(url_for("citizen_verify_otp"))

@app.route("/citizen/google")
def citizen_google_login():
    flash("CivicOS uses secure email OTP verification instead of Google Sign-In.", "info")
    return redirect(url_for("citizen_login"))

@app.route("/citizen/google/callback")
def citizen_google_callback():
    flash("Google Sign-In has been replaced by CivicOS email OTP verification.", "info")
    return redirect(url_for("citizen_login"))

@app.route("/citizen/profile", methods=["GET", "POST"])
@citizen_required
def citizen_profile():
    citizen = current_citizen()
    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        village = (request.form.get("village") or "").strip()
        ward = (request.form.get("ward") or "").strip()
        con = db()
        con.execute("UPDATE users SET full_name=?,village=?,ward=? WHERE id=?", (full_name, village, ward, citizen["id"]))
        audit_action(con, "Civic Profile Updated", "Citizen updated locality/profile information.")
        con.commit(); con.close()
        flash("Civic profile updated.", "success")
        return redirect(url_for("citizen_profile"))
    con = db()
    my_cases = con.execute("SELECT * FROM complaints WHERE citizen_user_id=? ORDER BY id DESC LIMIT 20", (citizen["id"],)).fetchall()
    con.close()
    return render_template("citizen_profile.html", citizen=citizen, my_cases=my_cases)

@app.route("/citizen/logout")
def citizen_logout():
    session.pop("citizen_id", None)
    session.pop("citizen_email", None)
    flash("Citizen account signed out.", "success")
    return redirect(url_for("index"))

@app.route("/worker/login", methods=["GET", "POST"])
def worker_login():
    if current_worker_account():
        return redirect(url_for("worker_portal"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        con = db()
        account = con.execute(
            "SELECT * FROM users WHERE lower(username)=? AND role='worker'", (username,)
        ).fetchone()
        con.close()
        if account and account["worker_id"] and get_worker(account["worker_id"]) and check_password_hash(account["password"] or "", password):
            session.clear()
            session["worker_user_id"] = account["id"]
            session["worker_id"] = account["worker_id"]
            flash(f"Worker portal opened for {worker_label(account['worker_id'])}.", "success")
            destination = request.args.get("next") or request.form.get("next")
            if destination and destination.startswith("/worker/portal"):
                return redirect(destination)
            return redirect(url_for("worker_portal"))
        flash("Invalid worker username or password.", "danger")
    return render_template("worker_login.html")

@app.route("/worker/logout")
def worker_logout():
    session.pop("worker_user_id", None)
    session.pop("worker_id", None)
    flash("Worker signed out.", "success")
    return redirect(url_for("index"))

def render_worker_dashboard(worker_id, worker_view=False):
    sync_escalations()
    worker = get_worker(worker_id)
    if not worker:
        flash(t("worker_not_found"), "danger")
        return redirect(url_for("worker_login") if worker_view else url_for("workers_dashboard"))
    con = db()
    tasks = con.execute(
        "SELECT * FROM complaints WHERE assigned_worker=? ORDER BY CASE WHEN status='Resolved' THEN 2 WHEN status='Awaiting Admin Verification' THEN 1 ELSE 0 END, id DESC",
        (worker_id,),
    ).fetchall()
    metric = next((item for item in calculate_worker_stats(con) if item["id"] == worker_id), None)
    con.close()
    active = [task for task in tasks if task["status"] in {"Assigned", "In Progress"}]
    stats = {
        "total": len(tasks),
        "active": len(active),
        "awaiting_review": sum(1 for task in tasks if task["status"] == "Awaiting Admin Verification"),
        "done": sum(1 for task in tasks if task["status"] == "Resolved"),
        "escalated": sum(1 for task in active if task["escalated"]),
        "high_priority": sum(1 for task in active if task["priority"] >= 70),
        "available": not bool(active),
    }
    return render_template(
        "worker.html",
        worker=worker,
        tasks=tasks,
        stats=stats,
        current_task=active[0] if active else None,
        performance=metric,
        worker_view=worker_view,
    )

@app.route("/worker/portal")
@worker_required
def worker_portal():
    return render_worker_dashboard(session["worker_id"], worker_view=True)

@app.route("/admin/accountability")
@login_required
def admin_accountability():
    con = db()
    context = admin_common_context(con)
    reports = con.execute(
        "SELECT a.*,u.full_name,u.email FROM admin_accountability a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC"
    ).fetchall()
    con.close()
    return render_template("admin_accountability.html", admin_active="accountability", accountability_reports=reports, **context)

@app.route("/admin/accountability/<int:report_id>", methods=["POST"])
@login_required
def admin_update_accountability(report_id):
    status = (request.form.get("status") or "Under Review").strip()
    note = (request.form.get("moderation_note") or "").strip()
    public_visible = 1 if request.form.get("public_visible") == "1" else 0
    allowed = {"Submitted", "Under Review", "Substantiated", "Not Substantiated", "Closed"}
    if status not in allowed:
        flash("Invalid accountability review status.", "danger")
        return redirect(url_for("admin_accountability"))
    con = db()
    row = con.execute("SELECT * FROM admin_accountability WHERE id=?", (report_id,)).fetchone()
    if not row:
        con.close(); flash("Accountability report not found.", "warning")
        return redirect(url_for("admin_accountability"))
    con.execute(
        "UPDATE admin_accountability SET status=?,moderation_note=?,public_visible=?,updated_at=? WHERE id=?",
        (status, note, public_visible, iso(), report_id),
    )
    audit_action(con, "Accountability Report Reviewed", f"Report #{report_id} moved to {status}. {note}")
    con.commit(); con.close()
    flash("Accountability review updated and recorded in the audit trail.", "success")
    return redirect(url_for("admin_accountability"))

def email_configuration_status():
    host = integration_value("SMTP_HOST", "smtp_host", "")
    port = integration_value("SMTP_PORT", "smtp_port", "587") or "587"
    username = integration_value("SMTP_USERNAME", "smtp_username", "")
    password = integration_value("SMTP_PASSWORD", "smtp_password", "")
    sender = integration_value("SMTP_FROM", "smtp_from", username)
    security = integration_value("SMTP_SECURITY", "smtp_security", "starttls").lower() or "starttls"
    google_id = integration_value("GOOGLE_CLIENT_ID", "google_client_id", "")
    google_secret = integration_value("GOOGLE_CLIENT_SECRET", "google_client_secret", "")
    try:
        callback = integration_value("GOOGLE_REDIRECT_URI", "google_redirect_uri", "") or url_for("citizen_google_callback", _external=True)
    except RuntimeError:
        callback = integration_value("GOOGLE_REDIRECT_URI", "google_redirect_uri", "") or "http://127.0.0.1:5000/citizen/google/callback"
    return {
        "configured": bool(host and sender and (not username or password)),
        "host": host or "Not configured",
        "host_value": host,
        "port": port,
        "username": username,
        "sender": sender or "Not configured",
        "sender_value": sender,
        "security": security,
        "password_saved": bool(password),
        "public_url": integration_value("CIVICOS_PUBLIC_URL", "public_url", "") or public_base_url(),
        "public_url_value": integration_value("CIVICOS_PUBLIC_URL", "public_url", ""),
        "google_oauth": False,
        "google_client_id": google_id,
        "google_secret_saved": bool(google_secret),
        "google_redirect_uri": callback,
        "last_error": app.config.get("LAST_EMAIL_ERROR", ""),
    }

@app.route("/admin/email-test", methods=["POST"])
@login_required
def admin_email_test():
    recipient = (request.form.get("recipient") or "").strip().lower()
    if not recipient or not valid_email(recipient):
        flash("Enter a valid recipient email for the SMTP test.", "warning")
        return redirect(url_for("admin_settings"))
    test_url = public_base_url()
    delivered = send_email_to(
        recipient,
        "CivicOS email delivery test",
        f"CivicOS SMTP delivery is working. Public site URL: {test_url}",
        html=f"<div style='font-family:Arial,sans-serif;padding:24px'><h2>CivicOS Gmail/SMTP verification ✓</h2><p>Your SMTP configuration successfully authenticated and delivered this message.</p><p>Citizen action links will use: <b>{html_lib.escape(test_url)}</b></p></div>",
        purpose="smtp_verification_test",
    )
    failure_detail = app.config.get("LAST_EMAIL_ERROR", "")
    flash(
        "Test email delivered successfully." if delivered else f"Test email failed: {failure_detail or 'Check SMTP host/port/security and credentials.'}",
        "success" if delivered else "danger",
    )
    return redirect(url_for("admin_settings"))

@app.route("/admin/integrations", methods=["POST"])
@login_required
def admin_integrations():
    smtp_host = (request.form.get("smtp_host") or "").strip()
    smtp_port = (request.form.get("smtp_port") or "587").strip()
    smtp_username = (request.form.get("smtp_username") or "").strip()
    smtp_from = (request.form.get("smtp_from") or smtp_username).strip()
    smtp_security = (request.form.get("smtp_security") or "starttls").strip().lower()
    public_url = (request.form.get("public_url") or "").strip().rstrip("/")
    google_client_id = (request.form.get("google_client_id") or "").strip()
    google_redirect_uri = (request.form.get("google_redirect_uri") or "").strip()

    if smtp_host:
        try:
            port_num = int(smtp_port)
            if not 1 <= port_num <= 65535:
                raise ValueError
        except ValueError:
            flash("SMTP port must be a number between 1 and 65535.", "danger")
            return redirect(url_for("admin_settings"))
        if smtp_security not in {"starttls", "ssl", "none"}:
            flash("Choose STARTTLS, SSL or none for SMTP security.", "danger")
            return redirect(url_for("admin_settings"))
    if public_url and not (public_url.startswith("http://") or public_url.startswith("https://")):
        flash("Public URL must start with http:// or https://.", "danger")
        return redirect(url_for("admin_settings"))

    current = load_integration_config()
    updates = {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_from": smtp_from,
        "smtp_security": smtp_security,
        "public_url": public_url,
        "google_client_id": google_client_id,
        "google_redirect_uri": google_redirect_uri,
    }
    smtp_password = request.form.get("smtp_password") or ""
    google_secret = request.form.get("google_client_secret") or ""
    if smtp_password.strip():
        updates["smtp_password"] = smtp_password.strip()
    elif "smtp_password" in current:
        updates["smtp_password"] = current["smtp_password"]
    if google_secret.strip():
        updates["google_client_secret"] = google_secret.strip()
    elif "google_client_secret" in current:
        updates["google_client_secret"] = current["google_client_secret"]
    if request.form.get("clear_smtp_password") == "1":
        updates["smtp_password"] = ""
    if request.form.get("clear_google_secret") == "1":
        updates["google_client_secret"] = ""

    try:
        save_integration_config(updates)
    except OSError as exc:
        app.logger.warning("Could not save local integration settings: %s", exc)
        flash("Could not save integration settings on this machine. Use .env/environment variables instead.", "danger")
        return redirect(url_for("admin_settings"))

    app.config["LAST_EMAIL_ERROR"] = ""
    flash("Email/OTP delivery settings saved locally. No restart is required.", "success")
    return redirect(url_for("admin_settings"))

@app.route("/admin/verification")
@login_required
def admin_verification():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    pending = con.execute(
        "SELECT * FROM complaints WHERE status='Awaiting Admin Verification' ORDER BY worker_completion_requested_at ASC,id ASC"
    ).fetchall()
    reopen_requests = con.execute(
        "SELECT * FROM complaints WHERE reopen_requested=1 AND reopen_review_status='Pending Admin Review' ORDER BY updated_at ASC,id ASC"
    ).fetchall()
    con.close()
    return render_template("admin_verification.html", admin_active="verification", pending=pending, reopen_requests=reopen_requests, **context)

@app.route("/admin/verification/<int:cid>", methods=["POST"])
@login_required
def admin_verify_completion(cid):
    action = (request.form.get("action") or "").strip()
    note = (request.form.get("note") or "").strip()
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not row or row["status"] != "Awaiting Admin Verification":
        con.close(); flash("This case is not waiting for authority verification.", "warning")
        return redirect(url_for("admin_verification"))
    if action == "approve":
        now = iso()
        con.execute(
            "UPDATE complaints SET status='Resolved',resolved_at=?,admin_verified_at=?,updated_at=?,escalated=0,citizen_resolution='Pending',reopen_requested=0,resolution_cycle=COALESCE(resolution_cycle,0)+1 WHERE id=?",
            (now, now, now, cid),
        )
        refreshed = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        before_path = os.path.join(UPLOAD, refreshed["before_photo"]) if refreshed["before_photo"] else None
        after_path = os.path.join(UPLOAD, refreshed["after_photo"]) if refreshed["after_photo"] else None
        proof = proof_verification(before_path, after_path, False)
        con.execute("UPDATE complaints SET verification_score=?,verification_status=? WHERE id=?", (proof["score"], proof["status"], cid))
        add_timeline(con, cid, "Authority Verified Completion", note or "Authority reviewed field proof and approved completion. Citizen verification requested.")
        create_notification(con, cid, "Authority approved completion", "The authority verified the field team's completion proof. Please confirm the real-world result and rate the work.", "success")
        audit_action(con, "Authority Approved Completion", note or "Completion proof approved and citizen verification initiated.", cid)
        con.commit(); con.close()
        delivered = send_resolution_email(cid)
        flash(
            "Completion approved. Citizen resolution-verification email was delivered."
            if delivered
            else f"Completion approved, but the citizen email failed: {app.config.get('LAST_EMAIL_ERROR') or 'SMTP is not configured.'}",
            "success" if delivered else "warning",
        )
        return redirect(url_for("admin_verification"))
    if action in {"sendback", "more_evidence"}:
        reason = note or ("Additional completion evidence is required." if action == "more_evidence" else "Authority rejected the completion proof and returned the case to the work queue.")
        old_worker = row["assigned_worker"]
        con.execute(
            "UPDATE complaints SET status='Pending',assigned_worker=NULL,assigned_at=NULL,worker_completion_requested_at=NULL,updated_at=?,resolved_at=NULL,admin_note=? WHERE id=?",
            (iso(), reason, cid),
        )
        add_timeline(con, cid, "Authority Returned Work", reason)
        create_notification(con, cid, "Completion requires more work", "Authority review did not approve closure yet. The case has returned to the field-work queue.", "warning")
        audit_action(con, "Authority Returned Completion", reason, cid)
        if old_worker:
            assign_next_pending(con, old_worker)
        con.commit(); con.close()
        flash("Completion was not approved; the case returned to the field-work queue.", "warning")
        return redirect(url_for("admin_verification"))
    con.close(); flash("Choose a valid verification action.", "warning")
    return redirect(url_for("admin_verification"))

@app.route("/admin/reopen/<int:cid>", methods=["POST"])
@login_required
def admin_review_reopen(cid):
    action = (request.form.get("action") or "").strip()
    note = (request.form.get("note") or "").strip()
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not row or not row["reopen_requested"] or row["reopen_review_status"] != "Pending Admin Review":
        con.close(); flash("No pending reopen request exists for this case.", "warning")
        return redirect(url_for("admin_verification"))
    if action == "approve":
        priority = min(100, max(int(row["priority"] or 0), 70) + 10)
        con.execute(
            "UPDATE complaints SET status='Pending',assigned_worker=NULL,assigned_at=NULL,resolved_at=NULL,admin_verified_at=NULL,citizen_confirmed=0,citizen_resolution='Reopened',reopen_requested=0,reopen_review_status='Approved',priority=?,updated_at=?,admin_note=? WHERE id=?",
            (priority, iso(), note or "Reopen evidence accepted; field work re-entered the queue.", cid),
        )
        con.execute("UPDATE resolution_reviews SET review_status='Reopen Approved',reviewed_at=? WHERE complaint_id=? AND resolution_cycle=? AND review_status='Reopen Requested'", (iso(), cid, int(row["resolution_cycle"] or 1)))
        add_timeline(con, cid, "Reopen Approved", note or "Authority accepted fresh citizen evidence and reopened the civic case.")
        create_notification(con, cid, "Case reopened", "Authority accepted the fresh evidence. The civic case has returned to the prioritized field-work queue.", "warning")
        audit_action(con, "Reopen Approved", note or "Authority approved citizen evidence and reopened the case.", cid)
        con.commit(); con.close()
        send_optional_email(cid, f"CivicOS #{cid}: case reopened", "Your reopen evidence was approved. The civic case has returned to the prioritized field-work queue.")
        flash("Reopen evidence approved; the case is active again.", "success")
        return redirect(url_for("admin_verification"))
    if action == "reject":
        reason = note or "Authority reviewed the reopen evidence and did not find sufficient basis to reopen the completed case."
        con.execute(
            "UPDATE complaints SET reopen_requested=0,reopen_review_status='Rejected',citizen_resolution='Reopen Rejected',updated_at=?,admin_note=? WHERE id=?",
            (iso(), reason, cid),
        )
        con.execute("UPDATE resolution_reviews SET review_status='Reopen Rejected',reviewed_at=? WHERE complaint_id=? AND resolution_cycle=? AND review_status='Reopen Requested'", (iso(), cid, int(row["resolution_cycle"] or 1)))
        add_timeline(con, cid, "Reopen Rejected", reason)
        create_notification(con, cid, "Reopen request reviewed", "Authority reviewed the fresh evidence and did not reopen the case. The review reason is recorded in the audit trail.", "info")
        audit_action(con, "Reopen Rejected", reason, cid)
        con.commit(); con.close()
        send_optional_email(cid, f"CivicOS #{cid}: reopen review completed", reason)
        flash("Reopen request rejected with an auditable reason.", "success")
        return redirect(url_for("admin_verification"))
    con.close(); flash("Choose approve or reject.", "warning")
    return redirect(url_for("admin_verification"))

@app.route("/resolution-email/<int:cid>", methods=["POST"])
@citizen_required
def resend_resolution_email(cid):
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    citizen = con.execute("SELECT * FROM users WHERE id=?", (session["citizen_id"],)).fetchone()
    con.close()
    if not row or row["status"] != "Resolved":
        flash("Resolution verification email is available only after authority-approved completion.", "warning")
        return redirect(url_for("track", cid=cid))
    owns_case = row["citizen_user_id"] == session["citizen_id"] or ((row["email"] or "").lower() == (citizen["email"] or "").lower())
    if not owns_case:
        flash("Only the reporting citizen can request the secure resolution email.", "danger")
        return redirect(url_for("track", cid=cid))
    delivered = send_resolution_email(cid)
    flash("Secure verification email sent again." if delivered else "Email could not be delivered. Check SMTP configuration and the citizen email address.", "success" if delivered else "warning")
    return redirect(url_for("track", cid=cid))

@app.route("/resolution-review/<token>", methods=["GET", "POST"])
def resolution_review(token):
    payload = read_resolution_token(token)
    if not payload:
        flash("This resolution-verification link is invalid or has expired.", "danger")
        return redirect(url_for("index"))
    cid = int(payload.get("cid") or 0)
    token_email = (payload.get("email") or "").strip().lower()
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not row or (row["email"] or "").strip().lower() != token_email:
        con.close(); flash("This verification link does not match the civic case.", "danger")
        return redirect(url_for("index"))
    if row["status"] != "Resolved":
        con.close(); flash("This case is not currently awaiting citizen resolution verification.", "warning")
        return redirect(url_for("track", cid=cid))
    if request.method == "POST":
        if (row["citizen_resolution"] or "Pending") != "Pending":
            con.close(); flash("A citizen outcome has already been recorded for this resolution cycle.", "warning")
            return redirect(url_for("track", cid=cid))
        verdict = (request.form.get("verdict") or "").strip()
        try:
            rating = max(1, min(5, int(request.form.get("rating") or 5)))
        except ValueError:
            rating = 5
        feedback_text = (request.form.get("feedback") or "").strip()
        user_id = row["citizen_user_id"] or session.get("citizen_id")
        if verdict == "satisfied":
            con.execute("UPDATE complaints SET citizen_confirmed=1,citizen_resolution='Satisfied',verification_status='Citizen Verified',updated_at=? WHERE id=?", (iso(), cid))
            con.execute(
                "INSERT INTO resolution_reviews(complaint_id,user_id,worker_id,resolution_cycle,verdict,rating,feedback,review_status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (cid, user_id, row["assigned_worker"], int(row["resolution_cycle"] or 1), "Satisfied", rating, feedback_text, "Citizen Verified", iso()),
            )
            con.execute("INSERT INTO feedback(complaint_id,name,rating,message,created_at) VALUES(?,?,?,?,?)", (cid, row["citizen_name"] or "Citizen", rating, feedback_text or "Satisfied with resolution.", iso()))
            add_timeline(con, cid, "Citizen Verified", f"Citizen confirmed the resolution and rated the field work {rating}/5.")
            create_notification(con, cid, "Resolution verified by citizen", "Citizen confirmation and field-team rating were recorded.", "success")
            audit_action(con, "Citizen Confirmed Resolution", f"Citizen rated the field work {rating}/5.", cid, actor_type="citizen", actor_id=str(user_id or token_email))
            con.commit(); con.close()
            flash("Thank you. Your one-time resolution confirmation and worker rating were recorded.", "success")
            return redirect(url_for("track", cid=cid))
        if verdict == "not_satisfied":
            reason = (request.form.get("reopen_reason") or "").strip()
            if len(reason) < 15:
                con.close(); flash("Explain why the issue remains unresolved before requesting reopening.", "warning")
                return render_template("resolution_review.html", comp=row, token=token)
            try:
                reopen_photo = save_file("reopen_photo")
            except ValueError as exc:
                con.close(); flash(str(exc), "danger")
                return render_template("resolution_review.html", comp=row, token=token)
            if not reopen_photo:
                con.close(); flash("Fresh photo evidence is required for a reopen request.", "warning")
                return render_template("resolution_review.html", comp=row, token=token)
            con.execute(
                "UPDATE complaints SET citizen_resolution='Reopen Requested',reopen_requested=1,reopen_reason=?,reopen_photo=?,reopen_review_status='Pending Admin Review',updated_at=? WHERE id=?",
                (reason, reopen_photo, iso(), cid),
            )
            con.execute(
                "INSERT INTO resolution_reviews(complaint_id,user_id,worker_id,resolution_cycle,verdict,rating,feedback,reopen_reason,evidence_photo,review_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cid, user_id, row["assigned_worker"], int(row["resolution_cycle"] or 1), "Not Satisfied", rating, feedback_text, reason, reopen_photo, "Reopen Requested", iso()),
            )
            con.execute("INSERT INTO feedback(complaint_id,name,rating,message,created_at) VALUES(?,?,?,?,?)", (cid, row["citizen_name"] or "Citizen", rating, feedback_text or reason, iso()))
            add_timeline(con, cid, "Reopen Requested", "Citizen reported the problem still exists and supplied fresh photo evidence. Authority review required.")
            create_notification(con, cid, "Reopen request submitted", "Your fresh evidence has been submitted for authority review. The case is not automatically reopened.", "warning")
            audit_action(con, "Citizen Requested Reopen", reason, cid, actor_type="citizen", actor_id=str(user_id or token_email))
            con.commit(); con.close()
            flash("Reopen request submitted with evidence. An authority must review it before the case is reopened.", "success")
            return redirect(url_for("track", cid=cid))
        con.close(); flash("Choose whether the issue is resolved or not resolved.", "warning")
        return render_template("resolution_review.html", comp=row, token=token)
    con.close()
    return render_template("resolution_review.html", comp=row, token=token)

@app.route("/civic-intelligence")
@citizen_required
def civic_intelligence_public():
    sync_escalations()
    con = db()
    rows = con.execute("SELECT * FROM complaints ORDER BY id DESC").fetchall()
    stats = get_stats(con)
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    recent = rows[:18]
    accountability = con.execute(
        "SELECT a.*,u.full_name FROM admin_accountability a LEFT JOIN users u ON u.id=a.user_id WHERE a.public_visible=1 ORDER BY a.id DESC LIMIT 10"
    ).fetchall()
    accountability_all = con.execute("SELECT status FROM admin_accountability").fetchall()
    approval_delays = []
    for row in rows:
        submitted = parse_dt(row["worker_completion_requested_at"])
        approved = parse_dt(row["admin_verified_at"])
        if submitted and approved and approved >= submitted:
            approval_delays.append((approved - submitted).total_seconds() / 3600)
    reopen_total = sum(1 for row in rows if (row["citizen_resolution"] or "") in {"Reopen Requested", "Reopened", "Reopen Rejected"})
    resolved_verified = sum(1 for row in rows if row["status"] == "Resolved" and row["admin_verified_at"])
    avg_approval_hours = round(sum(approval_delays) / len(approval_delays), 1) if approval_delays else 0
    reviewed_accountability = [a for a in accountability_all if a["status"] in {"Substantiated", "Not Substantiated", "Closed"}]
    substantiated_count = sum(1 for a in reviewed_accountability if a["status"] == "Substantiated")
    qa_component = max(0, round(100 - (min(avg_approval_hours, 48) / 48 * 100))) if approval_delays else 75
    reopen_component = max(0, round(100 - (reopen_total / max(1, resolved_verified) * 100))) if resolved_verified else 75
    accountability_component = max(0, round(100 - (substantiated_count / max(1, len(reviewed_accountability)) * 100))) if reviewed_accountability else 75
    authority_index = round(
        float(stats.get("sla_compliance", 0)) * 0.40
        + qa_component * 0.25
        + reopen_component * 0.20
        + accountability_component * 0.15
    )
    admin_kpis = {
        "authority_index": authority_index,
        "avg_approval_hours": avg_approval_hours,
        "authority_verified_closures": resolved_verified,
        "reopen_challenges": reopen_total,
        "open_accountability": sum(1 for a in accountability_all if a["status"] in {"Submitted", "Under Review"}),
        "qa_component": qa_component,
        "reopen_component": reopen_component,
        "accountability_component": accountability_component,
    }
    con.close()
    ward_health = []
    for item in ward_data:
        score = max(0, min(100, round((item["rate"] * 0.65) + (35 if item["escalated"] == 0 else max(0, 35 - item["escalated"] * 7)))))
        ward_health.append({**item, "health_score": score})
    return render_template(
        "civic_intelligence_public.html", stats=stats, dept_perf=dept_perf,
        ward_data=ward_health, recent=recent, accountability=accountability, admin_kpis=admin_kpis,
    )

@app.route("/api/nearby-activity")
@citizen_required
def nearby_activity_api():
    try:
        lat = float(request.args.get("lat", "")); lon = float(request.args.get("lon", ""))
        radius = max(0.25, min(float(request.args.get("radius", "3")), 25.0))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except ValueError:
        return jsonify(ok=False, error="Invalid location or radius"), 400
    con = db()
    rows = con.execute(
        """SELECT c.* FROM complaints c
           LEFT JOIN complaint_trust_assessments a ON a.complaint_id=c.id
           WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL
             AND COALESCE(a.public_visibility,'Normal')!='Quarantined'
           ORDER BY c.id DESC LIMIT 500"""
    ).fetchall()
    voted = {r["complaint_id"] for r in con.execute("SELECT complaint_id FROM complaint_votes WHERE user_id=?", (session["citizen_id"],)).fetchall()}
    reviewed = {(r["complaint_id"], r["resolution_cycle"]) for r in con.execute("SELECT complaint_id,resolution_cycle FROM resolution_reviews WHERE user_id=?", (session["citizen_id"],)).fetchall()}
    con.close()
    items = []
    for row in rows:
        distance = haversine_km(lat, lon, float(row["latitude"]), float(row["longitude"]))
        if distance > radius:
            continue
        items.append({
            "id": row["id"], "title": row["title"], "category": row["category"],
            "department": department_label(row["department"]), "status": row["status"],
            "ward": row["ward"], "village": row["village"], "address": row["address"] or row["location"],
            "lat": row["latitude"], "lon": row["longitude"], "distanceKm": round(distance, 2),
            "upvotes": int(row["upvotes"] or 0), "alreadyUpvoted": row["id"] in voted,
            "canVerify": row["status"] == "Resolved" and (row["id"], int(row["resolution_cycle"] or 1)) not in reviewed,
            "citizenResolution": row["citizen_resolution"] or "Pending",
            "updatedAt": row["updated_at"],
        })
    items.sort(key=lambda x: (x["distanceKm"], -x["id"]))
    citizen = current_citizen()
    return jsonify(ok=True, radiusKm=radius, count=len(items[:40]), participationVerified=bool(citizen and citizen["email_verified"]), items=items[:40])

@app.route("/accountability", methods=["GET", "POST"])
@citizen_required
def accountability_board():
    citizen = current_citizen()
    if request.method == "POST":
        if not citizen["email_verified"]:
            flash("Verify your Civic Account email before filing an administration accountability report.", "warning")
            return redirect(url_for("citizen_profile"))
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip()
        allowed = {"Unnecessary Delay", "Incorrect Closure", "Repeated Negligence", "False Status Update", "Misconduct", "Poor Service Quality", "Other"}
        if category not in allowed or len(description) < 20:
            flash("Choose an accountability category and provide at least 20 characters of factual detail.", "warning")
            return redirect(url_for("accountability_board"))
        try:
            evidence = save_file("evidence_photo")
        except ValueError as exc:
            flash(str(exc), "danger"); return redirect(url_for("accountability_board"))
        con = db()
        con.execute(
            "INSERT INTO admin_accountability(user_id,category,description,evidence_photo,status,public_visible,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (citizen["id"], category, description, evidence, "Submitted", 1, iso(), iso()),
        )
        report_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        audit_action(con, "Administrative Accountability Report", f"Citizen submitted accountability report #{report_id}.")
        con.commit(); con.close()
        flash("Accountability report submitted. It is recorded publicly as an allegation/report, not as a proven finding, until reviewed.", "success")
        return redirect(url_for("accountability_board"))
    con = db()
    reports = con.execute(
        "SELECT a.*,u.full_name FROM admin_accountability a LEFT JOIN users u ON u.id=a.user_id WHERE a.public_visible=1 ORDER BY a.id DESC LIMIT 50"
    ).fetchall()
    con.close()
    return render_template("accountability.html", reports=reports, citizen=citizen)

@app.route('/admin/procurement')
@login_required
def admin_procurement():
    con=db(); q=(request.args.get('q') or '').strip().lower(); dept=(request.args.get('department') or '').strip()
    summary=procurement_summary(con)
    inv=con.execute("""SELECT i.*,v.name supplier_name FROM inventory_items i LEFT JOIN finance_vendors v ON v.id=i.supplier_id ORDER BY (i.on_hand<=i.reorder_level) DESC,i.name""").fetchall()
    reqs=con.execute("""SELECT r.*,v.name vendor_name,(SELECT COUNT(*) FROM procurement_request_items x WHERE x.request_id=r.id) item_count
                       FROM procurement_requests r LEFT JOIN finance_vendors v ON v.id=r.vendor_id ORDER BY r.id DESC LIMIT 100""").fetchall()
    pos=con.execute("""SELECT p.*,v.name vendor_name,r.request_no FROM purchase_orders p LEFT JOIN finance_vendors v ON v.id=p.vendor_id LEFT JOIN procurement_requests r ON r.id=p.request_id ORDER BY p.id DESC LIMIT 100""").fetchall()
    movements=con.execute("""SELECT m.*,i.sku,i.name FROM stock_movements m JOIN inventory_items i ON i.id=m.item_id ORDER BY m.id DESC LIMIT 30""").fetchall()
    vendors=con.execute("SELECT * FROM finance_vendors WHERE status='Active' ORDER BY name").fetchall()
    if dept: inv=[x for x in inv if x['department']==dept]; reqs=[x for x in reqs if x['department']==dept]; pos=[x for x in pos if x['department']==dept]
    if q:
        inv=[x for x in inv if q in (x['sku']+' '+x['name']+' '+x['category']).lower()]
        reqs=[x for x in reqs if q in (x['request_no']+' '+x['purpose']+' '+x['department']).lower()]
        pos=[x for x in pos if q in (x['po_no']+' '+(x['vendor_name'] or '')).lower()]
    items=con.execute("SELECT id,sku,name,department,unit,on_hand,unit_cost FROM inventory_items ORDER BY name").fetchall()
    context=admin_common_context(con); con.close()
    return render_template_string(PROCUREMENT_TEMPLATE, procurement_active=True, summary=summary, inventory=inv, requests=reqs, purchase_orders=pos, movements=movements, vendors=vendors, items=items, departments=PROCUREMENT_DEPARTMENTS, priorities=PROCUREMENT_PRIORITIES, request_statuses=PROCUREMENT_REQUEST_STATUSES, po_statuses=PO_STATUSES, today=datetime.now().strftime('%Y-%m-%d'), dept_filter=dept, search_query=q, **context)

@app.route('/admin/procurement/inventory',methods=['POST'])
@login_required
def admin_procurement_inventory():
    f=request.form; name=(f.get('name') or '').strip(); sku=(f.get('sku') or '').strip().upper(); dept=(f.get('department') or '').strip()
    try: on_hand=float(f.get('on_hand') or 0); reorder=float(f.get('reorder_level') or 0); reorder_qty=float(f.get('reorder_qty') or 0); cost=float(f.get('unit_cost') or 0)
    except ValueError: flash('Enter valid inventory quantities and cost.','danger'); return redirect(url_for('admin_procurement'))
    if not name or not sku or dept not in PROCUREMENT_DEPARTMENTS or on_hand<0 or reorder<0 or reorder_qty<0 or cost<0: flash('Complete the inventory item fields correctly.','danger'); return redirect(url_for('admin_procurement'))
    con=db(); now=iso()
    try:
        cur=con.execute("""INSERT INTO inventory_items(sku,name,category,department,unit,on_hand,reorder_level,reorder_qty,unit_cost,warehouse,location,batch_no,expiry_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(sku,name,(f.get('category') or 'General').strip(),dept,(f.get('unit') or 'units').strip(),on_hand,reorder,reorder_qty,cost,(f.get('warehouse') or 'Central Store').strip(),(f.get('location') or '').strip(),(f.get('batch_no') or '').strip(),(f.get('expiry_date') or '').strip() or None,now,now))
        if on_hand: con.execute("INSERT INTO stock_movements(item_id,movement_type,qty,reference_type,reason,actor,created_at) VALUES(?,?,?,?,?,?,?)",(cur.lastrowid,'Opening',on_hand,'Inventory','Opening balance',session.get('admin','admin'),now))
        con.commit(); flash(f'{sku} added to inventory.','success')
    except Exception as exc: con.rollback(); flash('Could not add inventory item: '+str(exc),'danger')
    con.close(); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/request',methods=['POST'])
@login_required
def admin_procurement_request():
    f=request.form; dept=(f.get('department') or '').strip(); purpose=(f.get('purpose') or '').strip(); qty=float(f.get('qty') or 0); item_id=int(f.get('item_id')) if f.get('item_id') else None
    if dept not in PROCUREMENT_DEPARTMENTS or not purpose or qty<=0: flash('Complete the purchase request.','danger'); return redirect(url_for('admin_procurement'))
    con=db(); now=iso(); item=con.execute('SELECT * FROM inventory_items WHERE id=?',(item_id,)).fetchone() if item_id else None
    if not item: con.close(); flash('Select a valid inventory item.','danger'); return redirect(url_for('admin_procurement'))
    ref=procurement_ref(con,'PR','procurement_requests','request_no'); est=qty*float(item['unit_cost'] or 0)
    cur=con.execute("""INSERT INTO procurement_requests(request_no,requested_by,department,priority,purpose,status,total_estimate,needed_by,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(ref,session.get('admin','Admin'),dept,(f.get('priority') or 'Normal'),purpose,'Pending',est,(f.get('needed_by') or '').strip() or None,(f.get('notes') or '').strip(),now,now))
    con.execute("INSERT INTO procurement_request_items(request_id,item_id,item_name,qty,estimated_unit_cost) VALUES(?,?,?,?,?)",(cur.lastrowid,item_id,item['name'],qty,item['unit_cost']))
    con.commit(); con.close(); flash(f'{ref} submitted for approval.','success'); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/request/<int:rid>/status',methods=['POST'])
@login_required
def admin_procurement_request_status(rid):
    status=(request.form.get('status') or '').strip(); con=db(); row=con.execute('SELECT * FROM procurement_requests WHERE id=?',(rid,)).fetchone()
    if not row or status not in PROCUREMENT_REQUEST_STATUSES: con.close(); flash('Invalid request/status.','danger'); return redirect(url_for('admin_procurement'))
    if row['status'] not in ('Pending','Approved','Rejected') or status==row['status']: con.close(); flash('That status change is not allowed.','warning'); return redirect(url_for('admin_procurement'))
    con.execute('UPDATE procurement_requests SET status=?,updated_at=? WHERE id=?',(status,iso(),rid)); con.commit(); con.close(); flash(f"{row['request_no']} marked {status}.",'success'); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/po',methods=['POST'])
@login_required
def admin_procurement_po():
    f=request.form; vendor_id=int(f.get('vendor_id')) if f.get('vendor_id') else 0; item_id=int(f.get('item_id')) if f.get('item_id') else 0; dept=(f.get('department') or '').strip(); qty=float(f.get('qty') or 0); unit_cost=float(f.get('unit_cost') or 0)
    if not vendor_id or not item_id or dept not in PROCUREMENT_DEPARTMENTS or qty<=0 or unit_cost<0: flash('Complete the purchase order fields.','danger'); return redirect(url_for('admin_procurement'))
    con=db(); now=iso(); vendor=con.execute('SELECT id FROM finance_vendors WHERE id=? AND status="Active"',(vendor_id,)).fetchone(); item=con.execute('SELECT * FROM inventory_items WHERE id=?',(item_id,)).fetchone()
    if not vendor or not item: con.close(); flash('Invalid vendor or item.','danger'); return redirect(url_for('admin_procurement'))
    po=procurement_ref(con,'PO','purchase_orders','po_no'); total=qty*unit_cost
    cur=con.execute("""INSERT INTO purchase_orders(po_no,vendor_id,department,status,order_date,expected_date,subtotal,tax,total,delivery_status,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(po,vendor_id,dept,'Issued',datetime.now().strftime('%Y-%m-%d'),(f.get('expected_date') or '').strip() or None,total,0,total,'Not Received',(f.get('notes') or '').strip(),session.get('admin','Admin'),now,now))
    con.execute("INSERT INTO purchase_order_items(po_id,item_id,item_name,qty,unit_cost) VALUES(?,?,?,?,?)",(cur.lastrowid,item_id,item['name'],qty,unit_cost)); con.commit(); con.close(); flash(f'{po} issued to supplier.','success'); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/po/<int:poid>/receive',methods=['POST'])
@login_required
def admin_procurement_receive(poid):
    try: receive=float(request.form.get('received_qty') or 0)
    except ValueError: receive=0
    con=db(); po=con.execute('SELECT * FROM purchase_orders WHERE id=?',(poid,)).fetchone(); line=con.execute('SELECT * FROM purchase_order_items WHERE po_id=?',(poid,)).fetchone() if po else None
    if not po or not line or receive<=0: con.close(); flash('Enter a valid received quantity.','danger'); return redirect(url_for('admin_procurement'))
    remaining=float(line['qty'])-float(line['received_qty']); receive=min(receive,remaining)
    if receive<=0: con.close(); flash('This PO has already been fully received.','warning'); return redirect(url_for('admin_procurement'))
    item=con.execute('SELECT * FROM inventory_items WHERE id=?',(line['item_id'],)).fetchone()
    if not item: con.close(); flash('Inventory item is missing.','danger'); return redirect(url_for('admin_procurement'))
    new_received=float(line['received_qty'])+receive; new_stock=float(item['on_hand'])+receive; status='Received' if new_received>=float(line['qty']) else 'Partially Received'
    now=iso(); con.execute('UPDATE purchase_order_items SET received_qty=? WHERE id=?',(new_received,line['id'])); con.execute('UPDATE purchase_orders SET status=?,delivery_status=?,updated_at=? WHERE id=?',(status,status,now,poid)); con.execute('UPDATE inventory_items SET on_hand=?,updated_at=? WHERE id=?',(new_stock,now,item['id'])); con.execute("INSERT INTO stock_movements(item_id,movement_type,qty,reference_type,reference_id,to_location,reason,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(item['id'],'Receipt',receive,'PO',poid,item['location'] or item['warehouse'],'Goods received',session.get('admin','admin'),now))
    # Link receipt value to finance as a pending expense for a visible end-to-end workflow.
    if receive and po['vendor_id']:
        try:
            ref=finance_next_ref(con,'Expense'); con.execute("""INSERT INTO finance_transactions(txn_ref,txn_date,txn_type,department,category,description,amount,vendor_id,status,created_by,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(ref,datetime.now().strftime('%Y-%m-%d'),'Expense',po['department'],'Procurement','Goods receipt '+po['po_no'],round(receive*float(line['unit_cost']),2),po['vendor_id'],'Pending',session.get('admin','admin'),'Auto-linked from procurement receipt',now,now))
            finance_audit(con,'Procurement Receipt Linked','transaction',con.execute('SELECT last_insert_rowid() x').fetchone()['x'],f'{po["po_no"]} → {ref}')
        except Exception: pass
    con.commit(); con.close(); flash(f'{receive:g} {item["unit"]} received against {po["po_no"]}. Stock updated.','success'); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/stock-move',methods=['POST'])
@login_required
def admin_procurement_stock_move():
    try: item_id=int(request.form.get('item_id')); qty=float(request.form.get('qty') or 0)
    except (ValueError,TypeError): qty=0; item_id=0
    typ=(request.form.get('movement_type') or 'Issue').strip(); con=db(); item=con.execute('SELECT * FROM inventory_items WHERE id=?',(item_id,)).fetchone()
    if not item or qty<=0 or typ not in ('Issue','Transfer','Adjustment+','Adjustment-'): con.close(); flash('Invalid stock movement.','danger'); return redirect(url_for('admin_procurement'))
    delta=qty if typ in ('Adjustment+','Transfer') else -qty
    if typ in ('Issue','Adjustment-') and float(item['on_hand'])<qty: con.close(); flash('Movement blocked: insufficient stock.','danger'); return redirect(url_for('admin_procurement'))
    new=max(0,float(item['on_hand'])+delta); now=iso(); con.execute('UPDATE inventory_items SET on_hand=?,updated_at=? WHERE id=?',(new,now,item_id)); con.execute("INSERT INTO stock_movements(item_id,movement_type,qty,from_location,to_location,reason,actor,created_at) VALUES(?,?,?,?,?,?,?,?)",(item_id,typ,qty,item['location'] if typ in ('Issue','Transfer') else None,(request.form.get('to_location') or '').strip() or None,(request.form.get('reason') or '').strip(),session.get('admin','admin'),now)); con.commit(); con.close(); flash(f'{typ} recorded for {item["sku"]}. New balance: {new:g}.','success'); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/auto-reorder',methods=['POST'])
@login_required
def admin_procurement_auto_reorder():
    con=db(); now=iso(); created=0
    lows=con.execute("SELECT * FROM inventory_items WHERE status='Active' AND on_hand<=reorder_level AND reorder_qty>0").fetchall()
    for item in lows:
        exists=con.execute("""SELECT 1 FROM procurement_request_items ri JOIN procurement_requests r ON r.id=ri.request_id
                              WHERE ri.item_id=? AND r.status IN ('Pending','Approved') LIMIT 1""",(item['id'],)).fetchone()
        if exists: continue
        ref=procurement_ref(con,'PR','procurement_requests','request_no'); qty=float(item['reorder_qty']); est=qty*float(item['unit_cost'] or 0)
        cur=con.execute("""INSERT INTO procurement_requests(request_no,requested_by,department,priority,purpose,status,total_estimate,needed_by,notes,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(ref,'CivicOS Auto-Reorder',item['department'],'High',f'Automatic replenishment for low stock: {item["name"]}','Pending',est,(datetime.now()+timedelta(days=14)).strftime('%Y-%m-%d'),'Generated from reorder-level rule',now,now))
        con.execute("INSERT INTO procurement_request_items(request_id,item_id,item_name,qty,estimated_unit_cost) VALUES(?,?,?,?,?)",(cur.lastrowid,item['id'],item['name'],qty,item['unit_cost']))
        created+=1
    con.commit(); con.close(); flash(f'Auto-reorder created {created} purchase request(s).','success' if created else 'warning'); return redirect(url_for('admin_procurement'))

@app.route('/admin/procurement/export')
@login_required
def admin_procurement_export():
    con=db(); rows=con.execute("SELECT sku,name,category,department,unit,on_hand,reorder_level,reorder_qty,unit_cost,warehouse,location,batch_no,expiry_date FROM inventory_items ORDER BY department,name").fetchall(); con.close()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['SKU','Item','Category','Department','Unit','On Hand','Reorder Level','Reorder Qty','Unit Cost INR','Warehouse','Location','Batch','Expiry'])
    for r in rows: w.writerow(list(r))
    payload=io.BytesIO(out.getvalue().encode('utf-8-sig')); payload.seek(0)
    return send_file(payload,mimetype='text/csv',as_attachment=True,download_name=f'CivicOS_Inventory_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')

@app.route('/api/admin/procurement/summary')
@login_required
def api_admin_procurement_summary():
    con=db(); data=procurement_summary(con); con.close(); return jsonify(ok=True,**data)

PROCUREMENT_TEMPLATE=r"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Procurement & Inventory · CivicOS</title>
<style>:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f4f7fb;--panel:#fff;--blue:#2563eb;--green:#059669;--red:#dc2626;--amber:#d97706;--purple:#7c3aed;--shadow:0 12px 35px rgba(15,23,42,.08)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{text-decoration:none;color:inherit}.wrap{max-width:1550px;margin:auto;padding:22px}.top{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;margin-bottom:18px}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.14em;font-weight:900;color:var(--blue)}h1{margin:4px 0;font-size:30px;letter-spacing:-.03em}.muted{color:var(--muted);font-size:12px}.actions,.small-actions{display:flex;gap:7px;flex-wrap:wrap}.btn{border:0;border-radius:10px;padding:9px 13px;font-weight:800;cursor:pointer;display:inline-flex;align-items:center;gap:6px}.primary{background:var(--blue);color:#fff}.soft{background:#eaf2ff;color:#1d4ed8}.green{background:#ecfdf5;color:#047857}.dark{background:#0f172a;color:#fff}.red{background:#fee2e2;color:#b91c1c}.amber{background:#fff7ed;color:#b45309}.purple{background:#f3e8ff;color:#6d28d9}.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:18px}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:15px;box-shadow:var(--shadow)}.kpi small{display:block;color:var(--muted);font-weight:800;text-transform:uppercase;font-size:10px}.kpi strong{display:block;font-size:24px;margin-top:4px}.warn{color:var(--amber)}.danger{color:var(--red)}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);overflow:hidden;margin-bottom:16px}.head{padding:15px 17px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px;align-items:center}.head h2{font-size:16px;margin:0}.body{padding:16px}.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.full{grid-column:1/-1}label{font-size:10px;font-weight:900;color:#475569;text-transform:uppercase;display:block;margin-bottom:4px}input,select,textarea{width:100%;padding:9px 10px;border:1px solid #cbd5e1;border-radius:10px;font:inherit;background:#fff}.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse;min-width:900px}.table th,.table td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.table th{font-size:10px;text-transform:uppercase;color:var(--muted);background:#f8fafc;position:sticky;top:0}.table td{font-size:12px}.tag{display:inline-block;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900;background:#f1f5f9}.tag.Pending,.tag.Issued{background:#fff7ed;color:#b45309}.tag.Approved,.tag.Partially{background:#eff6ff;color:#1d4ed8}.tag.Received{background:#ecfdf5;color:#047857}.tag.Rejected,.tag.Cancelled{background:#fee2e2;color:#b91c1c}.low{background:#fff7ed!important}.flash{padding:11px 14px;border-radius:11px;margin-bottom:12px;background:#eff6ff;color:#1d4ed8}.empty{padding:25px;text-align:center;color:var(--muted);border:1px dashed #cbd5e1;border-radius:12px}.filter{display:grid;grid-template-columns:1fr 180px auto;gap:8px;margin-bottom:16px}.meter{height:7px;background:#e2e8f0;border-radius:99px;overflow:hidden}.meter i{display:block;height:100%;background:var(--blue)}.hint{padding:10px 12px;border-radius:12px;background:#f8fafc;color:#475569;font-size:12px;margin-bottom:12px}@media(max-width:1200px){.kpis{grid-template-columns:repeat(3,1fr)}}@media(max-width:900px){.grid2{grid-template-columns:1fr}.filter{grid-template-columns:1fr 1fr}.top{flex-direction:column}}@media(max-width:600px){.wrap{padding:12px}.kpis{grid-template-columns:1fr 1fr}.formgrid{grid-template-columns:1fr}.full{grid-column:auto}}</style></head>
<body><div class="wrap"><div class="top"><div><div class="eyebrow">CivicOS · Supply Chain Control</div><h1>Procurement & Inventory</h1><div class="muted">From demand → approval → purchase order → goods receipt → live stock → finance, with a complete operational trail.</div></div><div class="actions"><a class="btn soft" href="{{url_for('admin')}}">← Command Center</a><a class="btn purple" href="{{url_for('admin_procurement_export')}}">↧ Export Stock</a><form method="post" action="{{url_for('admin_procurement_auto_reorder')}}" style="display:inline"><button class="btn amber">⚡ Auto-Reorder Low Stock</button></form><a class="btn dark" href="{{url_for('admin_finance')}}">💰 Finance</a></div></div>
{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash">{{message}}</div>{% endfor %}{% endwith %}
<div class="kpis"><div class="kpi"><small>Active SKUs</small><strong>{{summary.sku_count}}</strong></div><div class="kpi"><small>Stock Value</small><strong>₹{{'{:,.0f}'.format(summary.stock_value)}}</strong></div><div class="kpi"><small>Low Stock Alerts</small><strong class="warn">{{summary.low_stock}}</strong></div><div class="kpi"><small>Pending Requests</small><strong>{{summary.pending_requests}}</strong></div><div class="kpi"><small>Open POs</small><strong>{{summary.open_pos}}</strong></div><div class="kpi"><small>PO Value YTD</small><strong>₹{{'{:,.0f}'.format(summary.po_value)}}</strong></div></div>
<form class="filter" method="get"><input name="q" value="{{search_query}}" placeholder="Search SKU, item, request, PO or supplier…"><select name="department"><option value="">All departments</option>{% for k,v in departments.items() %}<option value="{{k}}" {% if dept_filter==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select><button class="btn primary">Refresh</button></form>
<div class="grid2"><div class="panel"><div class="head"><h2>➕ Add Inventory Item</h2><span class="muted">Master stock register</span></div><div class="body"><form method="post" action="{{url_for('admin_procurement_inventory')}}" class="formgrid"><div><label>SKU</label><input name="sku" placeholder="INV-WTR-099" required></div><div><label>Item name</label><input name="name" placeholder="GI Valve 150mm" required></div><div><label>Category</label><input name="category" placeholder="Water / Road / Electrical"></div><div><label>Department</label><select name="department" required>{% for k,v in departments.items() %}<option value="{{k}}">{{v}}</option>{% endfor %}</select></div><div><label>Unit</label><input name="unit" value="units"></div><div><label>Opening quantity</label><input name="on_hand" type="number" min="0" step="0.01" value="0"></div><div><label>Reorder level</label><input name="reorder_level" type="number" min="0" step="0.01" value="10"></div><div><label>Reorder quantity</label><input name="reorder_qty" type="number" min="0" step="0.01" value="20"></div><div><label>Unit cost ₹</label><input name="unit_cost" type="number" min="0" step="0.01" value="0"></div><div><label>Warehouse</label><input name="warehouse" value="Central Store"></div><div><label>Rack / location</label><input name="location" placeholder="Rack A-03"></div><div><label>Batch / expiry</label><input name="batch_no" placeholder="Batch no."></div><div><label>Expiry date</label><input name="expiry_date" type="date"></div><div class="full"><button class="btn primary">Add to live inventory</button></div></form></div></div>
<div class="panel"><div class="head"><h2>🛒 Raise Purchase Request</h2><span class="muted">Low-stock aware</span></div><div class="body"><div class="hint">Tip: use this for planned replenishment. The request can be approved/rejected before a PO is issued.</div><form method="post" action="{{url_for('admin_procurement_request')}}" class="formgrid"><div><label>Department</label><select name="department">{% for k,v in departments.items() %}<option value="{{k}}">{{v}}</option>{% endfor %}</select></div><div><label>Priority</label><select name="priority">{% for x in priorities %}<option>{{x}}</option>{% endfor %}</select></div><div class="full"><label>Inventory item</label><select name="item_id" required>{% for i in items %}<option value="{{i.id}}">{{i.sku}} · {{i.name}} · {{'%g'|format(i.on_hand)}} {{i.unit}} on hand</option>{% endfor %}</select></div><div><label>Quantity</label><input name="qty" type="number" min="0.01" step="0.01" required></div><div><label>Needed by</label><input name="needed_by" type="date" value="{{today}}"></div><div class="full"><label>Purpose</label><input name="purpose" required placeholder="Replenish emergency repair stock for Ward 7"></div><div class="full"><label>Notes</label><input name="notes" placeholder="Specification, justification, delivery instruction…"></div><div class="full"><button class="btn primary">Submit purchase request</button></div></form></div></div></div>
<div class="panel"><div class="head"><h2>📦 Live Inventory</h2><span class="muted">Low-stock items rise to the top</span></div><div class="table-wrap"><table class="table"><thead><tr><th>SKU / Item</th><th>Department</th><th>Stock</th><th>Reorder</th><th>Value</th><th>Warehouse</th><th>Status</th></tr></thead><tbody>{% for i in inventory %}<tr class="{{'low' if i.on_hand<=i.reorder_level else ''}}"><td><b>{{i.sku}}</b><div>{{i.name}}</div><span class="muted">{{i.category}}</span></td><td>{{i.department|title}}</td><td><b>{{'%g'|format(i.on_hand)}} {{i.unit}}</b><div class="meter"><i style="width:{{[100,(i.on_hand/(i.reorder_level or 1)*100)]|min}}%"></i></div></td><td>{{'%g'|format(i.reorder_level)}}<div class="muted">Order {{'%g'|format(i.reorder_qty)}}</div></td><td>₹{{'{:,.0f}'.format(i.on_hand*i.unit_cost)}}</td><td>{{i.warehouse}}<div class="muted">{{i.location or '—'}}</div></td><td>{% if i.on_hand<=i.reorder_level %}<span class="tag Pending">⚠ Reorder now</span>{% else %}<span class="tag Received">Healthy</span>{% endif %}</td></tr>{% else %}<tr><td colspan="7"><div class="empty">No inventory found.</div></td></tr>{% endfor %}</tbody></table></div></div>
<div class="grid2"><div class="panel"><div class="head"><h2>📋 Purchase Requests</h2><span class="muted">Approval queue</span></div><div class="table-wrap"><table class="table"><thead><tr><th>Request</th><th>Department / Priority</th><th>Purpose</th><th>Estimate</th><th>Status</th><th>Action</th></tr></thead><tbody>{% for r in requests %}<tr><td><b>{{r.request_no}}</b><div class="muted">{{r.created_at}}</div></td><td>{{r.department|title}}<br><span class="tag">{{r.priority}}</span></td><td>{{r.purpose}}<div class="muted">{{r.item_count}} line item(s)</div></td><td>₹{{'{:,.0f}'.format(r.total_estimate)}}</td><td><span class="tag {{r.status}}">{{r.status}}</span></td><td>{% if r.status=='Pending' %}<div class="small-actions"><form method="post" action="{{url_for('admin_procurement_request_status',rid=r.id)}}"><input type="hidden" name="status" value="Approved"><button class="btn green">Approve</button></form><form method="post" action="{{url_for('admin_procurement_request_status',rid=r.id)}}"><input type="hidden" name="status" value="Rejected"><button class="btn red">Reject</button></form></div>{% else %}<span class="muted">{{r.requested_by}}</span>{% endif %}</td></tr>{% else %}<tr><td colspan="6"><div class="empty">No requests.</div></td></tr>{% endfor %}</tbody></table></div></div>
<div class="panel"><div class="head"><h2>🚚 Issue Purchase Order</h2><span class="muted">Supplier dispatch</span></div><div class="body"><form method="post" action="{{url_for('admin_procurement_po')}}" class="formgrid"><div><label>Supplier</label><select name="vendor_id" required><option value="">Select supplier</option>{% for v in vendors %}<option value="{{v.id}}">{{v.name}}</option>{% endfor %}</select></div><div><label>Department</label><select name="department">{% for k,v in departments.items() %}<option value="{{k}}">{{v}}</option>{% endfor %}</select></div><div class="full"><label>Item</label><select name="item_id">{% for i in items %}<option value="{{i.id}}">{{i.sku}} · {{i.name}}</option>{% endfor %}</select></div><div><label>Quantity</label><input name="qty" type="number" min="0.01" step="0.01" required></div><div><label>Unit cost ₹</label><input name="unit_cost" type="number" min="0" step="0.01" required></div><div><label>Expected delivery</label><input name="expected_date" type="date"></div><div><label>Notes</label><input name="notes" placeholder="Delivery / specification"></div><div class="full"><button class="btn dark">Issue purchase order</button></div></form></div></div></div>
<div class="panel"><div class="head"><h2>🚛 Purchase Orders & Goods Receipt</h2><span class="muted">Receiving updates stock automatically</span></div><div class="table-wrap"><table class="table"><thead><tr><th>PO</th><th>Supplier</th><th>Department</th><th>Total</th><th>Delivery</th><th>Receive</th></tr></thead><tbody>{% for p in purchase_orders %}<tr><td><b>{{p.po_no}}</b>{% if p.request_no %}<div class="muted">{{p.request_no}}</div>{% endif %}</td><td>{{p.vendor_name}}</td><td>{{p.department|title}}</td><td>₹{{'{:,.0f}'.format(p.total)}}</td><td><span class="tag {{p.status}}">{{p.status}}</span></td><td>{% if p.status in ('Issued','Partially Received') %}<form class="small-actions" method="post" action="{{url_for('admin_procurement_receive',poid=p.id)}}"><input name="received_qty" type="number" min="0.01" step="0.01" placeholder="Qty" style="width:90px"><button class="btn green">Receive</button></form>{% else %}<span class="muted">Complete</span>{% endif %}</td></tr>{% else %}<tr><td colspan="6"><div class="empty">No purchase orders.</div></td></tr>{% endfor %}</tbody></table></div></div>
<div class="panel"><div class="head"><h2>🔄 Stock Movement Console</h2><span class="muted">Issue, transfer or adjust stock</span></div><div class="body"><form method="post" action="{{url_for('admin_procurement_stock_move')}}" class="formgrid"><div><label>Item</label><select name="item_id">{% for i in items %}<option value="{{i.id}}">{{i.sku}} · {{i.name}} · {{'%g'|format(i.on_hand)}} {{i.unit}}</option>{% endfor %}</select></div><div><label>Movement</label><select name="movement_type"><option>Issue</option><option>Transfer</option><option>Adjustment+</option><option>Adjustment-</option></select></div><div><label>Quantity</label><input name="qty" type="number" min="0.01" step="0.01" required></div><div><label>To location</label><input name="to_location" placeholder="Ward 7 / Store B"></div><div class="full"><label>Reason</label><input name="reason" placeholder="Issued to field crew for road repair"></div><div class="full"><button class="btn purple">Record stock movement</button></div></form></div></div>
<div class="panel"><div class="head"><h2>🧾 Recent Stock Ledger</h2><span class="muted">Last 30 movements</span></div><div class="table-wrap"><table class="table"><thead><tr><th>Time</th><th>Item</th><th>Movement</th><th>Qty</th><th>Reference</th><th>Actor</th><th>Reason</th></tr></thead><tbody>{% for m in movements %}<tr><td>{{m.created_at}}</td><td><b>{{m.sku}}</b><div>{{m.name}}</div></td><td>{{m.movement_type}}</td><td>{{'%g'|format(m.qty)}}</td><td>{{m.reference_type or '—'}}{% if m.reference_id %} #{{m.reference_id}}{% endif %}</td><td>{{m.actor}}</td><td>{{m.reason or '—'}}</td></tr>{% else %}<tr><td colspan="7"><div class="empty">No stock movements yet.</div></td></tr>{% endfor %}</tbody></table></div></div>
</div></body></html>
"""

def init_finance_db():
    """Create and migrate CivicOS finance tables."""
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS finance_budgets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year TEXT NOT NULL,
            department TEXT NOT NULL,
            category TEXT NOT NULL,
            allocated_amount REAL NOT NULL DEFAULT 0,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(fiscal_year, department, category)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS finance_vendors(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            email TEXT,
            category TEXT,
            status TEXT DEFAULT 'Active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS finance_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_ref TEXT UNIQUE,
            txn_date TEXT NOT NULL,
            txn_type TEXT NOT NULL,
            department TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            vendor_id INTEGER,
            payment_method TEXT,
            status TEXT DEFAULT 'Pending',
            budget_id INTEGER,
            complaint_id INTEGER,
            asset_id INTEGER,
            created_by TEXT,
            approved_by TEXT,
            approved_at TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(vendor_id) REFERENCES finance_vendors(id) ON DELETE SET NULL,
            FOREIGN KEY(budget_id) REFERENCES finance_budgets(id) ON DELETE SET NULL,
            FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE SET NULL,
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE SET NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS finance_audit_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            actor TEXT,
            created_at TEXT NOT NULL
        )
    """)
    # Safe migrations for earlier finance-enabled copies.
    for name, definition in [
        ("fiscal_year", "TEXT"),
        ("department", "TEXT"),
        ("category", "TEXT"),
        ("allocated_amount", "REAL DEFAULT 0"),
        ("notes", "TEXT"),
        ("created_by", "TEXT"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
    ]:
        ensure_column(con, "finance_budgets", name, definition)
    for name, definition in [
        ("txn_ref", "TEXT"),
        ("txn_date", "TEXT"),
        ("txn_type", "TEXT"),
        ("department", "TEXT"),
        ("category", "TEXT"),
        ("description", "TEXT"),
        ("amount", "REAL DEFAULT 0"),
        ("vendor_id", "INTEGER"),
        ("payment_method", "TEXT"),
        ("status", "TEXT DEFAULT 'Pending'"),
        ("budget_id", "INTEGER"),
        ("complaint_id", "INTEGER"),
        ("asset_id", "INTEGER"),
        ("created_by", "TEXT"),
        ("approved_by", "TEXT"),
        ("approved_at", "TEXT"),
        ("notes", "TEXT"),
        ("created_at", "TEXT"),
        ("updated_at", "TEXT"),
    ]:
        ensure_column(con, "finance_transactions", name, definition)

    con.execute("CREATE INDEX IF NOT EXISTS idx_fin_budget_year_dept ON finance_budgets(fiscal_year, department)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fin_txn_date ON finance_transactions(txn_date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fin_txn_status ON finance_transactions(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fin_txn_dept ON finance_transactions(department)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fin_audit_created ON finance_audit_logs(created_at DESC)")

    # Seed a small, clearly-labelled demo ledger only when finance is empty.
    if con.execute("SELECT COUNT(*) AS c FROM finance_budgets").fetchone()["c"] == 0:
        fy = finance_current_fiscal_year()
        now = iso()
        demo = [
            (fy, "road", "Infrastructure", 2500000, "Demo planning allocation"),
            (fy, "water", "Maintenance", 1800000, "Demo preventive maintenance allocation"),
            (fy, "electricity", "Operations", 1400000, "Demo public lighting allocation"),
            (fy, "health", "Welfare", 1200000, "Demo public health allocation"),
        ]
        for row in demo:
            con.execute(
                """INSERT OR IGNORE INTO finance_budgets
                   (fiscal_year,department,category,allocated_amount,notes,created_by,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (*row, "system-demo", now, now)
            )
        # Demonstration ledger entries make the finance dashboard immediately useful
        # on a fresh hackathon database; they are clearly marked as demo records.
        vendor = con.execute("SELECT id FROM finance_vendors WHERE name='Civic Infrastructure Supplies (Demo)'").fetchone()
        if not vendor:
            cur = con.execute(
                """INSERT INTO finance_vendors(name,contact,email,category,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                ("Civic Infrastructure Supplies (Demo)","Demo vendor","demo@civicos.local","Municipal supplies","Active",now,now)
            )
            vendor_id=cur.lastrowid
        else:
            vendor_id=vendor["id"]
        road_budget=con.execute(
            "SELECT id FROM finance_budgets WHERE fiscal_year=? AND department='road' AND category='Infrastructure'",
            (fy,)
        ).fetchone()
        water_budget=con.execute(
            "SELECT id FROM finance_budgets WHERE fiscal_year=? AND department='water' AND category='Maintenance'",
            (fy,)
        ).fetchone()
        for txn_type, dept, category, desc, amount, budget_id, status, method in [
            ("Expense","road","Infrastructure","Ward road resurfacing materials (Demo)",325000,road_budget["id"] if road_budget else None,"Paid","Bank Transfer"),
            ("Expense","water","Maintenance","Water tank valve preventive maintenance (Demo)",145000,water_budget["id"] if water_budget else None,"Approved","Bank Transfer"),
            ("Income","health","Government Grant","Municipal public-health grant received (Demo)",500000,None,"Paid","Bank Transfer"),
        ]:
            ref=finance_next_ref(con,txn_type)
            con.execute(
                """INSERT INTO finance_transactions
                   (txn_ref,txn_date,txn_type,department,category,description,amount,vendor_id,
                    payment_method,status,budget_id,created_by,notes,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ref,datetime.now().strftime("%Y-%m-%d"),txn_type,dept,category,desc,amount,
                 vendor_id if txn_type=="Expense" else None,method,status,budget_id,
                 "system-demo","Demo record for CivicOS presentation",now,now)
            )
    con.commit()
    con.close()


def finance_current_fiscal_year(dt=None):
    dt = dt or datetime.now()
    start = dt.year if dt.month >= 4 else dt.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def finance_money(value):
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


FINANCE_DEPARTMENTS = dict(DEPARTMENTS)
FINANCE_TXN_TYPES = ("Expense", "Income", "Transfer")
FINANCE_STATUSES = ("Pending", "Approved", "Paid", "Rejected")
FINANCE_PAYMENT_METHODS = ("Bank Transfer", "UPI", "Cheque", "Cash", "Online", "Other")
FINANCE_EXPENSE_CATEGORIES = (
    "Operations", "Infrastructure", "Maintenance", "Welfare",
    "Salaries", "Technology", "Emergency", "Procurement", "Other"
)
FINANCE_INCOME_CATEGORIES = (
    "Government Grant", "Property Tax", "Service Fees", "Fines",
    "Donations", "Other Income"
)


def finance_audit(con, action, entity_type, entity_id=None, details=""):
    con.execute(
        """INSERT INTO finance_audit_logs(action,entity_type,entity_id,details,actor,created_at)
           VALUES(?,?,?,?,?,?)""",
        (action, entity_type, entity_id, details, session.get("admin", "system"), iso())
    )


def finance_effective_filter(alias=""):
    prefix = f"{alias}." if alias else ""
    return f"{prefix}status IN ('Approved','Paid')"


def finance_budget_rows(con, fiscal_year=None):
    fiscal_year = fiscal_year or finance_current_fiscal_year()
    rows = con.execute(
        """
        SELECT b.*,
               COALESCE((
                   SELECT SUM(t.amount) FROM finance_transactions t
                   WHERE t.budget_id=b.id AND t.txn_type='Expense'
                     AND t.status IN ('Approved','Paid')
               ),0) AS spent,
               COALESCE((
                   SELECT SUM(t.amount) FROM finance_transactions t
                   WHERE t.budget_id=b.id AND t.txn_type='Expense'
                     AND t.status='Pending'
               ),0) AS pending_spend
        FROM finance_budgets b
        WHERE b.fiscal_year=?
        ORDER BY b.department, b.category, b.id DESC
        """,
        (fiscal_year,)
    ).fetchall()
    output=[]
    for r in rows:
        allocated=finance_money(r["allocated_amount"])
        spent=finance_money(r["spent"])
        pending=finance_money(r["pending_spend"])
        remaining=allocated-spent
        utilization=(spent/allocated*100) if allocated else 0
        output.append({
            **dict(r),
            "allocated": allocated,
            "spent": spent,
            "pending_spend": pending,
            "remaining": remaining,
            "utilization": round(utilization,1),
        })
    return output


def finance_summary(con, fiscal_year=None):
    fiscal_year = fiscal_year or finance_current_fiscal_year()
    budgets = finance_budget_rows(con, fiscal_year)
    transactions = con.execute(
        """SELECT * FROM finance_transactions
           WHERE substr(txn_date,1,4) IN (?,?)
           ORDER BY txn_date DESC,id DESC""",
        (fiscal_year[:4], str(int(fiscal_year[:4])+1))
    ).fetchall()
    actual = [r for r in transactions if r["status"] in ("Approved","Paid")]
    income = sum(finance_money(r["amount"]) for r in actual if r["txn_type"]=="Income")
    expenses = sum(finance_money(r["amount"]) for r in actual if r["txn_type"]=="Expense")
    pending = sum(finance_money(r["amount"]) for r in transactions if r["status"]=="Pending")
    rejected = sum(finance_money(r["amount"]) for r in transactions if r["status"]=="Rejected")
    allocated = sum(r["allocated"] for r in budgets)
    spent = sum(r["spent"] for r in budgets)
    pending_budget = sum(r["pending_spend"] for r in budgets)
    by_dept=[]
    for key,label in FINANCE_DEPARTMENTS.items():
        dept_budget=sum(r["allocated"] for r in budgets if r["department"]==key)
        dept_spent=sum(r["spent"] for r in budgets if r["department"]==key)
        dept_income=sum(finance_money(r["amount"]) for r in actual if r["department"]==key and r["txn_type"]=="Income")
        by_dept.append({
            "key":key,"label":label,"budget":dept_budget,"spent":dept_spent,
            "income":dept_income,"remaining":dept_budget-dept_spent,
            "utilization":round(dept_spent/dept_budget*100,1) if dept_budget else 0
        })
    month_map={}
    for r in actual:
        month=r["txn_date"][:7]
        bucket=month_map.setdefault(month,{"income":0.0,"expense":0.0})
        if r["txn_type"]=="Income": bucket["income"]+=finance_money(r["amount"])
        elif r["txn_type"]=="Expense": bucket["expense"]+=finance_money(r["amount"])
    monthly=[{"month":k,"income":round(v["income"],2),"expense":round(v["expense"],2)}
             for k,v in sorted(month_map.items())]
    return {
        "fiscal_year":fiscal_year,"allocated":round(allocated,2),"spent":round(spent,2),
        "remaining":round(allocated-spent,2),"income":round(income,2),
        "expenses":round(expenses,2),"net":round(income-expenses,2),
        "pending":round(pending,2),"rejected":round(rejected,2),
        "pending_budget":round(pending_budget,2),
        "budget_utilization":round(spent/allocated*100,1) if allocated else 0,
        "transaction_count":len(transactions),
        "by_department":by_dept,"monthly":monthly
    }


def finance_next_ref(con, txn_type):
    prefix = {"Expense":"EXP","Income":"INC","Transfer":"TRF"}.get(txn_type,"FIN")
    for _ in range(100):
        stamp=datetime.now().strftime("%Y%m%d")
        seq=con.execute(
            "SELECT COUNT(*) AS c FROM finance_transactions WHERE txn_ref LIKE ?",
            (f"{prefix}-{stamp}-%",)
        ).fetchone()["c"] + 1
        ref=f"{prefix}-{stamp}-{seq:04d}"
        if not con.execute("SELECT 1 FROM finance_transactions WHERE txn_ref=?", (ref,)).fetchone():
            return ref
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"





@app.route("/admin/finance")
@login_required
def admin_finance():
    con=db()
    fiscal_year=(request.args.get("fy") or finance_current_fiscal_year()).strip()
    summary=finance_summary(con,fiscal_year)
    budgets=finance_budget_rows(con,fiscal_year)
    dept_filter=(request.args.get("department") or "").strip()
    status_filter=(request.args.get("status") or "").strip()
    search_query=(request.args.get("q") or "").strip()
    txns=con.execute(
        """SELECT t.*,v.name AS vendor_name,b.category AS budget_category,
                  a.asset_uid,a.name AS asset_name,c.title AS complaint_title
           FROM finance_transactions t
           LEFT JOIN finance_vendors v ON v.id=t.vendor_id
           LEFT JOIN finance_budgets b ON b.id=t.budget_id
           LEFT JOIN assets a ON a.id=t.asset_id
           LEFT JOIN complaints c ON c.id=t.complaint_id
           WHERE t.txn_date >= ? AND t.txn_date <= ?
           ORDER BY t.txn_date DESC,t.id DESC LIMIT 500""",
        (fiscal_year[:4]+"-04-01",str(int(fiscal_year[:4])+1)+"-03-31")
    ).fetchall()
    if dept_filter:
        txns=[r for r in txns if r["department"]==dept_filter]
    if status_filter:
        txns=[r for r in txns if r["status"]==status_filter]
    if search_query:
        needle=search_query.lower()
        txns=[r for r in txns if needle in " ".join(str(r[k] or "") for k in
              ("txn_ref","description","vendor_name","department","category","status")).lower()]
    vendors=con.execute("SELECT * FROM finance_vendors ORDER BY status DESC,name").fetchall()
    assets=con.execute("SELECT id,asset_uid,name,department FROM assets ORDER BY name").fetchall()
    complaints=con.execute("SELECT id,title,department FROM complaints ORDER BY id DESC LIMIT 100").fetchall()
    audits=con.execute("SELECT * FROM finance_audit_logs ORDER BY id DESC LIMIT 20").fetchall()
    context=admin_common_context(con)
    # admin_common_context() already contains a `complaints` key. Replace that
    # value with the Finance page's smaller complaint list before unpacking
    # the context, so render_template_string() never receives the same keyword
    # twice.
    context["complaints"] = complaints
    con.close()
    return render_template_string(FINANCE_TEMPLATE,
        finance_active=True, fiscal_year=fiscal_year, summary=summary,
        budgets=budgets, transactions=txns, vendors=vendors, assets=assets,
        audits=audits,
        finance_departments=FINANCE_DEPARTMENTS, finance_statuses=FINANCE_STATUSES,
        finance_txn_types=FINANCE_TXN_TYPES, finance_payment_methods=FINANCE_PAYMENT_METHODS,
        dept_filter=dept_filter, status_filter=status_filter, search_query=search_query,
        today=datetime.now().strftime("%Y-%m-%d"),
        expense_categories=FINANCE_EXPENSE_CATEGORIES, income_categories=FINANCE_INCOME_CATEGORIES,
        **context)


@app.route("/admin/finance/budget", methods=["POST"])
@login_required
def admin_finance_budget():
    fy=(request.form.get("fiscal_year") or finance_current_fiscal_year()).strip()
    dept=(request.form.get("department") or "").strip()
    category=(request.form.get("category") or "").strip()
    notes=(request.form.get("notes") or "").strip()
    try:
        amount=finance_validate_amount(request.form.get("allocated_amount"))
    except ValueError as exc:
        flash(str(exc),"danger")
        return redirect(url_for("admin_finance",fy=fy))
    if dept not in FINANCE_DEPARTMENTS or not category:
        flash("Select a valid department and budget category.","danger")
        return redirect(url_for("admin_finance",fy=fy))
    con=db()
    existing=con.execute(
        "SELECT id FROM finance_budgets WHERE fiscal_year=? AND department=? AND category=?",
        (fy,dept,category)
    ).fetchone()
    now=iso()
    if existing:
        con.execute(
            "UPDATE finance_budgets SET allocated_amount=?,notes=?,updated_at=? WHERE id=?",
            (amount,notes,now,existing["id"])
        )
        finance_audit(con,"Budget Updated","budget",existing["id"],f"{fy} / {dept} / {category} → ₹{amount:,.2f}")
        flash("Budget allocation updated.","success")
    else:
        cur=con.execute(
            """INSERT INTO finance_budgets
               (fiscal_year,department,category,allocated_amount,notes,created_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (fy,dept,category,amount,notes,session.get("admin","admin"),now,now)
        )
        finance_audit(con,"Budget Created","budget",cur.lastrowid,f"{fy} / {dept} / {category} → ₹{amount:,.2f}")
        flash("Budget allocation created.","success")
    con.commit(); con.close()
    return redirect(url_for("admin_finance",fy=fy))


@app.route("/admin/finance/budget/<int:bid>/delete", methods=["POST"])
@login_required
def admin_finance_budget_delete(bid):
    fy=request.form.get("fiscal_year") or finance_current_fiscal_year()
    con=db()
    budget=con.execute("SELECT * FROM finance_budgets WHERE id=?",(bid,)).fetchone()
    if not budget:
        con.close(); flash("Budget allocation not found.","warning")
        return redirect(url_for("admin_finance",fy=fy))
    used=con.execute("SELECT COUNT(*) AS c FROM finance_transactions WHERE budget_id=?",(bid,)).fetchone()["c"]
    if used:
        con.close(); flash("This budget cannot be deleted because transactions are linked to it.","warning")
        return redirect(url_for("admin_finance",fy=fy))
    con.execute("DELETE FROM finance_budgets WHERE id=?",(bid,))
    finance_audit(con,"Budget Deleted","budget",bid,f"{budget['fiscal_year']} / {budget['department']} / {budget['category']}")
    con.commit(); con.close()
    flash("Budget allocation deleted.","success")
    return redirect(url_for("admin_finance",fy=fy))


@app.route("/admin/finance/transaction", methods=["POST"])
@login_required
def admin_finance_transaction():
    txn_type=(request.form.get("txn_type") or "Expense").strip()
    dept=(request.form.get("department") or "").strip()
    category=(request.form.get("category") or "").strip()
    description=(request.form.get("description") or "").strip()
    fy=request.form.get("fiscal_year") or finance_current_fiscal_year()
    try:
        txn_date=finance_parse_date(request.form.get("txn_date") or datetime.now().strftime("%Y-%m-%d"))
        amount=finance_validate_amount(request.form.get("amount"))
    except ValueError as exc:
        flash(str(exc),"danger"); return redirect(url_for("admin_finance",fy=fy))
    if txn_type not in FINANCE_TXN_TYPES or dept not in FINANCE_DEPARTMENTS or not description:
        flash("Complete the transaction type, department and description.","danger")
        return redirect(url_for("admin_finance",fy=fy))
    allowed_categories=FINANCE_INCOME_CATEGORIES if txn_type=="Income" else FINANCE_EXPENSE_CATEGORIES
    if category not in allowed_categories:
        flash("Select a valid transaction category.","danger")
        return redirect(url_for("admin_finance",fy=fy))
    try:
        vendor_id=int(request.form.get("vendor_id")) if request.form.get("vendor_id") else None
        budget_id=int(request.form.get("budget_id")) if request.form.get("budget_id") else None
        complaint_id=int(request.form.get("complaint_id")) if request.form.get("complaint_id") else None
        asset_id=int(request.form.get("asset_id")) if request.form.get("asset_id") else None
    except ValueError:
        flash("Invalid linked record selected.","danger"); return redirect(url_for("admin_finance",fy=fy))
    payment=(request.form.get("payment_method") or "").strip() or None
    notes=(request.form.get("notes") or "").strip()
    status="Pending"
    con=db()
    if vendor_id and not con.execute("SELECT 1 FROM finance_vendors WHERE id=?",(vendor_id,)).fetchone():
        con.close(); flash("Selected vendor was not found.","danger"); return redirect(url_for("admin_finance",fy=fy))
    if budget_id:
        budget=con.execute("SELECT * FROM finance_budgets WHERE id=?",(budget_id,)).fetchone()
        if not budget or budget["department"]!=dept:
            con.close(); flash("The selected budget does not belong to the chosen department.","danger"); return redirect(url_for("admin_finance",fy=fy))
        if txn_type!="Expense":
            con.close(); flash("Budgets can only be linked to expense transactions.","danger"); return redirect(url_for("admin_finance",fy=fy))
        spent=con.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM finance_transactions WHERE budget_id=? AND txn_type='Expense' AND status IN ('Approved','Paid')",
            (budget_id,)
        ).fetchone()["s"]
        if finance_money(spent)+amount > finance_money(budget["allocated_amount"]):
            con.close(); flash("This expense exceeds the selected budget's available allocation.","danger"); return redirect(url_for("admin_finance",fy=fy))
    if complaint_id and not con.execute("SELECT 1 FROM complaints WHERE id=?",(complaint_id,)).fetchone():
        complaint_id=None
    if asset_id and not con.execute("SELECT 1 FROM assets WHERE id=?",(asset_id,)).fetchone():
        asset_id=None
    ref=finance_next_ref(con,txn_type)
    now=iso()
    cur=con.execute(
        """INSERT INTO finance_transactions
           (txn_ref,txn_date,txn_type,department,category,description,amount,vendor_id,
            payment_method,status,budget_id,complaint_id,asset_id,created_by,notes,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ref,txn_date,txn_type,dept,category,description,amount,vendor_id,payment,status,budget_id,
         complaint_id,asset_id,session.get("admin","admin"),notes,now,now)
    )
    finance_audit(con,"Transaction Created","transaction",cur.lastrowid,f"{ref} · {txn_type} · ₹{amount:,.2f}")
    con.commit(); con.close()
    flash(f"{ref} created and sent for approval.","success")
    return redirect(url_for("admin_finance",fy=fy))


@app.route("/admin/finance/transaction/<int:tid>/status", methods=["POST"])
@login_required
def admin_finance_transaction_status(tid):
    new_status=(request.form.get("status") or "").strip()
    fy=request.form.get("fiscal_year") or finance_current_fiscal_year()
    if new_status not in FINANCE_STATUSES:
        flash("Invalid finance status.","danger"); return redirect(url_for("admin_finance",fy=fy))
    con=db()
    txn=con.execute("SELECT * FROM finance_transactions WHERE id=?",(tid,)).fetchone()
    if not txn:
        con.close(); flash("Transaction not found.","warning"); return redirect(url_for("admin_finance",fy=fy))
    current=txn["status"]
    allowed={
        "Pending":{"Approved","Rejected"},
        "Approved":{"Paid","Rejected"},
        "Paid":set(),
        "Rejected":{"Pending"},
    }
    if new_status not in allowed.get(current,set()):
        con.close(); flash(f"Cannot change {current} transaction to {new_status}.","warning")
        return redirect(url_for("admin_finance",fy=fy))
    if new_status in {"Approved","Paid"} and txn["txn_type"]=="Expense" and txn["budget_id"]:
        budget=con.execute("SELECT * FROM finance_budgets WHERE id=?",(txn["budget_id"],)).fetchone()
        if budget:
            spent=con.execute(
                """SELECT COALESCE(SUM(amount),0) AS s FROM finance_transactions
                   WHERE budget_id=? AND txn_type='Expense' AND status IN ('Approved','Paid') AND id!=?""",
                (txn["budget_id"],tid)
            ).fetchone()["s"]
            if finance_money(spent)+finance_money(txn["amount"]) > finance_money(budget["allocated_amount"]):
                con.close(); flash("Approval blocked: this transaction would exceed its budget.","danger")
                return redirect(url_for("admin_finance",fy=fy))
    now=iso()
    if new_status=="Approved":
        con.execute("UPDATE finance_transactions SET status=?,approved_by=?,approved_at=?,updated_at=? WHERE id=?",
                    (new_status,session.get("admin","admin"),now,now,tid))
    else:
        con.execute("UPDATE finance_transactions SET status=?,updated_at=? WHERE id=?",(new_status,now,tid))
    finance_audit(con,"Transaction Status Changed","transaction",tid,f"{txn['txn_ref']}: {current} → {new_status}")
    con.commit(); con.close()
    flash(f"{txn['txn_ref']} marked {new_status}.","success")
    return redirect(url_for("admin_finance",fy=fy))


@app.route("/admin/finance/vendor", methods=["POST"])
@login_required
def admin_finance_vendor():
    name=(request.form.get("name") or "").strip()
    contact=(request.form.get("contact") or "").strip()
    email=(request.form.get("email") or "").strip()
    category=(request.form.get("category") or "").strip()
    if not name:
        flash("Vendor name is required.","danger"); return redirect(url_for("admin_finance"))
    if email and not valid_email(email):
        flash("Enter a valid vendor email.","danger"); return redirect(url_for("admin_finance"))
    con=db(); now=iso()
    cur=con.execute(
        "INSERT INTO finance_vendors(name,contact,email,category,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (name,contact,email,category,"Active",now,now)
    )
    finance_audit(con,"Vendor Created","vendor",cur.lastrowid,name)
    con.commit(); con.close()
    flash("Vendor added to the finance register.","success")
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/vendor/<int:vid>/status", methods=["POST"])
@login_required
def admin_finance_vendor_status(vid):
    status=(request.form.get("status") or "").strip()
    if status not in {"Active","Inactive"}:
        flash("Invalid vendor status.","danger"); return redirect(url_for("admin_finance"))
    con=db()
    vendor=con.execute("SELECT * FROM finance_vendors WHERE id=?",(vid,)).fetchone()
    if not vendor:
        con.close(); flash("Vendor not found.","warning"); return redirect(url_for("admin_finance"))
    con.execute("UPDATE finance_vendors SET status=?,updated_at=? WHERE id=?",(status,iso(),vid))
    finance_audit(con,"Vendor Status Changed","vendor",vid,f"{vendor['name']}: {status}")
    con.commit(); con.close()
    flash(f"Vendor {vendor['name']} is now {status.lower()}.","success")
    return redirect(url_for("admin_finance"))


@app.route("/admin/finance/export")
@login_required
def admin_finance_export():
    fy=(request.args.get("fy") or finance_current_fiscal_year()).strip()
    con=db()
    rows=con.execute(
        """SELECT t.*,v.name AS vendor_name,b.fiscal_year AS budget_fy,
                  b.category AS budget_category,a.asset_uid,c.title AS complaint_title
           FROM finance_transactions t
           LEFT JOIN finance_vendors v ON v.id=t.vendor_id
           LEFT JOIN finance_budgets b ON b.id=t.budget_id
           LEFT JOIN assets a ON a.id=t.asset_id
           LEFT JOIN complaints c ON c.id=t.complaint_id
           WHERE t.txn_date >= ? AND t.txn_date <= ?
           ORDER BY t.txn_date ASC,t.id ASC""",
        (fy[:4]+"-04-01",str(int(fy[:4])+1)+"-03-31")
    ).fetchall()
    con.close()
    out=io.StringIO()
    writer=csv.writer(out)
    writer.writerow(["Transaction Ref","Date","Type","Department","Category","Description","Amount (INR)",
                     "Vendor","Payment Method","Status","Budget","Complaint ID","Asset UID","Created By","Approved By","Notes"])
    for r in rows:
        writer.writerow([r["txn_ref"],r["txn_date"],r["txn_type"],department_label(r["department"]),r["category"],
                         r["description"],r["amount"],r["vendor_name"] or "",r["payment_method"] or "",r["status"],
                         r["budget_category"] or "",r["complaint_id"] or "",r["asset_uid"] or "",
                         r["created_by"] or "",r["approved_by"] or "",r["notes"] or ""])
    payload=io.BytesIO(out.getvalue().encode("utf-8-sig")); payload.seek(0)
    return send_file(payload,mimetype="text/csv",as_attachment=True,
                     download_name=f"CivicOS_Finance_{fy}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")


@app.route("/api/admin/finance/summary")
@login_required
def api_admin_finance_summary():
    con=db()
    data=finance_summary(con,(request.args.get("fy") or finance_current_fiscal_year()).strip())
    con.close()
    return jsonify(ok=True,**data)


FINANCE_TEMPLATE = r"""
<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finance · CivicOS</title>
<style>
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f4f7fb;--panel:#fff;--blue:#2563eb;--green:#059669;--red:#dc2626;--amber:#d97706;--purple:#7c3aed;--shadow:0 12px 35px rgba(15,23,42,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{text-decoration:none;color:inherit}.wrap{max-width:1500px;margin:auto;padding:22px}.top{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;margin-bottom:18px}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.14em;font-weight:900;color:var(--blue)}h1{margin:4px 0;font-size:30px;letter-spacing:-.03em}.muted{color:var(--muted);font-size:12px}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:0;border-radius:10px;padding:9px 13px;font-weight:800;cursor:pointer;display:inline-flex;align-items:center;gap:6px}.primary{background:var(--blue);color:#fff}.soft{background:#eaf2ff;color:#1d4ed8}.green{background:#ecfdf5;color:#047857}.dark{background:#0f172a;color:#fff}.red{background:#fee2e2;color:#b91c1c}.amber{background:#fff7ed;color:#b45309}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:18px}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:15px;box-shadow:var(--shadow)}.kpi small{display:block;color:var(--muted);font-weight:800;text-transform:uppercase;font-size:10px}.kpi strong{display:block;font-size:24px;margin-top:4px}.green-text{color:var(--green)}.red-text{color:var(--red)}.purple-text{color:var(--purple)}
.grid2{display:grid;grid-template-columns:1.15fr .85fr;gap:16px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);overflow:hidden;margin-bottom:16px}.head{padding:15px 17px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px;align-items:center}.head h2{font-size:16px;margin:0}.body{padding:16px}
.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.full{grid-column:1/-1}label{font-size:10px;font-weight:900;color:#475569;text-transform:uppercase;display:block;margin-bottom:4px}input,select,textarea{width:100%;padding:9px 10px;border:1px solid #cbd5e1;border-radius:10px;font:inherit;background:#fff}textarea{min-height:70px}
.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse;min-width:920px}.table th,.table td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.table th{font-size:10px;text-transform:uppercase;color:var(--muted);background:#f8fafc;position:sticky;top:0}.table td{font-size:12px}.right{text-align:right!important}.ref{font-weight:900;color:var(--blue)}.tag{display:inline-block;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900;background:#f1f5f9}.tag.Pending{background:#fff7ed;color:#b45309}.tag.Approved{background:#eff6ff;color:#1d4ed8}.tag.Paid{background:#ecfdf5;color:#047857}.tag.Rejected{background:#fee2e2;color:#b91c1c}
.progress{height:8px;background:#e2e8f0;border-radius:99px;overflow:hidden}.progress i{display:block;height:100%;background:var(--blue)}.dept{margin-bottom:14px}.dept:last-child{margin-bottom:0}.depttop{display:flex;justify-content:space-between;gap:10px;font-size:12px;font-weight:800}.chart{display:flex;align-items:flex-end;gap:7px;height:170px;padding:10px 4px 0;border-bottom:1px solid var(--line)}.barbox{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:25px}.bars{height:135px;display:flex;align-items:flex-end;gap:3px}.bar{width:10px;border-radius:4px 4px 0 0;min-height:2px}.bar.income{background:#10b981}.bar.expense{background:#ef4444}.month{font-size:9px;color:var(--muted);margin-top:6px;white-space:nowrap;transform:rotate(-35deg);transform-origin:top center}.legend{display:flex;gap:14px;font-size:11px;color:var(--muted);margin-top:12px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}.dot.in{background:#10b981}.dot.ex{background:#ef4444}
.flash{padding:11px 14px;border-radius:11px;margin-bottom:12px;background:#eff6ff;color:#1d4ed8}.empty{padding:25px;text-align:center;color:var(--muted);border:1px dashed #cbd5e1;border-radius:12px}.tabs{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:16px}.tab{padding:8px 11px;border:1px solid var(--line);border-radius:10px;background:#fff;font-weight:800;font-size:12px}.tab.active{background:#0f172a;color:#fff}.audit{padding:9px 0;border-bottom:1px solid var(--line);font-size:12px}.audit:last-child{border-bottom:0}.small-actions{display:flex;gap:5px;flex-wrap:wrap}.small-actions .btn{padding:6px 8px;font-size:10px}.filter{display:grid;grid-template-columns:1fr 170px 150px auto;gap:8px;margin-bottom:10px}
@media(max-width:1200px){.kpis{grid-template-columns:repeat(3,1fr)}}@media(max-width:900px){.grid2{grid-template-columns:1fr}.filter{grid-template-columns:1fr 1fr}.top{flex-direction:column}}@media(max-width:600px){.wrap{padding:12px}.kpis{grid-template-columns:1fr 1fr}.formgrid{grid-template-columns:1fr}.full{grid-column:auto}}
</style></head>
<body><div class="wrap">
<div class="top"><div><div class="eyebrow">CivicOS · Administration</div><h1>Finance</h1><div class="muted">Budget control, public expenditure, revenue, approvals, vendors and audit visibility in one ledger.</div></div>
<div class="actions"><a class="btn soft" href="{{url_for('admin')}}">← Command Center</a><a class="btn dark" href="{{url_for('admin_finance_export',fy=fiscal_year)}}">Export CSV</a></div></div>

{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash">{{message}}</div>{% endfor %}{% endwith %}

<div class="tabs"><a class="tab active" href="{{url_for('admin_finance',fy=fiscal_year)}}">Overview</a><a class="tab" href="#budgets">Budgets</a><a class="tab" href="#transactions">Transactions</a><a class="tab" href="#vendors">Vendors</a><a class="tab" href="#audit">Audit Trail</a></div>

<form class="filter" method="get" action="{{url_for('admin_finance')}}">
<input name="fy" value="{{fiscal_year}}" placeholder="Fiscal year e.g. 2026-27">
<select name="department"><option value="">All departments</option>{% for k,v in finance_departments.items() %}<option value="{{k}}" {% if dept_filter==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select>
<select name="status"><option value="">All statuses</option>{% for s in finance_statuses %}<option {% if status_filter==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select>
<button class="btn primary">Refresh</button>
<input name="q" value="{{search_query}}" placeholder="Search ledger…"></form>

<div class="kpis">
<div class="kpi"><small>Allocated Budget</small><strong>₹{{'{:,.0f}'.format(summary.allocated)}}</strong></div>
<div class="kpi"><small>Actual Expenditure</small><strong class="red-text">₹{{'{:,.0f}'.format(summary.expenses)}}</strong></div>
<div class="kpi"><small>Budget Utilization</small><strong>{{summary.budget_utilization}}%</strong></div>
<div class="kpi"><small>Revenue Received</small><strong class="green-text">₹{{'{:,.0f}'.format(summary.income)}}</strong></div>
<div class="kpi"><small>Net Position</small><strong class="{{'green-text' if summary.net>=0 else 'red-text'}}">₹{{'{:,.0f}'.format(summary.net)}}</strong></div>
<div class="kpi"><small>Pending Approvals</small><strong class="purple-text">₹{{'{:,.0f}'.format(summary.pending)}}</strong></div>
</div>

<div class="grid2">
<div class="panel"><div class="head"><h2>Monthly Cash Activity</h2><span class="muted">{{summary.transaction_count}} ledger entries</span></div><div class="body">
{% if summary.monthly %}<div class="chart">{% set maxv=1 %}{% for m in summary.monthly %}{% if m.income>maxv %}{% set maxv=m.income %}{% endif %}{% if m.expense>maxv %}{% set maxv=m.expense %}{% endif %}{% endfor %}{% for m in summary.monthly %}<div class="barbox"><div class="bars"><div class="bar income" title="Income ₹{{m.income|round(0)}}" style="height:{{(m.income/maxv*130)|round(0)}}px"></div><div class="bar expense" title="Expense ₹{{m.expense|round(0)}}" style="height:{{(m.expense/maxv*130)|round(0)}}px"></div></div><div class="month">{{m.month}}</div></div>{% endfor %}</div><div class="legend"><span><i class="dot in"></i>Income</span><span><i class="dot ex"></i>Expense</span></div>{% else %}<div class="empty">No approved or paid transactions yet. Create a transaction below to populate the financial trend.</div>{% endif %}
</div></div>

<div class="panel"><div class="head"><h2>Department Budget Health</h2></div><div class="body">{% for d in summary.by_department %}<div class="dept"><div class="depttop"><span>{{d.label}}</span><span>₹{{'{:,.0f}'.format(d.spent)}} / ₹{{'{:,.0f}'.format(d.budget)}}</span></div><div class="progress" style="margin-top:6px"><i style="width:{{[d.utilization,100]|min}}%"></i></div><div class="muted" style="margin-top:3px">{{d.utilization}}% used · ₹{{'{:,.0f}'.format(d.remaining)}} remaining</div></div>{% endfor %}</div></div>
</div>

<div class="panel" id="budgets"><div class="head"><h2>Budget Planning & Allocation</h2><span class="muted">Fiscal year {{fiscal_year}}</span></div><div class="body"><form method="post" action="{{url_for('admin_finance_budget')}}" class="formgrid">
<input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><div><label>Department</label><select name="department" required>{% for k,v in finance_departments.items() %}<option value="{{k}}">{{v}}</option>{% endfor %}</select></div><div><label>Budget category</label><select name="category" required>{% for c in expense_categories %}<option>{{c}}</option>{% endfor %}</select></div><div><label>Allocated amount (₹)</label><input type="number" name="allocated_amount" min="1" step="100" required></div><div><label>Planning notes</label><input name="notes" placeholder="Purpose / funding source / approval note"></div><div class="full"><button class="btn primary">Save Budget Allocation</button></div></form>
<div class="table-wrap" style="margin-top:16px"><table class="table"><thead><tr><th>Department</th><th>Category</th><th>Allocated</th><th>Spent</th><th>Pending</th><th>Remaining</th><th>Usage</th><th>Action</th></tr></thead><tbody>{% for b in budgets %}<tr><td>{{department_label(b.department)}}</td><td>{{b.category}}</td><td>₹{{'{:,.0f}'.format(b.allocated)}}</td><td>₹{{'{:,.0f}'.format(b.spent)}}</td><td>₹{{'{:,.0f}'.format(b.pending_spend)}}</td><td class="{{'red-text' if b.remaining<0 else 'green-text'}}">₹{{'{:,.0f}'.format(b.remaining)}}</td><td>{{b.utilization}}%</td><td><form method="post" action="{{url_for('admin_finance_budget_delete',bid=b.id)}}" onsubmit="return confirm('Delete this unused budget allocation?')"><input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><button class="btn red" {% if b.spent or b.pending_spend %}disabled title="Linked transactions prevent deletion"{% endif %}>Delete</button></form></td></tr>{% else %}<tr><td colspan="8"><div class="empty">No budget allocations for this fiscal year.</div></td></tr>{% endfor %}</tbody></table></div></div></div>

<div class="panel" id="transactions"><div class="head"><h2>Transaction & Approval Ledger</h2><span class="muted">Every entry starts Pending for authority review.</span></div><div class="body">
<form method="post" action="{{url_for('admin_finance_transaction')}}" class="formgrid">
<input type="hidden" name="fiscal_year" value="{{fiscal_year}}">
<div><label>Transaction type</label><select id="txnType" name="txn_type" onchange="updateCategories()" required>{% for x in finance_txn_types %}<option>{{x}}</option>{% endfor %}</select></div>
<div><label>Date</label><input type="date" name="txn_date" value="{{today}}" required></div>
<div><label>Department</label><select name="department" required>{% for k,v in finance_departments.items() %}<option value="{{k}}">{{v}}</option>{% endfor %}</select></div>
<div><label>Category</label><select id="txnCategory" name="category" required></select></div>
<div class="full"><label>Description</label><input name="description" required placeholder="e.g. Streetlight replacement materials for Ward 4"></div>
<div><label>Amount (₹)</label><input type="number" name="amount" min="1" step="0.01" required></div>
<div><label>Vendor</label><select name="vendor_id"><option value="">No vendor</option>{% for v in vendors %}<option value="{{v.id}}">{{v.name}}{% if v.status!='Active' %} · Inactive{% endif %}</option>{% endfor %}</select></div>
<div><label>Payment method</label><select name="payment_method"><option value="">Not paid yet</option>{% for x in finance_payment_methods %}<option>{{x}}</option>{% endfor %}</select></div>
<div><label>Expense budget</label><select name="budget_id"><option value="">No budget link</option>{% for b in budgets %}<option value="{{b.id}}">{{department_label(b.department)}} · {{b.category}} · ₹{{'{:,.0f}'.format(b.remaining) }} left</option>{% endfor %}</select></div>
<div><label>Related complaint</label><select name="complaint_id"><option value="">None</option>{% for c in complaints %}<option value="{{c.id}}">#{{c.id}} · {{c.title}}</option>{% endfor %}</select></div>
<div><label>Related asset</label><select name="asset_id"><option value="">None</option>{% for a in assets %}<option value="{{a.id}}">{{a.asset_uid}} · {{a.name}}</option>{% endfor %}</select></div>
<div><label>Notes</label><input name="notes" placeholder="Invoice / voucher / audit note"></div>
<div class="full"><button class="btn primary">Create Finance Transaction</button></div>
</form>
<div style="margin-top:18px"><input id="txnSearch" placeholder="Search transaction reference, vendor, description or department…" oninput="filterTransactions()"></div>
<div class="table-wrap" style="margin-top:8px"><table class="table" id="txnTable"><thead><tr><th>Ref / Date</th><th>Type</th><th>Department</th><th>Description</th><th>Amount</th><th>Vendor</th><th>Status</th><th>Authority Action</th></tr></thead><tbody>{% for trow in transactions %}<tr><td><div class="ref">{{trow.txn_ref}}</div><div class="muted">{{trow.txn_date}}</div></td><td>{{trow.txn_type}}</td><td>{{department_label(trow.department)}}<br><span class="muted">{{trow.category}}</span></td><td>{{trow.description}}{% if trow.notes %}<div class="muted">{{trow.notes}}</div>{% endif %}{% if trow.complaint_id %}<div class="muted">Complaint #{{trow.complaint_id}}</div>{% endif %}{% if trow.asset_uid %}<div class="muted">Asset {{trow.asset_uid}}</div>{% endif %}</td><td><b>₹{{'{:,.2f}'.format(trow.amount)}}</b></td><td>{{trow.vendor_name or '—'}}</td><td><span class="tag {{trow.status}}">{{trow.status}}</span></td><td><div class="small-actions">{% if trow.status=='Pending' %}<form method="post" action="{{url_for('admin_finance_transaction_status',tid=trow.id)}}"><input type="hidden" name="status" value="Approved"><input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><button class="btn green">Approve</button></form><form method="post" action="{{url_for('admin_finance_transaction_status',tid=trow.id)}}"><input type="hidden" name="status" value="Rejected"><input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><button class="btn red">Reject</button></form>{% elif trow.status=='Approved' %}<form method="post" action="{{url_for('admin_finance_transaction_status',tid=trow.id)}}"><input type="hidden" name="status" value="Paid"><input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><button class="btn green">Mark Paid</button></form><form method="post" action="{{url_for('admin_finance_transaction_status',tid=trow.id)}}"><input type="hidden" name="status" value="Rejected"><input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><button class="btn red">Reject</button></form>{% elif trow.status=='Rejected' %}<form method="post" action="{{url_for('admin_finance_transaction_status',tid=trow.id)}}"><input type="hidden" name="status" value="Pending"><input type="hidden" name="fiscal_year" value="{{fiscal_year}}"><button class="btn amber">Reopen</button></form>{% else %}<span class="muted">Final</span>{% endif %}</div></td></tr>{% else %}<tr><td colspan="8"><div class="empty">No finance transactions found for this fiscal year.</div></td></tr>{% endfor %}</tbody></table></div></div></div>

<div class="grid2">
<div class="panel" id="vendors"><div class="head"><h2>Vendor Register</h2><span class="muted">{{vendors|length}} vendor(s)</span></div><div class="body"><form method="post" action="{{url_for('admin_finance_vendor')}}" class="formgrid"><div><label>Vendor / supplier name</label><input name="name" required></div><div><label>Contact</label><input name="contact"></div><div><label>Email</label><input type="email" name="email"></div><div><label>Service category</label><input name="category" placeholder="Construction / supplies / IT"></div><div class="full"><button class="btn primary">Add Vendor</button></div></form><div style="margin-top:14px">{% for v in vendors %}<div class="audit"><b>{{v.name}}</b> · {{v.category or 'General'}}<div class="muted">{{v.contact or 'No contact'}}{% if v.email %} · {{v.email}}{% endif %}</div><form method="post" action="{{url_for('admin_finance_vendor_status',vid=v.id)}}" style="margin-top:5px"><input type="hidden" name="status" value="{{'Inactive' if v.status=='Active' else 'Active'}}"><button class="btn {{'red' if v.status=='Active' else 'green'}}">{{'Deactivate' if v.status=='Active' else 'Activate'}}</button></form></div>{% else %}<div class="empty">No vendors registered.</div>{% endfor %}</div></div></div>

<div class="panel" id="audit"><div class="head"><h2>Finance Audit Trail</h2><span class="muted">Latest 20 events</span></div><div class="body">{% for a in audits %}<div class="audit"><b>{{a.action}}</b> · {{a.entity_type}}{% if a.entity_id %} #{{a.entity_id}}{% endif %}<div>{{a.details}}</div><div class="muted">{{a.actor or 'system'}} · {{a.created_at}}</div></div>{% else %}<div class="empty">No finance audit events yet.</div>{% endfor %}</div></div>
</div>

</div>
<script>
const expenseCategories={{expense_categories|tojson}},incomeCategories={{income_categories|tojson}};
function updateCategories(){const type=document.getElementById('txnType').value;const arr=type==='Income'?incomeCategories:expenseCategories;const el=document.getElementById('txnCategory');el.innerHTML=arr.map(x=>'<option value="'+x.replace(/"/g,'&quot;')+'">'+x+'</option>').join('');}
function filterTransactions(){const q=(document.getElementById('txnSearch').value||'').toLowerCase();document.querySelectorAll('#txnTable tbody tr').forEach(tr=>{tr.style.display=tr.innerText.toLowerCase().includes(q)?'':'none';});}
updateCategories();
</script>
</body></html>
"""


def sync_escalations():
    con = db()
    rows = con.execute("SELECT * FROM complaints WHERE status!='Resolved' AND escalated=0").fetchall()
    email_jobs = []
    changed = False
    for row in rows:
        deadline = parse_dt(row["sla_deadline"])
        if deadline and datetime.now() > deadline:
            priority = service_priority(
                row["title"],
                row["description"],
                row["category"],
                bool(row["emergency"]),
                row["upvotes"],
                True,
            )
            con.execute(
                "UPDATE complaints SET escalated=1, priority=?, updated_at=? WHERE id=?",
                (priority, iso(), row["id"]),
            )
            add_timeline(con, row["id"], "SLA Escalated", "Automatic escalation triggered because the SLA deadline passed.")
            create_notification(
                con,
                row["id"],
                "SLA escalation",
                "Your complaint crossed its service deadline and has been automatically escalated for senior attention.",
                "warning",
            )
            email_jobs.append((row["id"], "CivicOS: complaint escalated", "Your CivicOS complaint has been automatically escalated because its SLA deadline passed."))
            changed = True
    if changed:
        con.commit()
    con.close()
    for job in email_jobs:
        send_optional_email(*job)


def assign_next_pending(con, worker_id):
    worker = get_worker(worker_id)
    if not worker or worker_active_task(con, worker_id):
        return None
    queue = con.execute(
        """
        SELECT * FROM complaints
        WHERE department=? AND status='Pending' AND (assigned_worker IS NULL OR TRIM(assigned_worker)='')
        ORDER BY emergency DESC, escalated DESC, priority DESC, created_at ASC, id ASC
        """,
        (worker["department"],),
    ).fetchall()
    if not queue:
        return None
    # Prefer a skill match among the highest-priority queue without violating priority badly.
    ranked = sorted(
        queue,
        key=lambda row: (
            int(row["emergency"] or 0),
            int(row["escalated"] or 0),
            int(row["priority"] or 0),
            worker_skill_score(worker, row["required_skill"]),
            -int(row["id"]),
        ),
        reverse=True,
    )
    next_task = ranked[0]

    # "Never spend the last resource": automatic queue pull must obey the same
    # reserve-capacity rule as first-time smart assignment.
    dept_workers = [w for w in WORKERS if w["department"] == worker["department"] and w.get("available", True)]
    idle_workers = [w for w in dept_workers if not worker_active_task(con, w["id"])]
    reserve_enabled = get_setting(con, "reserve_guard_enabled", "1") == "1"
    disaster_mode = get_setting(con, "disaster_mode", "0") == "1"
    protected_slots = 1 if reserve_enabled and len(dept_workers) >= 2 else 0
    if disaster_mode and len(dept_workers) >= 3:
        protected_slots = max(protected_slots, 2)
    task_is_critical = bool(next_task["emergency"]) or int(next_task["priority"] or 0) >= 85
    if protected_slots and len(idle_workers) <= protected_slots and not task_is_critical:
        add_timeline(
            con,
            next_task["id"],
            "Reserve Capacity Protected",
            "Automatic assignment paused so the department keeps its final emergency-response team available.",
        )
        return None

    con.execute(
        "UPDATE complaints SET assigned_worker=?, status='Assigned', assigned_at=?, updated_at=? WHERE id=?",
        (worker_id, iso(), iso(), next_task["id"]),
    )
    add_timeline(
        con,
        next_task["id"],
        "Queue Auto-Assignment",
        f"{worker_label(worker_id)} became available and CivicOS assigned the next queued task automatically.",
    )
    create_notification(
        con,
        next_task["id"],
        "Field team assigned",
        f"{worker_label(worker_id)} is now assigned to your complaint.",
        "success",
    )
    return next_task["id"]


def get_stats(con):
    rows = con.execute("SELECT * FROM complaints").fetchall()
    total = len(rows)
    active = [row for row in rows if row["status"] != "Resolved"]
    resolved = [row for row in rows if row["status"] == "Resolved"]
    today = datetime.now().date()
    resolved_today = sum(1 for row in resolved if parse_dt(row["resolved_at"]) and parse_dt(row["resolved_at"]).date() == today)
    compliant = 0
    measurable = 0
    for row in rows:
        deadline = parse_dt(row["sla_deadline"])
        if not deadline:
            continue
        measurable += 1
        if row["status"] == "Resolved":
            resolved_at = parse_dt(row["resolved_at"])
            if resolved_at and resolved_at <= deadline:
                compliant += 1
        elif not row["escalated"] and datetime.now() <= deadline:
            compliant += 1
    category_counts = {key: 0 for key in CATEGORY_LABELS if key != "auto"}
    for row in rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    feedback_row = con.execute("SELECT AVG(rating) AS avg_rating FROM feedback").fetchone()
    return {
        "total": total,
        "pending": len(active),
        "active": len(active),
        "resolved": len(resolved),
        "resolved_today": resolved_today,
        "emergency": sum(1 for row in rows if row["emergency"]),
        "escalated": sum(1 for row in active if row["escalated"]),
        "sla_compliance": round((compliant / measurable) * 100, 1) if measurable else 100.0,
        "feedback": round(float(feedback_row["avg_rating"] or 0), 1),
        "category_counts": category_counts,
    }


def calculate_department_performance(con):
    output = []
    for key, label in DEPARTMENTS.items():
        rows = con.execute("SELECT * FROM complaints WHERE department=?", (key,)).fetchall()
        total = len(rows)
        resolved = sum(1 for row in rows if row["status"] == "Resolved")
        escalated = sum(1 for row in rows if row["escalated"] and row["status"] != "Resolved")
        output.append(
            {
                "key": key,
                "label": label,
                "total": total,
                "resolved": resolved,
                "escalated": escalated,
                "rate": round((resolved / total) * 100) if total else 0,
            }
        )
    return output


def calculate_ward_analytics(con):
    rows = con.execute(
        """
        SELECT ward, COUNT(*) AS total,
               SUM(CASE WHEN status='Resolved' THEN 1 ELSE 0 END) AS resolved,
               SUM(CASE WHEN escalated=1 AND status!='Resolved' THEN 1 ELSE 0 END) AS escalated
        FROM complaints GROUP BY ward ORDER BY total DESC, ward ASC
        """
    ).fetchall()
    return [
        {
            "ward": row["ward"],
            "total": row["total"],
            "resolved": row["resolved"],
            "escalated": row["escalated"],
            "rate": round((row["resolved"] / row["total"]) * 100) if row["total"] else 0,
        }
        for row in rows
    ]


def calculate_worker_stats(con):
    output = []
    for worker in WORKERS:
        tasks = con.execute(
            "SELECT * FROM complaints WHERE assigned_worker=? ORDER BY id DESC",
            (worker["id"],),
        ).fetchall()
        active_rows = [task for task in tasks if task["status"] in {"Assigned", "In Progress"}]
        awaiting_rows = [task for task in tasks if task["status"] == "Awaiting Admin Verification"]
        resolved_rows = [task for task in tasks if task["status"] == "Resolved"]
        completed = len(resolved_rows)
        current = active_rows[0] if active_rows else None

        review_row = con.execute(
            "SELECT AVG(rating) AS avg_rating, COUNT(*) AS ratings, SUM(CASE WHEN verdict='Not Satisfied' THEN 1 ELSE 0 END) AS reopens FROM resolution_reviews WHERE worker_id=? AND rating IS NOT NULL",
            (worker["id"],),
        ).fetchone()
        avg_rating = round(float(review_row["avg_rating"] or 0), 2)
        rating_count = int(review_row["ratings"] or 0)
        reopen_count = int(review_row["reopens"] or 0)

        sla_ok = 0
        for task in resolved_rows:
            deadline = parse_dt(task["sla_deadline"])
            resolved_at = parse_dt(task["resolved_at"])
            if deadline and resolved_at and resolved_at <= deadline:
                sla_ok += 1
        sla_score = (sla_ok / completed * 100) if completed else 0
        rating_score = (avg_rating / 5 * 100) if rating_count else (70 if tasks else 0)
        proof_values = [int(task["verification_score"] or 0) for task in resolved_rows if task["verification_score"] is not None]
        proof_score = (sum(proof_values) / len(proof_values)) if proof_values else (70 if resolved_rows else 0)
        reopen_score = max(0, 100 - ((reopen_count / max(1, completed)) * 100)) if completed else 0
        admin_quality_score = proof_score
        productivity_score = min(100, completed * 12.5)
        reliability_score = max(0, 100 - (sum(1 for task in active_rows if task["escalated"]) * 25)) if tasks else 0
        performance_score = round(
            sla_score * 0.25
            + rating_score * 0.20
            + admin_quality_score * 0.20
            + reopen_score * 0.15
            + productivity_score * 0.10
            + proof_score * 0.05
            + reliability_score * 0.05
        ) if tasks else 0
        if performance_score >= 90:
            performance_band = "Outstanding"
        elif performance_score >= 80:
            performance_band = "Excellent"
        elif performance_score >= 70:
            performance_band = "Good"
        elif performance_score >= 60:
            performance_band = "Needs Improvement"
        else:
            performance_band = "Performance Review" if tasks else "No Data"
        incentive_eligible = performance_score >= 90 and completed >= 3 and (avg_rating >= 4.2 if rating_count else False)

        output.append(
            {
                **worker,
                "total": len(tasks),
                "active": len(active_rows),
                "awaiting_review": len(awaiting_rows),
                "completed": completed,
                "escalated": sum(1 for task in active_rows if task["escalated"]),
                "high_priority": sum(1 for task in active_rows if task["priority"] >= 70),
                "rate": round((completed / len(tasks)) * 100) if tasks else 0,
                "busy": bool(current),
                "current_task_id": current["id"] if current else None,
                "current_task_title": current["title"] if current else None,
                "current_task_status": current["status"] if current else None,
                "avg_rating": avg_rating,
                "rating_count": rating_count,
                "reopen_count": reopen_count,
                "sla_score": round(sla_score),
                "proof_score": round(proof_score),
                "performance_score": performance_score,
                "performance_band": performance_band,
                "incentive_eligible": incentive_eligible,
            }
        )
    return output


def get_setting(con, key, default=""):
    row = con.execute("SELECT setting_value FROM system_settings WHERE setting_key=?", (key,)).fetchone()
    return row["setting_value"] if row and row["setting_value"] is not None else default


def table_exists(con, table_name):
    row = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return bool(row)


def set_setting(con, key, value):
    con.execute(
        "INSERT INTO system_settings(setting_key,setting_value) VALUES(?,?) "
        "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
        (key, value),
    )


def average_resolution_days(rows):
    values = []
    for row in rows:
        if row["status"] != "Resolved":
            continue
        start = parse_dt(row["created_at"])
        end = parse_dt(row["resolved_at"])
        if start and end and end >= start:
            values.append((end - start).total_seconds() / 86400)
    return round(sum(values) / len(values), 1) if values else 0.0


def complaint_trend(rows, days=14):
    today = datetime.now().date()
    output = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        count = 0
        for row in rows:
            created = parse_dt(row["created_at"])
            if created and created.date() == day:
                count += 1
        output.append({"label": day.strftime("%d %b"), "count": count})
    return output



def init_contractors_db():
    """Create and migrate the contractor management registry."""
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS contractors(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_code TEXT UNIQUE,
            company_name TEXT NOT NULL,
            contact_person TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            category TEXT NOT NULL,
            department TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            compliance_status TEXT DEFAULT 'Pending',
            license_no TEXT,
            gst_no TEXT,
            registration_date TEXT,
            license_expiry TEXT,
            insurance_expiry TEXT,
            performance_score INTEGER DEFAULT 70,
            total_contract_value REAL DEFAULT 0,
            amount_paid REAL DEFAULT 0,
            active_projects INTEGER DEFAULT 0,
            completed_projects INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS contractor_contracts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER NOT NULL,
            contract_no TEXT UNIQUE,
            title TEXT NOT NULL,
            department TEXT NOT NULL,
            category TEXT NOT NULL,
            ward TEXT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            contract_value REAL NOT NULL DEFAULT 0,
            amount_paid REAL DEFAULT 0,
            status TEXT DEFAULT 'Draft',
            progress INTEGER DEFAULT 0,
            milestone TEXT,
            asset_id INTEGER,
            complaint_id INTEGER,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(contractor_id) REFERENCES contractors(id) ON DELETE CASCADE,
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE SET NULL,
            FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE SET NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS contractor_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER NOT NULL,
            contract_id INTEGER,
            payment_ref TEXT UNIQUE,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            payment_type TEXT DEFAULT 'Milestone',
            status TEXT DEFAULT 'Pending',
            finance_transaction_id INTEGER,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(contractor_id) REFERENCES contractors(id) ON DELETE CASCADE,
            FOREIGN KEY(contract_id) REFERENCES contractor_contracts(id) ON DELETE SET NULL,
            FOREIGN KEY(finance_transaction_id) REFERENCES finance_transactions(id) ON DELETE SET NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS contractor_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER NOT NULL,
            contract_id INTEGER,
            rating INTEGER NOT NULL,
            quality INTEGER DEFAULT 0,
            timeliness INTEGER DEFAULT 0,
            compliance INTEGER DEFAULT 0,
            comment TEXT,
            reviewed_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(contractor_id) REFERENCES contractors(id) ON DELETE CASCADE,
            FOREIGN KEY(contract_id) REFERENCES contractor_contracts(id) ON DELETE SET NULL
        )
    """)
    for table, fields in {
        "contractors": [
            ("contractor_code","TEXT"),("company_name","TEXT"),("contact_person","TEXT"),("phone","TEXT"),
            ("email","TEXT"),("category","TEXT"),("department","TEXT"),("status","TEXT DEFAULT 'Pending'"),
            ("compliance_status","TEXT DEFAULT 'Pending'"),("license_no","TEXT"),("gst_no","TEXT"),
            ("registration_date","TEXT"),("license_expiry","TEXT"),("insurance_expiry","TEXT"),
            ("performance_score","INTEGER DEFAULT 70"),("total_contract_value","REAL DEFAULT 0"),
            ("amount_paid","REAL DEFAULT 0"),("active_projects","INTEGER DEFAULT 0"),
            ("completed_projects","INTEGER DEFAULT 0"),("notes","TEXT"),("created_at","TEXT"),("updated_at","TEXT")
        ],
        "contractor_contracts": [
            ("contract_no","TEXT"),("title","TEXT"),("department","TEXT"),("category","TEXT"),("ward","TEXT"),
            ("start_date","TEXT"),("end_date","TEXT"),("contract_value","REAL DEFAULT 0"),
            ("amount_paid","REAL DEFAULT 0"),("status","TEXT DEFAULT 'Draft'"),("progress","INTEGER DEFAULT 0"),
            ("milestone","TEXT"),("asset_id","INTEGER"),("complaint_id","INTEGER"),("notes","TEXT"),
            ("created_by","TEXT"),("created_at","TEXT"),("updated_at","TEXT")
        ],
        "contractor_payments": [
            ("payment_ref","TEXT"),("payment_date","TEXT"),("amount","REAL DEFAULT 0"),
            ("payment_type","TEXT DEFAULT 'Milestone'"),("status","TEXT DEFAULT 'Pending'"),
            ("finance_transaction_id","INTEGER"),("notes","TEXT"),("created_by","TEXT"),("created_at","TEXT")
        ],
    }.items():
        for name, definition in fields:
            ensure_column(con, table, name, definition)

    con.execute("CREATE INDEX IF NOT EXISTS idx_contractors_status ON contractors(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_contractors_department ON contractors(department)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_contracts_contractor ON contractor_contracts(contractor_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_contracts_status ON contractor_contracts(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_contractor_payments_contractor ON contractor_payments(contractor_id)")

    # Seed only when the registry is empty, giving the hackathon demo a realistic live screen.
    if con.execute("SELECT COUNT(*) AS c FROM contractors").fetchone()["c"] == 0:
        now = iso()
        demo = [
            ("CTR-001","Sahyadri InfraWorks","Amit Patil","9876543210","sahyadri@example.com","Roads","road","Active","Verified",
             "MRC/ROAD/2026/114","27ABCDE1234F1Z5","2026-04-10","2027-03-31","2027-01-15",92,18500000,6200000,2,6,
             "Preferred road contractor; strong quality and on-time record."),
            ("CTR-002","Godavari Water Solutions","Neha Shinde","9876501234","godavari@example.com","Water & Drainage","water","Active","Verified",
             "MRC/WTR/2026/072","27FGHIJ5678K2Z6","2026-05-18","2027-05-17","2027-02-20",87,9600000,2800000,1,4,
             "Specialist in pipeline rehabilitation and valves."),
            ("CTR-003","NagarSeva Electricals","Rohan Jadhav","9822001122","nse@example.com","Streetlights","electricity","Under Review","Expiring Soon",
             "MRC/ELC/2025/041","27KLMNO9012P3Z7","2025-09-01","2026-09-15","2026-09-15",74,4300000,3100000,1,8,
             "Insurance and license renewal should be completed before new award."),
        ]
        con.executemany("""
            INSERT INTO contractors(contractor_code,company_name,contact_person,phone,email,category,department,status,compliance_status,
            license_no,gst_no,registration_date,license_expiry,insurance_expiry,performance_score,total_contract_value,amount_paid,
            active_projects,completed_projects,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [r+(now,now) for r in demo])
    con.commit()
    con.close()


def contractor_money(value):
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        raise ValueError("Enter a valid non-negative amount.")


def contractor_int(value, default=0, low=0, high=100):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))


def contractor_recalculate(con, contractor_id):
    row = con.execute("""
        SELECT
          COALESCE(SUM(contract_value),0) AS total_value,
          COALESCE(SUM(amount_paid),0) AS contract_paid,
          SUM(CASE WHEN status IN ('Awarded','In Progress') THEN 1 ELSE 0 END) AS active_count,
          SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed_count
        FROM contractor_contracts WHERE contractor_id=?
    """, (contractor_id,)).fetchone()
    paid = con.execute(
        "SELECT COALESCE(SUM(amount),0) AS p FROM contractor_payments WHERE contractor_id=? AND status IN ('Approved','Paid')",
        (contractor_id,)
    ).fetchone()["p"]
    review = con.execute(
        "SELECT AVG(rating) AS r FROM contractor_reviews WHERE contractor_id=?",
        (contractor_id,)
    ).fetchone()["r"]
    score = round(float(review) * 20) if review is not None else None
    con.execute("""
        UPDATE contractor_contracts
        SET amount_paid=COALESCE((SELECT SUM(p.amount) FROM contractor_payments p
                                  WHERE p.contract_id=contractor_contracts.id
                                    AND p.status IN ('Approved','Paid')),0),
            updated_at=?
        WHERE contractor_id=?
    """, (iso(), contractor_id))
    con.execute("""
        UPDATE contractors SET total_contract_value=?, amount_paid=?, active_projects=?,
        completed_projects=?, performance_score=COALESCE(?,performance_score), updated_at=? WHERE id=?
    """, (row["total_value"], paid, int(row["active_count"] or 0), int(row["completed_count"] or 0),
          score, iso(), contractor_id))


def contractor_sync_compliance(con):
    """Keep compliance badges truthful from the stored expiry dates."""
    today=datetime.now().date()
    rows=con.execute("SELECT id,compliance_status,license_expiry,insurance_expiry FROM contractors").fetchall()
    for r in rows:
        dates=[]
        for key in ("license_expiry","insurance_expiry"):
            raw=r[key]
            if raw:
                try: dates.append(datetime.strptime(raw,"%Y-%m-%d").date())
                except ValueError: pass
        if not dates:
            continue
        nearest=min(dates)
        if nearest < today:
            new_status="Expired"
        elif nearest <= today+timedelta(days=30) and r["compliance_status"] not in ("Rejected",):
            new_status="Expiring Soon"
        elif r["compliance_status"] in ("Expired","Expiring Soon"):
            new_status="Verified"
        else:
            new_status=r["compliance_status"]
        if new_status != r["compliance_status"]:
            con.execute("UPDATE contractors SET compliance_status=?,updated_at=? WHERE id=?",(new_status,iso(),r["id"]))


@app.route("/admin/contractors")
@login_required
def admin_contractors():
    con = db()
    contractor_sync_compliance(con)
    con.commit()
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "all").strip()
    department = (request.args.get("department") or "all").strip()
    compliance = (request.args.get("compliance") or "all").strip()

    sql = "SELECT * FROM contractors WHERE 1=1"
    params = []
    if status != "all":
        sql += " AND status=?"; params.append(status)
    if department != "all":
        sql += " AND department=?"; params.append(department)
    if compliance != "all":
        sql += " AND compliance_status=?"; params.append(compliance)
    if q:
        sql += " AND (company_name LIKE ? OR contractor_code LIKE ? OR contact_person LIKE ? OR license_no LIKE ?)"
        like=f"%{q}%"; params += [like]*4
    contractors = con.execute(sql+" ORDER BY performance_score DESC, company_name", params).fetchall()

    contracts = con.execute("""
        SELECT c.*, r.company_name, r.contractor_code
        FROM contractor_contracts c JOIN contractors r ON r.id=c.contractor_id
        ORDER BY c.id DESC LIMIT 100
    """).fetchall()
    payments = con.execute("""
        SELECT p.*, r.company_name, c.contract_no
        FROM contractor_payments p JOIN contractors r ON r.id=p.contractor_id
        LEFT JOIN contractor_contracts c ON c.id=p.contract_id
        ORDER BY p.id DESC LIMIT 50
    """).fetchall()
    stats = {
        "total": con.execute("SELECT COUNT(*) c FROM contractors").fetchone()["c"],
        "active": con.execute("SELECT COUNT(*) c FROM contractors WHERE status='Active'").fetchone()["c"],
        "compliance": con.execute("SELECT COUNT(*) c FROM contractors WHERE compliance_status='Verified'").fetchone()["c"],
        "review": con.execute("SELECT COUNT(*) c FROM contractors WHERE compliance_status!='Verified'").fetchone()["c"],
        "value": con.execute("SELECT COALESCE(SUM(total_contract_value),0) v FROM contractors").fetchone()["v"],
        "paid": con.execute("SELECT COALESCE(SUM(amount_paid),0) v FROM contractors").fetchone()["v"],
    }
    assets = con.execute("SELECT id,asset_uid,name FROM assets ORDER BY name").fetchall()
    complaints = con.execute("SELECT id,title FROM complaints ORDER BY id DESC LIMIT 150").fetchall()
    context = admin_common_context(con)
    # Convert SQLite Row objects used by client-side JSON helpers into plain dictionaries.
    contractors = [dict(r) for r in contractors]
    contracts = [dict(r) for r in contracts]
    payments = [dict(r) for r in payments]
    assets = [dict(r) for r in assets]
    complaints = [dict(r) for r in complaints]
    con.close()
    return render_template("admin_contractors.html", contractors=contractors, contracts=contracts, payments=payments,
                           contractor_stats=stats, contractor_query=q, contractor_status=status,
                           contractor_department=department, contractor_compliance=compliance,
                           contractor_statuses=["Pending","Active","Under Review","Suspended","Blacklisted"],
                           contractor_compliances=["Pending","Verified","Expiring Soon","Expired","Rejected"],
                           contractor_contract_statuses=["Draft","Awarded","In Progress","On Hold","Completed","Terminated"],
                           contractor_payment_statuses=["Pending","Approved","Paid","Rejected"],
                           contractor_departments=FINANCE_DEPARTMENTS, contractor_assets=assets,
                           contractor_complaints=complaints, **context)


@app.route("/admin/contractors/save", methods=["POST"])
@login_required
def admin_contractor_save():
    data = {k:(request.form.get(k) or "").strip() for k in
            ["id","company_name","contact_person","phone","email","category","department","status",
             "compliance_status","license_no","gst_no","registration_date","license_expiry","insurance_expiry","notes"]}
    if not data["company_name"] or not data["contact_person"] or not valid_phone(data["phone"]) or not data["category"] or data["department"] not in DEPARTMENTS:
        flash("Company, contact person, valid phone, category and department are required.","danger")
        return redirect(url_for("admin_contractors"))
    if not valid_email(data["email"]):
        flash("Enter a valid contractor email.","danger"); return redirect(url_for("admin_contractors"))
    if data["status"] not in ["Pending","Active","Under Review","Suspended","Blacklisted"]:
        data["status"]="Pending"
    if data["compliance_status"] not in ["Pending","Verified","Expiring Soon","Expired","Rejected"]:
        data["compliance_status"]="Pending"
    con=db(); now=iso()
    try:
        if data["id"]:
            cid=int(data["id"])
            exists=con.execute("SELECT id FROM contractors WHERE id=?",(cid,)).fetchone()
            if not exists: raise ValueError("Contractor not found.")
            con.execute("""UPDATE contractors SET company_name=?,contact_person=?,phone=?,email=?,category=?,department=?,
                status=?,compliance_status=?,license_no=?,gst_no=?,registration_date=?,license_expiry=?,insurance_expiry=?,notes=?,updated_at=? WHERE id=?""",
                (data["company_name"],data["contact_person"],normalize_phone(data["phone"]),data["email"],data["category"],data["department"],
                 data["status"],data["compliance_status"],data["license_no"],data["gst_no"],data["registration_date"],data["license_expiry"],
                 data["insurance_expiry"],data["notes"],now,cid))
            flash("Contractor profile updated successfully.","success")
        else:
            code="CTR-"+datetime.now().strftime("%y%m%d%H%M%S")
            cur=con.execute("""INSERT INTO contractors(contractor_code,company_name,contact_person,phone,email,category,department,status,
                compliance_status,license_no,gst_no,registration_date,license_expiry,insurance_expiry,notes,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (code,data["company_name"],data["contact_person"],normalize_phone(data["phone"]),data["email"],data["category"],data["department"],
                 data["status"],data["compliance_status"],data["license_no"],data["gst_no"],data["registration_date"],data["license_expiry"],
                 data["insurance_expiry"],data["notes"],now,now))
            flash(f"Contractor {code} registered.","success")
        con.commit()
    except (ValueError, sqlite3.IntegrityError) as exc:
        con.rollback(); flash(f"Could not save contractor: {exc}","danger")
    finally: con.close()
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/delete/<int:cid>", methods=["POST"])
@login_required
def admin_contractor_delete(cid):
    con=db()
    active=con.execute("SELECT COUNT(*) c FROM contractor_contracts WHERE contractor_id=? AND status IN ('Awarded','In Progress')",(cid,)).fetchone()["c"]
    if active:
        con.close(); flash("Active contracts cannot be deleted. Suspend the contractor instead.","warning")
        return redirect(url_for("admin_contractors"))
    con.execute("DELETE FROM contractors WHERE id=?",(cid,))
    con.commit(); con.close()
    flash("Contractor removed from the registry.","success")
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/contract/save", methods=["POST"])
@login_required
def admin_contractor_contract_save():
    try:
        contractor_id=int(request.form.get("contractor_id") or 0)
        value=contractor_money(request.form.get("contract_value"))
        progress=contractor_int(request.form.get("progress"),0)
    except ValueError as exc:
        flash(str(exc),"danger"); return redirect(url_for("admin_contractors"))
    title=(request.form.get("title") or "").strip()
    dept=(request.form.get("department") or "").strip()
    start=(request.form.get("start_date") or "").strip()
    end=(request.form.get("end_date") or "").strip()
    category=(request.form.get("category") or "").strip()
    if not title or contractor_id <= 0 or dept not in DEPARTMENTS or not start or not end or not category:
        flash("Contract title, contractor, department, category and dates are required.","danger"); return redirect(url_for("admin_contractors"))
    try:
        datetime.strptime(start,"%Y-%m-%d"); datetime.strptime(end,"%Y-%m-%d")
        if datetime.strptime(end,"%Y-%m-%d") < datetime.strptime(start,"%Y-%m-%d"): raise ValueError("End date cannot be before start date.")
    except ValueError as exc:
        flash(str(exc),"danger"); return redirect(url_for("admin_contractors"))
    con=db(); now=iso()
    if not con.execute("SELECT 1 FROM contractors WHERE id=?",(contractor_id,)).fetchone():
        con.close(); flash("Contractor not found.","danger"); return redirect(url_for("admin_contractors"))
    cid=(request.form.get("id") or "").strip()
    status=(request.form.get("status") or "Draft").strip()
    if status not in ["Draft","Awarded","In Progress","On Hold","Completed","Terminated"]: status="Draft"
    try:
        if cid:
            con.execute("""UPDATE contractor_contracts SET contractor_id=?,title=?,department=?,category=?,ward=?,start_date=?,end_date=?,
                contract_value=?,status=?,progress=?,milestone=?,asset_id=?,complaint_id=?,notes=?,updated_at=? WHERE id=?""",
                (contractor_id,title,dept,category,(request.form.get("ward") or "").strip(),start,end,value,status,progress,
                 (request.form.get("milestone") or "").strip(),request.form.get("asset_id") or None,request.form.get("complaint_id") or None,
                 (request.form.get("notes") or "").strip(),now,int(cid)))
            flash("Contract updated.","success")
        else:
            no="CON-"+datetime.now().strftime("%y%m%d%H%M%S")
            con.execute("""INSERT INTO contractor_contracts(contractor_id,contract_no,title,department,category,ward,start_date,end_date,
                contract_value,status,progress,milestone,asset_id,complaint_id,notes,created_by,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor_id,no,title,dept,category,(request.form.get("ward") or "").strip(),start,end,value,status,progress,
                 (request.form.get("milestone") or "").strip(),request.form.get("asset_id") or None,request.form.get("complaint_id") or None,
                 (request.form.get("notes") or "").strip(),session.get("admin","admin"),now,now))
            flash(f"Contract {no} created.","success")
        contractor_recalculate(con,contractor_id)
        con.commit()
    except (ValueError, sqlite3.IntegrityError) as exc:
        con.rollback(); flash(f"Could not save contract: {exc}","danger")
    finally: con.close()
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/contract/status/<int:contract_id>", methods=["POST"])
@login_required
def admin_contractor_contract_status(contract_id):
    new=(request.form.get("status") or "").strip()
    if new not in ["Draft","Awarded","In Progress","On Hold","Completed","Terminated"]:
        flash("Invalid contract status.","danger"); return redirect(url_for("admin_contractors"))
    con=db(); row=con.execute("SELECT * FROM contractor_contracts WHERE id=?",(contract_id,)).fetchone()
    if not row:
        con.close(); flash("Contract not found.","warning"); return redirect(url_for("admin_contractors"))
    con.execute("UPDATE contractor_contracts SET status=?,progress=?,updated_at=? WHERE id=?",
                (new,100 if new=="Completed" else row["progress"],iso(),contract_id))
    contractor_recalculate(con,row["contractor_id"]); con.commit(); con.close()
    flash(f"{row['contract_no']} moved to {new}.","success")
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/payment/save", methods=["POST"])
@login_required
def admin_contractor_payment_save():
    try:
        contractor_id=int(request.form.get("contractor_id") or 0)
        contract_id=int(request.form.get("contract_id") or 0) if request.form.get("contract_id") else None
        amount=contractor_money(request.form.get("amount"))
    except ValueError as exc:
        flash(str(exc),"danger"); return redirect(url_for("admin_contractors"))
    date=(request.form.get("payment_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    try: datetime.strptime(date,"%Y-%m-%d")
    except ValueError:
        flash("Use a valid payment date.","danger"); return redirect(url_for("admin_contractors"))
    con=db()
    contractor=con.execute("SELECT * FROM contractors WHERE id=?",(contractor_id,)).fetchone()
    contract=con.execute("SELECT * FROM contractor_contracts WHERE id=? AND contractor_id=?",(contract_id,contractor_id)).fetchone() if contract_id else None
    if not contractor or (contract_id and not contract):
        con.close(); flash("Invalid contractor or contract.","danger"); return redirect(url_for("admin_contractors"))
    already=con.execute("SELECT COALESCE(SUM(amount),0) a FROM contractor_payments WHERE contract_id=? AND status IN ('Approved','Paid')",(contract_id,)).fetchone()["a"] if contract_id else 0
    if contract and already+amount > float(contract["contract_value"] or 0)+0.01:
        con.close(); flash("Payment blocked: it exceeds the contract value.","danger"); return redirect(url_for("admin_contractors"))
    status=(request.form.get("status") or "Pending").strip()
    if status not in ["Pending","Approved","Paid","Rejected"]: status="Pending"
    ref="PAY-"+datetime.now().strftime("%y%m%d%H%M%S%f")[:14]
    try:
        cur=con.execute("""INSERT INTO contractor_payments(contractor_id,contract_id,payment_ref,payment_date,amount,payment_type,status,notes,created_by,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (contractor_id,contract_id,ref,date,amount,(request.form.get("payment_type") or "Milestone").strip(),status,
                         (request.form.get("notes") or "").strip(),session.get("admin","admin"),iso()))
        # When approved/paid, also create a finance expense for a single source of truth.
        if status in ("Approved","Paid"):
            fin_ref=finance_next_ref(con,"Expense")
            dept=contract["department"] if contract else contractor["department"]
            cur2=con.execute("""INSERT INTO finance_transactions(txn_ref,txn_date,txn_type,department,category,description,amount,
                               status,created_by,created_at,updated_at,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (fin_ref,date,"Expense",dept,"Contractor Payments",
                              f"{ref} · {contractor['company_name']}",amount,status,session.get("admin","admin"),iso(),iso(),
                              "Auto-created from Contractor Management"))
            con.execute("UPDATE contractor_payments SET finance_transaction_id=? WHERE id=?",(cur2.lastrowid,cur.lastrowid))
            finance_audit(con,"Contractor Payment Linked","transaction",cur2.lastrowid,f"{ref} → {contractor['company_name']} ₹{amount:,.2f}")
        contractor_recalculate(con,contractor_id)
        con.commit(); flash(f"{ref} recorded and linked to Finance where applicable.","success")
    except (sqlite3.IntegrityError, ValueError) as exc:
        con.rollback(); flash(f"Could not record payment: {exc}","danger")
    finally: con.close()
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/payment/status/<int:payment_id>", methods=["POST"])
@login_required
def admin_contractor_payment_status(payment_id):
    new=(request.form.get("status") or "").strip()
    if new not in ["Pending","Approved","Paid","Rejected"]:
        flash("Invalid payment status.","danger"); return redirect(url_for("admin_contractors"))
    con=db()
    p=con.execute("SELECT * FROM contractor_payments WHERE id=?",(payment_id,)).fetchone()
    if not p:
        con.close(); flash("Payment not found.","warning"); return redirect(url_for("admin_contractors"))
    old=p["status"]
    if old==new:
        con.close(); return redirect(url_for("admin_contractors"))
    if new in ("Approved","Paid") and old not in ("Approved","Paid"):
        contract=con.execute("SELECT * FROM contractor_contracts WHERE id=?",(p["contract_id"],)).fetchone() if p["contract_id"] else None
        if contract:
            used=con.execute("SELECT COALESCE(SUM(amount),0) a FROM contractor_payments WHERE contract_id=? AND status IN ('Approved','Paid') AND id!=?",
                             (p["contract_id"],payment_id)).fetchone()["a"]
            if float(used)+float(p["amount"]) > float(contract["contract_value"])+0.01:
                con.close(); flash("Approval blocked: payment would exceed contract value.","danger"); return redirect(url_for("admin_contractors"))
        contractor=con.execute("SELECT * FROM contractors WHERE id=?",(p["contractor_id"],)).fetchone()
        if not p["finance_transaction_id"]:
            fin_ref=finance_next_ref(con,"Expense")
            dept=contract["department"] if contract else contractor["department"]
            cur=con.execute("""INSERT INTO finance_transactions(txn_ref,txn_date,txn_type,department,category,description,amount,status,created_by,created_at,updated_at,notes)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (fin_ref,p["payment_date"],"Expense",dept,"Contractor Payments",f"{p['payment_ref']} · {contractor['company_name']}",
                             p["amount"],new,session.get("admin","admin"),iso(),iso(),"Auto-created from Contractor Management"))
            con.execute("UPDATE contractor_payments SET finance_transaction_id=? WHERE id=?",(cur.lastrowid,payment_id))
            finance_audit(con,"Contractor Payment Approved","transaction",cur.lastrowid,f"{p['payment_ref']} → Finance")
    con.execute("UPDATE contractor_payments SET status=? WHERE id=?",(new,payment_id))
    contractor_recalculate(con,p["contractor_id"]); con.commit(); con.close()
    flash(f"{p['payment_ref']} marked {new}.","success")
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/review", methods=["POST"])
@login_required
def admin_contractor_review():
    try:
        contractor_id=int(request.form.get("contractor_id") or 0)
        rating=contractor_int(request.form.get("rating"),5,1,5)
        quality=contractor_int(request.form.get("quality"),rating,1,5)
        timeliness=contractor_int(request.form.get("timeliness"),rating,1,5)
        compliance=contractor_int(request.form.get("compliance"),rating,1,5)
    except ValueError:
        flash("Invalid review values.","danger"); return redirect(url_for("admin_contractors"))
    con=db()
    if not con.execute("SELECT 1 FROM contractors WHERE id=?",(contractor_id,)).fetchone():
        con.close(); flash("Contractor not found.","warning"); return redirect(url_for("admin_contractors"))
    con.execute("""INSERT INTO contractor_reviews(contractor_id,contract_id,rating,quality,timeliness,compliance,comment,reviewed_by,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (contractor_id,request.form.get("contract_id") or None,rating,quality,timeliness,compliance,
                 (request.form.get("comment") or "").strip(),session.get("admin","admin"),iso()))
    contractor_recalculate(con,contractor_id); con.commit(); con.close()
    flash("Performance review saved and score recalculated.","success")
    return redirect(url_for("admin_contractors"))


@app.route("/admin/contractors/export")
@login_required
def admin_contractors_export():
    con=db()
    rows=con.execute("SELECT * FROM contractors ORDER BY company_name").fetchall()
    con.close()
    out=io.StringIO(); writer=csv.writer(out)
    writer.writerow(["Code","Company","Contact","Phone","Email","Category","Department","Status","Compliance","License","GST",
                     "License Expiry","Insurance Expiry","Performance","Contract Value (INR)","Paid (INR)","Active Projects","Completed Projects"])
    for r in rows:
        writer.writerow([r["contractor_code"],r["company_name"],r["contact_person"],r["phone"],r["email"] or "",r["category"],r["department"],
                         r["status"],r["compliance_status"],r["license_no"] or "",r["gst_no"] or "",r["license_expiry"] or "",
                         r["insurance_expiry"] or "",r["performance_score"],r["total_contract_value"],r["amount_paid"],r["active_projects"],r["completed_projects"]])
    payload=io.BytesIO(out.getvalue().encode("utf-8-sig")); payload.seek(0)
    return send_file(payload,mimetype="text/csv",as_attachment=True,
                     download_name=f"CivicOS_Contractors_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")


@app.route("/api/admin/contractors/summary")
@login_required
def api_admin_contractors_summary():
    con=db()
    data={
        "total":con.execute("SELECT COUNT(*) c FROM contractors").fetchone()["c"],
        "active":con.execute("SELECT COUNT(*) c FROM contractors WHERE status='Active'").fetchone()["c"],
        "verified":con.execute("SELECT COUNT(*) c FROM contractors WHERE compliance_status='Verified'").fetchone()["c"],
        "at_risk":con.execute("SELECT COUNT(*) c FROM contractors WHERE compliance_status IN ('Expired','Expiring Soon') OR status IN ('Suspended','Blacklisted')").fetchone()["c"],
        "contract_value":con.execute("SELECT COALESCE(SUM(total_contract_value),0) v FROM contractors").fetchone()["v"],
        "paid":con.execute("SELECT COALESCE(SUM(amount_paid),0) v FROM contractors").fetchone()["v"],
    }
    con.close(); return jsonify(ok=True,**data)


def admin_common_context(con):
    complaints = con.execute(
        "SELECT * FROM complaints ORDER BY emergency DESC, escalated DESC, priority DESC, id DESC"
    ).fetchall()
    stats = get_stats(con)
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    worker_stats = calculate_worker_stats(con)
    feedback_rows = con.execute(
        "SELECT f.*, c.title AS complaint_title, c.ward AS ward FROM feedback f "
        "LEFT JOIN complaints c ON c.id=f.complaint_id ORDER BY f.id DESC"
    ).fetchall()
    announcements = con.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 8").fetchall()
    active = [row for row in complaints if row["status"] != "Resolved"]
    critical = [row for row in active if row["escalated"] or row["emergency"] or int(row["priority"] or 0) >= 70]
    critical = critical[:8]
    resolved_recent = [row for row in complaints if row["status"] == "Resolved"][:8]
    busy_workers = sum(1 for item in worker_stats if item["busy"])
    intelligence = intelligence_bundle(complaints, WORKERS)
    disaster_mode = get_setting(con, "disaster_mode", "0") == "1"
    reserve_guard_enabled = get_setting(con, "reserve_guard_enabled", "1") == "1"
    sweep_missions = con.execute(
        "SELECT * FROM sweep_missions ORDER BY id DESC LIMIT 8"
    ).fetchall()
    recovery_events = con.execute("SELECT * FROM recovery_events ORDER BY id DESC LIMIT 8").fetchall()
    return {
        "complaints": complaints,
        "stats": stats,
        "dept_perf": dept_perf,
        "ward_data": ward_data,
        "worker_stats": worker_stats,
        "feedback_rows": feedback_rows,
        "announcements": announcements,
        "critical": critical,
        "resolved_recent": resolved_recent,
        "avg_resolution_days": average_resolution_days(complaints),
        "complaint_trend": complaint_trend(complaints),
        "busy_workers": busy_workers,
        "area_name": get_setting(con, "civic_area_name", "Live location"),
        "map_default_lat": get_setting(con, "map_default_lat", "20.5937"),
        "map_default_lon": get_setting(con, "map_default_lon", "78.9629"),
        "intelligence": intelligence,
        "disaster_mode": disaster_mode,
        "reserve_guard_enabled": reserve_guard_enabled,
        "sweep_missions": sweep_missions,
        "recovery_events": recovery_events,
        "verification_pending": sum(1 for row in complaints if row["status"] == "Awaiting Admin Verification"),
        "accountability_pending": con.execute("SELECT COUNT(*) AS c FROM admin_accountability WHERE status IN ('Submitted','Under Review')").fetchone()["c"],
        "trust_pending": con.execute("SELECT COUNT(*) AS c FROM misinformation_reports WHERE status IN ('Submitted','Under Review')").fetchone()["c"]
            + con.execute("SELECT COUNT(*) AS c FROM complaint_trust_assessments WHERE risk_score>=60 AND reviewer_status IN ('Automated','Needs Review')").fetchone()["c"],
        "trust_summary": trust_summary(con),
    }


@app.context_processor
def inject_globals():
    return {
        "departments": DEPARTMENTS,
        "category_labels": CATEGORY_LABELS,
        "workers": WORKERS,
        "workers_by_dept": workers_by_department(),
        "status_order": STATUS_ORDER,
        "display_time": display_time,
        "sla_label": sla_label,
        "worker_label": worker_label,
        "t": t,
        "current_lang": get_language(),
        "supported_languages": SUPPORTED_LANGUAGES,
        "department_label": department_label,
        "category_label": category_label,
        "status_label": status_label,
        "timeline_step_label": timeline_step_label,
        "format_inr": lambda n: "₹{:,.0f}".format(float(n or 0)),
        "impact_score_for": impact_score,
        "cost_of_delay_for": cost_of_delay,
        "cascade_for": cascade_for,
        "asset_categories": ASSET_CATEGORIES,
        "asset_status_options": ASSET_STATUS_OPTIONS,
        "condition_for": calculate_condition_index,
        "maintenance_due_for": evaluate_maintenance_due,
        "trust_tone": trust_tone,
        "verdict_tone": verdict_tone,
        "trust_categories": TRUST_CATEGORIES,
        "from_json": lambda s: json.loads(s) if (s and isinstance(s, str)) else (s or {}),
    }


TRUST_CATEGORIES = {
    "scheme": "Government Scheme / Subsidy",
    "health": "Health / Screening",
    "water": "Water Quality",
    "transport": "Transport / Bus Service",
    "food": "Food Safety",
    "agriculture": "Agriculture / Crop Advisory",
    "civic": "Civic Service / Complaint",
    "other": "Other Public Information",
}
TRUST_CHANNELS = ("WhatsApp", "SMS", "Social Media", "Word of Mouth", "Platform Submission", "Other")
TRUST_VERDICTS = ("Unverified", "True", "False", "Misleading", "Official Update")


@app.route("/trust")
def trust_center():
    con = db()
    query = (request.args.get("q") or "").strip()
    result = trust_match_claim(con, query) if query else None
    bulletins = con.execute(
        "SELECT * FROM truth_bulletins WHERE public_visible=1 ORDER BY id DESC LIMIT 18"
    ).fetchall()
    summary = trust_summary(con)
    report_id = request.args.get("report_id", type=int)
    submitted = None
    if report_id:
        submitted = con.execute(
            "SELECT * FROM misinformation_reports WHERE id=?", (report_id,)
        ).fetchone()
    con.close()
    return render_template(
        "trust_center.html",
        query=query,
        result=result,
        bulletins=bulletins,
        trust_summary=summary,
        submitted=submitted,
        trust_categories=TRUST_CATEGORIES,
        trust_channels=TRUST_CHANNELS,
    )


@app.route("/trust/report", methods=["POST"])
def trust_report():
    claim = (request.form.get("claim_text") or "").strip()
    category = (request.form.get("category") or "other").strip()
    channel = (request.form.get("source_channel") or "Other").strip()
    source_url = (request.form.get("source_url") or "").strip()
    if len(claim) < 12:
        flash("Paste enough of the claim to let CivicOS compare it with official corrections.", "warning")
        return redirect(url_for("trust_center"))
    if len(claim) > 5000:
        flash("The claim is too long. Submit the specific message or allegation you want verified.", "warning")
        return redirect(url_for("trust_center"))
    if category not in TRUST_CATEGORIES:
        category = "other"
    if channel not in TRUST_CHANNELS:
        channel = "Other"
    if source_url and not re.match(r"^https?://", source_url, re.I):
        flash("Source link must start with http:// or https://.", "warning")
        return redirect(url_for("trust_center", q=claim))

    con = db()
    citizen = current_citizen()
    match = trust_match_claim(con, claim)
    confident_match = bool(match["matched"] and match["confidence"] >= 0.52)
    status = "Matched Official Record" if confident_match else "Submitted"
    verdict = match["verdict"] if confident_match else "Unverified"
    bulletin_id = match["bulletin"]["id"] if confident_match else None
    cur = con.execute(
        """INSERT INTO misinformation_reports(
            claim_text,category,source_channel,source_url,reporter_user_id,reporter_name,
            status,auto_match_id,auto_match_confidence,verdict,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            claim, category, channel, source_url or None,
            citizen["id"] if citizen else None,
            citizen["full_name"] if citizen else "Public reporter",
            status, bulletin_id, float(match["confidence"] or 0), verdict, iso(),
        ),
    )
    report_id = cur.lastrowid
    con.commit()
    con.close()
    if confident_match:
        flash("This report matches an existing CivicOS authority bulletin. The verified correction is shown below.", "success")
        return redirect(url_for("truth_detail", bulletin_id=bulletin_id, report_id=report_id))
    flash("Rumor submitted to the CivicOS Trust Queue. Until reviewed, it remains clearly labelled Unverified.", "success")
    return redirect(url_for("trust_center", q=claim, report_id=report_id))


@app.route("/truth/<int:bulletin_id>")
def truth_detail(bulletin_id):
    con = db()
    bulletin = con.execute(
        "SELECT * FROM truth_bulletins WHERE id=? AND public_visible=1", (bulletin_id,)
    ).fetchone()
    related = con.execute(
        "SELECT * FROM truth_bulletins WHERE public_visible=1 AND id!=? ORDER BY id DESC LIMIT 4",
        (bulletin_id,),
    ).fetchall()
    con.close()
    if not bulletin:
        flash("That public verification bulletin is not available.", "warning")
        return redirect(url_for("trust_center"))
    return render_template("truth_detail.html", bulletin=bulletin, related=related)


@app.route("/api/trust/check", methods=["POST"])
def api_trust_check():
    payload = request.get_json(silent=True) or request.form
    claim = (payload.get("claim") or payload.get("claim_text") or "").strip()
    if len(claim) < 8:
        return jsonify(ok=False, error="Provide a claim to verify."), 400
    con = db()
    result = trust_match_claim(con, claim)
    con.close()
    if not result["matched"]:
        return jsonify(
            ok=True, matched=False, verdict="Unverified",
            confidence=round(float(result["confidence"] or 0) * 100),
            message="No strong match was found in the published CivicOS authority bulletin registry. This does not make the claim true; it needs source verification.",
        )
    b = result["bulletin"]
    return jsonify(
        ok=True,
        matched=True,
        confidence=round(float(result["confidence"] or 0) * 100),
        verdict=b["verdict"],
        title=b["title"],
        fact=b["fact_text"],
        source=b["official_source"],
        bulletin_url=url_for("truth_detail", bulletin_id=b["id"]),
    )


@app.route("/admin/trust")
@login_required
def admin_trust_center():
    con = db()
    # Backfill explainable trust assessments for older demo/existing complaints.
    for complaint in con.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 120").fetchall():
        ensure_complaint_trust(con, complaint)
    con.commit()
    assessments = con.execute(
        """SELECT a.*, c.title, c.description, c.ward, c.village, c.category,
                  c.status AS complaint_status, c.citizen_name, c.created_at AS complaint_created_at
           FROM complaint_trust_assessments a
           JOIN complaints c ON c.id=a.complaint_id
           ORDER BY a.risk_score DESC, a.id DESC LIMIT 80"""
    ).fetchall()
    reports = con.execute(
        "SELECT * FROM misinformation_reports ORDER BY id DESC LIMIT 80"
    ).fetchall()
    bulletins = con.execute(
        "SELECT * FROM truth_bulletins ORDER BY id DESC LIMIT 60"
    ).fetchall()
    summary = trust_summary(con)
    context = admin_common_context(con)
    con.close()
    return render_template(
        "admin_trust_center.html",
        admin_active="trust",
        trust_summary=summary,
        assessments=assessments,
        misinformation_reports=reports,
        bulletins=bulletins,
        trust_categories=TRUST_CATEGORIES,
        trust_verdicts=TRUST_VERDICTS,
        **context,
    )


@app.route("/api/admin/trust/simulate-coordination", methods=["POST"])
@login_required
def api_admin_trust_simulate_coordination():
    """Run a zero-side-effect coordinated-fake demo in an in-memory database."""
    sim = sqlite3.connect(":memory:")
    sim.row_factory = sqlite3.Row
    sim.execute(
        """CREATE TABLE complaints(
            id INTEGER PRIMARY KEY,title TEXT,description TEXT,ward TEXT,category TEXT,
            citizen_user_id INTEGER,created_at TEXT,before_photo TEXT
        )"""
    )
    sample_title = "Food supplier is selling contaminated stock"
    sample_description = "Forwarded urgent message says the supplier is fraudulent and every food batch is contaminated. Everyone share urgently."
    stamp = iso()
    for idx, ward in enumerate(("Ward 2", "Ward 5", "Ward 8"), start=1):
        sim.execute(
            "INSERT INTO complaints(id,title,description,ward,category,citizen_user_id,created_at,before_photo) VALUES(?,?,?,?,?,?,?,NULL)",
            (idx, sample_title, sample_description, ward, "health", idx, stamp),
        )
    result = evaluate_submission(
        sim, sample_title, sample_description, 99, False, "Ward 11", "health"
    )
    sim.close()
    return jsonify(
        ok=True,
        scenario="Four near-identical accusatory submissions from different accounts and wards within the same window.",
        sample_claim=sample_description,
        score=result["score"],
        label=result["label"],
        auto_quarantine=bool(result["auto_quarantine"]),
        signals=result["signals"],
        policy="Quarantine from public amplification; preserve the case and continue authority/service review.",
    )


@app.route("/admin/trust/bulletin", methods=["POST"])
@login_required
def admin_trust_bulletin():
    title = (request.form.get("title") or "").strip()
    category = (request.form.get("category") or "civic").strip()
    claim_summary = (request.form.get("claim_summary") or "").strip()
    verdict = (request.form.get("verdict") or "Official Update").strip()
    fact_text = (request.form.get("fact_text") or "").strip()
    official_source = (request.form.get("official_source") or "").strip()
    evidence_url = (request.form.get("evidence_url") or "").strip()
    keywords = (request.form.get("keywords") or "").strip()
    if not title or not claim_summary or not fact_text:
        flash("Title, circulating claim, and official correction are required.", "danger")
        return redirect(url_for("admin_trust_center"))
    if category not in TRUST_CATEGORIES:
        category = "civic"
    if verdict not in TRUST_VERDICTS:
        verdict = "Official Update"
    if evidence_url and not re.match(r"^https?://", evidence_url, re.I):
        flash("Evidence/source URL must start with http:// or https://.", "warning")
        return redirect(url_for("admin_trust_center"))
    con = db()
    con.execute(
        """INSERT INTO truth_bulletins(
            title,category,claim_summary,verdict,fact_text,official_source,evidence_url,keywords,
            public_visible,is_demo,created_by,published_at
        ) VALUES(?,?,?,?,?,?,?,?,1,0,?,?)""",
        (title, category, claim_summary, verdict, fact_text, official_source or None,
         evidence_url or None, keywords, session.get("admin"), iso()),
    )
    if request.form.get("citizen_alert") == "1":
        con.execute(
            "INSERT INTO announcements(title,body,priority,created_by,created_at) VALUES(?,?,?,?,?)",
            ("Trust Bulletin · " + title, fact_text, "high" if verdict in ("False","Misleading") else "normal", session.get("admin"), iso()),
        )
    con.commit()
    con.close()
    flash("Official CivicOS verification bulletin published.", "success")
    return redirect(url_for("admin_trust_center"))


@app.route("/admin/trust/report/<int:report_id>", methods=["POST"])
@login_required
def admin_trust_report_review(report_id):
    status = (request.form.get("status") or "Reviewed").strip()
    verdict = (request.form.get("verdict") or "Unverified").strip()
    note = (request.form.get("review_note") or "").strip()
    if verdict not in TRUST_VERDICTS:
        verdict = "Unverified"
    if status not in ("Submitted", "Under Review", "Matched Official Record", "Reviewed", "Closed"):
        status = "Reviewed"
    con = db()
    report_row = con.execute("SELECT * FROM misinformation_reports WHERE id=?", (report_id,)).fetchone()
    if not report_row:
        con.close()
        flash("Rumor report not found.", "warning")
        return redirect(url_for("admin_trust_center"))
    bulletin_id = report_row["auto_match_id"]
    if request.form.get("publish_public") == "1":
        correction = (request.form.get("correction_text") or note).strip()
        source = (request.form.get("official_source") or "CivicOS Authority Review").strip()
        evidence_url = (request.form.get("evidence_url") or "").strip()
        if not correction:
            con.close()
            flash("Add an official correction before publishing this rumor as a public fact-check bulletin.", "danger")
            return redirect(url_for("admin_trust_center"))
        cur = con.execute(
            """INSERT INTO truth_bulletins(
                title,category,claim_summary,verdict,fact_text,official_source,evidence_url,keywords,
                public_visible,is_demo,created_by,published_at
            ) VALUES(?,?,?,?,?,?,?,?,1,0,?,?)""",
            (
                "Fact Check · " + report_row["claim_text"][:72],
                report_row["category"], report_row["claim_text"], verdict, correction,
                source, evidence_url or None, report_row["claim_text"][:300], session.get("admin"), iso(),
            ),
        )
        bulletin_id = cur.lastrowid
    con.execute(
        """UPDATE misinformation_reports
           SET status=?,verdict=?,review_note=?,reviewed_at=?,reviewed_by=?,auto_match_id=?
           WHERE id=?""",
        (status, verdict, note, iso(), session.get("admin"), bulletin_id, report_id),
    )
    con.commit()
    con.close()
    flash("Trust report review saved." + (" Public correction published." if request.form.get("publish_public") == "1" else ""), "success")
    return redirect(url_for("admin_trust_center"))


@app.route("/admin/trust/complaint/<int:cid>", methods=["POST"])
@login_required
def admin_trust_complaint_review(cid):
    decision = (request.form.get("decision") or "Needs Review").strip()
    note = (request.form.get("review_note") or "").strip()
    allowed = ("Automated", "Needs Review", "Cleared", "Coordinated Abuse", "False Submission")
    if decision not in allowed:
        decision = "Needs Review"
    con = db()
    complaint = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not complaint:
        con.close()
        flash("Complaint not found.", "warning")
        return redirect(url_for("admin_trust_center"))
    assessment = ensure_complaint_trust(con, complaint)
    visibility = "Quarantined" if decision in ("Coordinated Abuse", "False Submission") else "Normal"
    if decision == "Needs Review" and int(assessment["risk_score"] or 0) >= 80:
        visibility = "Quarantined"
    con.execute(
        """UPDATE complaint_trust_assessments
           SET reviewer_status=?,public_visibility=?,review_note=?,reviewed_at=?,reviewed_by=?,updated_at=?
           WHERE complaint_id=?""",
        (decision, visibility, note, iso(), session.get("admin"), iso(), cid),
    )
    add_timeline(
        con, cid, "Authority Trust Review",
        f"Information-integrity review: {decision}. Public visibility: {visibility}. " + (note or "No additional note."),
    )
    audit_action(con, "Trust Review Updated", f"Decision: {decision}; public visibility: {visibility}. {note}", cid)
    con.commit()
    con.close()
    flash("Complaint trust decision saved. Operational case history was preserved.", "success")
    return redirect(request.referrer or url_for("admin_trust_center"))


@app.route("/language/<lang>")
def change_language(lang):
    if lang in SUPPORTED_LANGUAGES:
        session["lang"] = lang
    return redirect(request.referrer or url_for("index"))


@app.route("/")
def index():
    sync_escalations()
    con = db()
    stats = get_stats(con)
    feedback_rows = con.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 4").fetchall()
    recent = con.execute(
        """SELECT c.* FROM complaints c
           LEFT JOIN complaint_trust_assessments a ON a.complaint_id=c.id
           WHERE COALESCE(a.public_visibility,'Normal')!='Quarantined'
           ORDER BY c.id DESC LIMIT 6"""
    ).fetchall()
    con.close()
    return render_template("index.html", stats=stats, feedback=feedback_rows, recent=recent)


@app.route("/report", methods=["GET", "POST"])
@citizen_required
def report():
    citizen = current_citizen()
    if not citizen or not citizen["email_verified"]:
        flash("Verify your Civic Account email with the 6-digit OTP before reporting a civic issue. SOS remains available without login.", "warning")
        return redirect(url_for("citizen_verify_otp"))
    asset_uid = (request.values.get("asset_uid") or "").strip()
    linked_asset = None
    if asset_uid:
        asset_con = db()
        linked_asset = asset_con.execute("SELECT * FROM assets WHERE asset_uid=?", (asset_uid,)).fetchone()
        asset_con.close()
        if not linked_asset and request.method == "GET":
            flash("The municipal asset reference was not found. You can still submit a normal civic issue.", "warning")
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        citizen_name = (request.form.get("citizen_name") or citizen["full_name"] or "").strip()
        phone = (request.form.get("phone") or "").strip()
        email = (citizen["email"] or request.form.get("email") or "").strip()
        village = (request.form.get("village") or citizen["village"] or "").strip()
        ward = (request.form.get("ward") or citizen["ward"] or "").strip()
        location = (request.form.get("location") or "").strip()
        selected = request.form.get("category", "auto")

        if not all([title, description, citizen_name, phone, village, ward]):
            flash("Please complete all required complaint and contact fields.", "danger")
            return render_template("report.html", citizen=citizen, linked_asset=linked_asset)
        if not valid_phone(phone):
            flash("Enter a valid phone number so your complaint ID can be recovered later.", "danger")
            return render_template("report.html", citizen=citizen, linked_asset=linked_asset)
        if not valid_email(email):
            flash("Enter a valid email address or leave the email field empty.", "danger")
            return render_template("report.html", citizen=citizen, linked_asset=linked_asset)

        try:
            category, department, required_skill, routing_reason = smart_route(title, description, selected)
        except ValueError:
            flash("Invalid complaint category.", "danger")
            return render_template("report.html", citizen=citizen, linked_asset=linked_asset)

        lat_raw = (request.form.get("latitude") or "").strip()
        lon_raw = (request.form.get("longitude") or "").strip()
        detected_address = (request.form.get("address") or "").strip()
        location_confirmed = (request.form.get("location_confirmed") or "false").lower()
        gps_used = bool(lat_raw or lon_raw or detected_address)

        if gps_used:
            try:
                latitude = float(lat_raw)
                longitude = float(lon_raw)
            except (TypeError, ValueError):
                flash(t("invalid_location_coordinates"), "danger")
                return render_template("report.html", citizen=citizen, linked_asset=linked_asset)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                flash(t("invalid_location_coordinates"), "danger")
                return render_template("report.html", citizen=citizen, linked_asset=linked_asset)
            if not detected_address:
                detected_address = f"GPS location: {latitude:.6f}, {longitude:.6f}"
            if location_confirmed != "true":
                flash(t("confirm_detected_address"), "warning")
                return render_template("report.html", citizen=citizen, linked_asset=linked_asset)
            address = detected_address
            if not location:
                location = address
        else:
            latitude = None
            longitude = None
            address = location

        if not location:
            flash(t("enter_location_or_gps"), "danger")
            return render_template("report.html", citizen=citizen, linked_asset=linked_asset)

        try:
            before_photo = save_file("before_photo")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("report.html", citizen=citizen, linked_asset=linked_asset)

        con = db()
        trust_assessment = evaluate_submission(
            con, title, description, citizen["id"], bool(before_photo), ward, category
        )
        duplicate = con.execute(
            "SELECT id FROM complaints WHERE village=? AND ward=? AND category=? AND status!='Resolved' LIMIT 1",
            (village, ward, category),
        ).fetchone()
        priority = service_priority(title, description, category, False, 0, bool(duplicate))
        hours = sla_hours(priority, False)
        created = datetime.now()
        worker = select_best_worker(con, department, required_skill, emergency=False, priority=priority)
        assigned_worker = worker["id"] if worker else None
        status = "Assigned" if worker else "Pending"
        assigned_at = iso(created) if worker else None

        con.execute(
            """INSERT INTO complaints(
                title,description,category,department,village,ward,location,address,
                latitude,longitude,status,priority,emergency,upvotes,before_photo,
                assigned_worker,citizen_name,phone,phone_key,email,required_skill,citizen_user_id,asset_id,
                created_at,updated_at,assigned_at,sla_deadline,sla_hours,routing_reason,duplicate_group
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                title,
                description,
                category,
                department,
                village,
                ward,
                location,
                address,
                latitude,
                longitude,
                status,
                priority,
                0,
                0,
                before_photo,
                assigned_worker,
                citizen_name,
                phone,
                normalize_phone(phone),
                email or None,
                required_skill,
                citizen["id"],
                linked_asset["id"] if linked_asset else None,
                iso(created),
                iso(created),
                assigned_at,
                iso(created + timedelta(hours=hours)),
                hours,
                routing_reason,
                title.lower()[:22] if duplicate else None,
            ),
        )
        cid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        store_complaint_trust(con, cid, trust_assessment)
        audit_action(con, "Complaint Reported", f"Verified civic account submitted complaint #{cid}.", cid)
        created_row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        created_impact = impact_score(created_row)
        con.execute(
            "UPDATE complaints SET impact_score=?, impact_label=? WHERE id=?",
            (created_impact["score"], created_impact["label"], cid),
        )

        add_timeline(
            con,
            cid,
            "Location Confirmed" if gps_used else "Location Added",
            f"Complaint location: {address}",
            created,
        )
        add_timeline(con, cid, "Reported", "Citizen submitted the issue with contact and location information.", created + timedelta(seconds=1))
        add_timeline(con, cid, "CivicOS Analysis", f"Detected category: {category_label(category)}. Required skill: {required_skill}.", created + timedelta(minutes=1))
        add_timeline(con, cid, "Smart Department Routing", routing_reason, created + timedelta(minutes=2))
        if worker:
            add_timeline(con, cid, "Worker Assigned", f"Automatically assigned to {worker_label(worker['id'])}. One-task policy verified.", created + timedelta(minutes=3))
        else:
            add_timeline(con, cid, "Queued for Worker", "Suitable field teams are busy or protected as emergency reserve. The complaint is safely queued by priority.", created + timedelta(minutes=3))
        add_timeline(con, cid, "SLA Assigned", f"Resolution SLA: {hours} hours based on service priority.", created + timedelta(minutes=4))
        if duplicate:
            add_timeline(con, cid, "Duplicate / Cluster Flag", "A similar open issue exists in the same ward and category.", created + timedelta(minutes=5))
        trust_note = (
            f"Information-integrity triage recorded a {trust_assessment['score']}/100 risk score ({trust_assessment['label']}). "
            + ("The case is temporarily withheld from public amplification pending authority review; operational handling continues."
               if trust_assessment.get("auto_quarantine") else "No automatic public hold was applied.")
        )
        add_timeline(con, cid, "Civic Trust Precheck", trust_note, created + timedelta(minutes=6))

        notification_message = f"Complaint #{cid} was registered and routed to {DEPARTMENTS[department]}."
        if worker:
            notification_message += f" {worker_label(worker['id'])} has been assigned."
        else:
            notification_message += " It is queued until a field team becomes available."
        create_notification(con, cid, "Complaint registered", notification_message, "success", created)
        con.commit()
        con.close()

        recent_ids = [int(value) for value in session.get("recent_complaint_ids", []) if str(value).isdigit()]
        session["recent_complaint_ids"] = ([cid] + [value for value in recent_ids if value != cid])[:8]
        send_optional_email(cid, f"CivicOS complaint #{cid} registered", notification_message)
        flash(f"Complaint submitted successfully. Your tracking ID is #{cid}. Save it, or recover it later using your name and phone number.", "success")
        return redirect(url_for("track", cid=cid))

    return render_template("report.html", citizen=citizen, linked_asset=linked_asset)


@app.route("/sos", methods=["GET", "POST"])
def sos():
    if request.method == "POST":
        emergency_type = (request.form.get("type") or "Women Safety").strip()
        emergency_map = {
            "Women Safety": ("safety", "police", "women safety"),
            "Medical Emergency": ("health", "health", "ambulance"),
            "Fire Emergency": ("fire", "fire", "fire rescue"),
        }
        if emergency_type not in emergency_map:
            emergency_type = "Women Safety"
        category, department, required_skill = emergency_map[emergency_type]
        village = (request.form.get("village") or "").strip()
        ward = (request.form.get("ward") or "").strip()
        location = (request.form.get("location") or "").strip()
        lat_raw = (request.form.get("latitude") or "").strip()
        lon_raw = (request.form.get("longitude") or "").strip()
        detected_address = (request.form.get("address") or "").strip()
        confirmed = (request.form.get("location_confirmed") or "false").lower()

        if confirmed != "true":
            flash(t("sos_confirm_location_first"), "warning")
            return render_template("emergency.html")
        try:
            latitude = float(lat_raw)
            longitude = float(lon_raw)
        except (TypeError, ValueError):
            flash(t("sos_invalid_coordinates"), "danger")
            return render_template("emergency.html")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            flash(t("sos_invalid_coordinates"), "danger")
            return render_template("emergency.html")
        address = detected_address or f"GPS location: {latitude:.6f}, {longitude:.6f}"
        location = location or address
        created = datetime.now()
        priority = 100
        hours = sla_hours(priority, True)

        con = db()
        worker = select_best_worker(con, department, required_skill, emergency=True, priority=priority)
        assigned_worker = worker["id"] if worker else None
        status = "Assigned" if worker else "Pending"
        routing_reason = f"Emergency SOS routed directly to {DEPARTMENTS[department]}."
        con.execute(
            """INSERT INTO complaints(
                title,description,category,department,village,ward,location,address,latitude,longitude,
                status,priority,emergency,assigned_worker,admin_note,required_skill,created_at,updated_at,
                assigned_at,sla_deadline,sla_hours,routing_reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"{emergency_type} Alert",
                "One-tap SOS generated by citizen.",
                category,
                department,
                village or "Emergency location",
                ward or "Emergency area",
                location,
                address,
                latitude,
                longitude,
                status,
                priority,
                1,
                assigned_worker,
                "Automatic emergency escalation sent. Citizen location confirmed.",
                required_skill,
                iso(created),
                iso(created),
                iso(created) if worker else None,
                iso(created + timedelta(hours=hours)),
                hours,
                routing_reason,
            ),
        )
        cid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        emergency_row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        emergency_impact = impact_score(emergency_row)
        con.execute(
            "UPDATE complaints SET impact_score=?, impact_label=? WHERE id=?",
            (emergency_impact["score"], emergency_impact["label"], cid),
        )
        add_timeline(con, cid, "Emergency Reported", f"{emergency_type} SOS received with confirmed GPS location.", created)
        add_timeline(con, cid, "Smart Department Routing", routing_reason, created + timedelta(seconds=20))
        if worker:
            add_timeline(con, cid, "Worker Assigned", f"Emergency assigned to {worker_label(worker['id'])}; the team had no other active task.", created + timedelta(seconds=40))
        else:
            add_timeline(con, cid, "Queued for Worker", "All matching teams are busy. Emergency remains at the top of the priority queue.", created + timedelta(seconds=40))
        add_timeline(con, cid, "SLA Assigned", f"Emergency SLA: {hours} hours.", created + timedelta(minutes=1))
        create_notification(con, cid, "Emergency alert registered", f"SOS #{cid} was routed to {DEPARTMENTS[department]}.", "danger", created)
        con.commit()
        con.close()

        recent_ids = [int(value) for value in session.get("recent_complaint_ids", []) if str(value).isdigit()]
        session["recent_complaint_ids"] = ([cid] + [value for value in recent_ids if value != cid])[:8]
        flash(f"Emergency alert #{cid} registered. Keep this screen open for live updates.", "success")
        return redirect(url_for("track", cid=cid))

    return render_template("emergency.html")


@app.route("/track")
def track():
    sync_escalations()
    cid_raw = (request.args.get("cid") or "").strip().lstrip("#")
    comp = None
    timeline = []
    feedback_rows = []
    notifications = []
    trust_assessment = None
    if cid_raw:
        if not cid_raw.isdigit():
            flash("Complaint ID must be a number.", "warning")
        else:
            cid = int(cid_raw)
            con = db()
            comp = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
            if comp:
                timeline = con.execute("SELECT * FROM timeline WHERE complaint_id=? ORDER BY id", (cid,)).fetchall()
                feedback_rows = con.execute("SELECT * FROM feedback WHERE complaint_id=? ORDER BY id DESC", (cid,)).fetchall()
                notifications = con.execute("SELECT * FROM notifications WHERE complaint_id=? ORDER BY id DESC LIMIT 8", (cid,)).fetchall()
                trust_assessment = con.execute("SELECT * FROM complaint_trust_assessments WHERE complaint_id=?", (cid,)).fetchone()
            else:
                flash(t("complaint_not_found"), "warning")
            con.close()
    return render_template("track.html", comp=comp, timeline=timeline, feedback=feedback_rows, notifications=notifications, trust_assessment=trust_assessment)


@app.route("/find-complaint", methods=["GET", "POST"])
def find_complaint():
    con = db()
    recent = []
    ids = [int(value) for value in session.get("recent_complaint_ids", []) if str(value).isdigit()]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        rows = con.execute(f"SELECT * FROM complaints WHERE id IN ({placeholders})", ids).fetchall()
        by_id = {row["id"]: row for row in rows}
        recent = [by_id[cid] for cid in ids if cid in by_id]

    results = []
    searched = False
    if request.method == "POST":
        searched = True
        name = (request.form.get("citizen_name") or "").strip()
        phone_key = normalize_phone(request.form.get("phone"))
        if not name or not valid_phone(phone_key):
            flash("Enter the same name and valid phone number used while reporting.", "warning")
        else:
            results = con.execute(
                """SELECT * FROM complaints
                   WHERE LOWER(TRIM(citizen_name))=LOWER(TRIM(?)) AND phone_key=?
                   ORDER BY id DESC LIMIT 20""",
                (name, phone_key),
            ).fetchall()
    con.close()
    return render_template("find_complaint.html", results=results, recent=recent, searched=searched)


@app.route("/notifications", methods=["GET", "POST"])
def notification_center():
    updates = []
    complaints = []
    searched = False
    if request.method == "POST":
        searched = True
        name = (request.form.get("citizen_name") or "").strip()
        phone_key = normalize_phone(request.form.get("phone"))
        if not name or not valid_phone(phone_key):
            flash("Enter the same name and valid phone number used while reporting.", "warning")
        else:
            con = db()
            complaints = con.execute(
                """SELECT * FROM complaints
                   WHERE LOWER(TRIM(citizen_name))=LOWER(TRIM(?)) AND phone_key=?
                   ORDER BY id DESC LIMIT 20""",
                (name, phone_key),
            ).fetchall()
            ids = [row["id"] for row in complaints]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                updates = con.execute(
                    f"SELECT * FROM notifications WHERE complaint_id IN ({placeholders}) ORDER BY id DESC LIMIT 80",
                    ids,
                ).fetchall()
                con.execute(f"UPDATE notifications SET is_read=1 WHERE complaint_id IN ({placeholders})", ids)
                con.commit()
            con.close()
    return render_template("notifications.html", updates=updates, complaints=complaints, searched=searched)


@app.route("/api/complaint/<int:cid>/state")
def complaint_state(cid):
    sync_escalations()
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    latest = con.execute("SELECT * FROM notifications WHERE complaint_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
    con.close()
    if not row:
        return jsonify({"error": "Complaint not found"}), 404
    return jsonify(
        id=row["id"],
        status=row["status"],
        statusLabel=status_label(row["status"]),
        worker=worker_label(row["assigned_worker"]),
        escalated=bool(row["escalated"]),
        sla=sla_label(row),
        updatedAt=row["updated_at"],
        latestNotification=(
            {"id": latest["id"], "title": latest["title"], "message": latest["message"], "createdAt": latest["created_at"]}
            if latest
            else None
        ),
    )


@app.route("/upvote/<int:cid>", methods=["POST"])
@verified_participation_required
def upvote(cid):
    user_id = session.get("citizen_id")
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not row:
        con.close()
        flash("Civic case not found.", "warning")
        return redirect(request.referrer or url_for("index"))
    try:
        con.execute("INSERT INTO complaint_votes(complaint_id,user_id,created_at) VALUES(?,?,?)", (cid, user_id, iso()))
    except sqlite3.IntegrityError:
        con.close()
        flash("You already supported this civic issue. Each verified account can upvote once.", "warning")
        return redirect(request.referrer or url_for("track", cid=cid))
    upvotes = int(row["upvotes"] or 0) + 1
    priority = service_priority(row["title"], row["description"], row["category"], bool(row["emergency"]), upvotes, bool(row["escalated"]))
    con.execute("UPDATE complaints SET upvotes=?, priority=?, updated_at=? WHERE id=?", (upvotes, priority, iso(), cid))
    add_timeline(con, cid, "Community Upvote", f"Verified civic support increased to {upvotes}.")
    audit_action(con, "Civic Issue Upvoted", f"Citizen supported complaint #{cid}.", cid)
    con.commit(); con.close()
    flash("Your support was recorded. You can upvote each issue only once.", "success")
    return redirect(request.referrer or url_for("track", cid=cid))


@app.route("/feedback/<int:cid>", methods=["POST"])
@citizen_required
def feedback(cid):
    con = db()
    exists = con.execute("SELECT id,status FROM complaints WHERE id=?", (cid,)).fetchone()
    if exists and exists["status"] == "Resolved":
        try:
            rating = max(1, min(int(request.form.get("rating") or 5), 5))
        except ValueError:
            rating = 5
        con.execute(
            "INSERT INTO feedback(complaint_id,name,rating,message,created_at) VALUES(?,?,?,?,?)",
            (cid, request.form.get("name") or "Citizen", rating, request.form.get("message") or "Satisfied with resolution.", iso()),
        )
        add_timeline(con, cid, "Citizen Feedback", "Citizen submitted feedback after tracking/resolution.")
        con.commit()
        flash(t("feedback_submitted"), "success")
    con.close()
    return redirect(url_for("track", cid=cid))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        con = db()
        user = con.execute("SELECT * FROM users WHERE username=? AND role='admin'", (username,)).fetchone()
        valid = False
        if user:
            stored = user["password"] or ""
            if stored.startswith(("scrypt:", "pbkdf2:")):
                valid = check_password_hash(stored, password)
            else:
                valid = stored == password
                if valid:
                    con.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(password), user["id"]))
                    con.commit()
        con.close()
        if valid:
            session.clear()
            session["admin"] = username
            flash(t("command_center_login_success"), "success")
            destination = request.args.get("next")
            return redirect(destination if destination and destination.startswith("/") else url_for("admin"))
        flash(t("invalid_login"), "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_command_center.html", admin_active="command", **context)


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_dashboard.html", admin_active="dashboard", **context)


@app.route("/admin/complaints")
@login_required
def admin_complaints():
    sync_escalations()
    status_filter = (request.args.get("status") or "all").strip()
    dept_filter = (request.args.get("department") or "all").strip()
    query = (request.args.get("q") or "").strip()
    con = db()
    context = admin_common_context(con)
    rows = context["complaints"]
    if status_filter != "all":
        rows = [row for row in rows if row["status"] == status_filter]
    if dept_filter != "all":
        rows = [row for row in rows if row["department"] == dept_filter]
    if query:
        q = query.lower()
        rows = [
            row for row in rows
            if q in str(row["id"]).lower()
            or q in (row["title"] or "").lower()
            or q in (row["ward"] or "").lower()
            or q in (row["village"] or "").lower()
            or q in (row["citizen_name"] or "").lower()
        ]
    con.close()
    return render_template(
        "admin_complaints.html",
        admin_active="complaints",
        filtered_complaints=rows,
        status_filter=status_filter,
        dept_filter=dept_filter,
        search_query=query,
        **context,
    )


@app.route("/admin/departments")
@login_required
def admin_departments():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_departments.html", admin_active="departments", **context)


@app.route("/admin/workers")
@login_required
def admin_workers():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_workers.html", admin_active="workers", **context)


@app.route("/admin/analytics")
@login_required
def admin_analytics():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_analytics.html", admin_active="analytics", **context)


@app.route("/admin/sla")
@login_required
def admin_sla():
    sync_escalations()
    now = datetime.now()
    con = db()
    context = admin_common_context(con)
    active = [row for row in context["complaints"] if row["status"] != "Resolved"]
    breached = [row for row in active if row["escalated"]]
    due_soon = []
    for row in active:
        deadline = parse_dt(row["sla_deadline"])
        if deadline and not row["escalated"] and now <= deadline <= now + timedelta(hours=12):
            due_soon.append(row)
    con.close()
    return render_template(
        "admin_sla.html", admin_active="sla", breached=breached, due_soon=due_soon, **context
    )


@app.route("/admin/feedback")
@login_required
def admin_feedback():
    con = db()
    context = admin_common_context(con)
    rating_counts = {}
    for row in context["feedback_rows"]:
        rating_counts[int(row["rating"] or 0)] = rating_counts.get(int(row["rating"] or 0), 0) + 1
    con.close()
    return render_template(
        "admin_feedback.html", admin_active="feedback", rating_counts=rating_counts, **context
    )


@app.route("/admin/reports")
@login_required
def admin_reports():
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_reports.html", admin_active="reports", **context)


@app.route("/admin/transparency")
@login_required
def admin_transparency():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_transparency.html", admin_active="transparency", **context)


@app.route("/admin/recovery")
@login_required
def admin_recovery():
    con = db()
    context = admin_common_context(con)
    # admin_common_context already provides recovery_events.  The recovery page
    # intentionally loads a larger (12-row) list, so replace the shared value
    # instead of passing the same keyword twice to render_template().
    events = con.execute("SELECT * FROM recovery_events ORDER BY id DESC LIMIT 12").fetchall()
    context["recovery_events"] = events
    counts = {
        "complaints": con.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"],
        "active_complaints": con.execute("SELECT COUNT(*) c FROM complaints WHERE status!='Resolved'").fetchone()["c"],
        "inventory": con.execute("SELECT COUNT(*) c FROM inventory_items").fetchone()["c"] if table_exists(con, "inventory_items") else 0,
    }
    con.close()
    meta = _load_recovery_meta()
    primary_ok = _integrity_ok(DB)
    backup_ok = _integrity_ok(RECOVERY_DB)
    return render_template(
        "admin_recovery.html",
        admin_active="recovery",
        recovery_meta=meta,
        primary_ok=primary_ok,
        backup_ok=backup_ok,
        primary_size=os.path.getsize(DB) if os.path.exists(DB) else 0,
        backup_size=os.path.getsize(RECOVERY_DB) if os.path.exists(RECOVERY_DB) else 0,
        backup_time=datetime.fromtimestamp(os.path.getmtime(RECOVERY_DB)).strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(RECOVERY_DB) else "—",
        record_counts=counts,
        **context,
    )


@app.route("/api/admin/recovery/status")
@login_required
def api_admin_recovery_status():
    # Calling db() here is deliberate: this endpoint is also a live self-heal
    # probe, so a damaged primary store is recovered before status is returned.
    con = db()
    complaint_count = con.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
    inventory_count = con.execute("SELECT COUNT(*) c FROM inventory_items").fetchone()["c"] if table_exists(con, "inventory_items") else 0
    last_event = con.execute("SELECT * FROM recovery_events ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    return jsonify(
        primary="HEALTHY" if _integrity_ok(DB) else "DEGRADED",
        recovery_snapshot="READY" if _integrity_ok(RECOVERY_DB) else "UNAVAILABLE",
        last_snapshot=datetime.fromtimestamp(os.path.getmtime(RECOVERY_DB)).strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(RECOVERY_DB) else None,
        complaints=complaint_count,
        inventory=inventory_count,
        last_incident=(dict(last_event) if last_event else None),
    )


@app.route("/admin/recovery/snapshot", methods=["POST"])
@login_required
def admin_recovery_snapshot():
    con = db()
    ok = create_recovery_snapshot(con)
    con.close()
    flash("Recovery snapshot updated successfully." if ok else "Could not create a recovery snapshot.", "success" if ok else "danger")
    return redirect(url_for("admin_recovery"))


@app.route("/admin/recovery/simulate-blackout", methods=["POST"])
@login_required
def admin_recovery_simulate_blackout():
    """Hackathon demo: corrupt the live DB, detect it, then auto-restore it."""
    incident_id = "BLK-" + uuid.uuid4().hex[:10].upper()
    con = db()
    create_recovery_snapshot(con)
    complaints_before = con.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
    active_before = con.execute("SELECT COUNT(*) c FROM complaints WHERE status!='Resolved'").fetchone()["c"]
    inventory_before = con.execute("SELECT COUNT(*) c FROM inventory_items").fetchone()["c"] if table_exists(con, "inventory_items") else 0
    records_before = complaints_before + inventory_before
    con.close()

    started = iso()
    meta = _load_recovery_meta()
    meta["active_incident"] = {
        "incident_id": incident_id,
        "started_at": started,
        "started_epoch": time.time(),
        "status": "Corrupted → detecting → restoring",
        "trigger": "Hackathon live blackout simulator",
        "records_before": records_before,
        "complaints_before": complaints_before,
        "active_complaints_before": active_before,
        "inventory_before": inventory_before,
    }
    _save_recovery_meta(meta)

    # Preserve the damaged artifact for the evidence trail, then make the real
    # primary store unreadable. The next db() call must self-heal from the backup.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    incident_copy = os.path.join(RECOVERY_CORRUPT_DIR, f"{incident_id}_{stamp}_before_recovery.db")
    try:
        shutil.copy2(DB, incident_copy)
        with open(DB, "wb") as handle:
            handle.write(b"CIVICOS_BLACKOUT_CORRUPTED_PRIMARY_STORE")
    except OSError as exc:
        flash(f"Blackout simulation could not corrupt the primary store: {exc}", "danger")
        return redirect(url_for("admin_recovery"))

    detected_at = iso()
    # This is the real recovery boundary: db() validates the damaged primary,
    # restores the independent snapshot, and only then lets the application continue.
    recovered_con = db()
    integrity = recovered_con.execute("PRAGMA integrity_check").fetchone()[0]
    recovered_complaints = recovered_con.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
    recovered_active = recovered_con.execute("SELECT COUNT(*) c FROM complaints WHERE status!='Resolved'").fetchone()["c"]
    recovered_inventory = recovered_con.execute("SELECT COUNT(*) c FROM inventory_items").fetchone()["c"] if table_exists(recovered_con, "inventory_items") else 0
    duration_ms = round((time.time() - meta["active_incident"]["started_epoch"]) * 1000, 1)
    recovered_con.execute(
        """INSERT INTO recovery_events(
            incident_id,started_at,detected_at,restored_at,duration_ms,trigger,
            records_before,complaints_before,inventory_before,integrity_after,status,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (incident_id, started, detected_at, iso(), duration_ms,
         "Hackathon live blackout simulator", records_before, complaints_before,
         inventory_before, str(integrity), "Recovered",
         f"Primary store intentionally corrupted; quarantined artifact: {os.path.relpath(incident_copy, BASE_DIR)}"),
    )
    recovered_con.commit()
    recovered_con.close()

    meta = _load_recovery_meta()
    active = meta.get("active_incident") or {}
    active.update({
        "incident_id": incident_id,
        "detected_at": detected_at,
        "restored_at": iso(),
        "duration_ms": duration_ms,
        "status": "Recovered",
        "integrity_after": str(integrity),
        "records_after": recovered_complaints + recovered_inventory,
        "active_complaints_after": recovered_active,
        "quarantined_file": os.path.relpath(incident_copy, BASE_DIR),
    })
    active.pop("started_epoch", None)
    meta["incidents"] = ([active] + meta.get("incidents", []))[:20]
    meta["active_incident"] = None
    _save_recovery_meta(meta)

    flash(
        f"BLACKOUT RECOVERED · {incident_id} · primary store restored and integrity_check={integrity}. "
        f"{recovered_complaints} complaints and {recovered_inventory} inventory records verified.",
        "success",
    )
    return redirect(url_for("admin_recovery"))


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    con = db()
    if request.method == "POST":
        area_name = (request.form.get("area_name") or "Live location").strip()[:80]
        lat = (request.form.get("map_default_lat") or "20.5937").strip()
        lon = (request.form.get("map_default_lon") or "78.9629").strip()
        try:
            lat_num, lon_num = float(lat), float(lon)
            if not (-90 <= lat_num <= 90 and -180 <= lon_num <= 180):
                raise ValueError
        except ValueError:
            con.close()
            flash("Enter valid default map latitude and longitude.", "danger")
            return redirect(url_for("admin_settings"))
        set_setting(con, "civic_area_name", area_name)
        set_setting(con, "map_default_lat", str(lat_num))
        set_setting(con, "map_default_lon", str(lon_num))
        set_setting(con, "reserve_guard_enabled", "1" if request.form.get("reserve_guard_enabled") == "1" else "0")
        con.commit()
        flash("Command Center settings updated.", "success")
    context = admin_common_context(con)
    email_deliveries = con.execute(
        "SELECT * FROM email_deliveries ORDER BY id DESC LIMIT 12"
    ).fetchall()
    con.close()
    return render_template(
        "admin_settings.html",
        admin_active="settings",
        email_config=email_configuration_status(),
        email_deliveries=email_deliveries,
        **context,
    )


@app.route("/admin/announcements", methods=["GET", "POST"])
@login_required
def admin_announcements():
    con = db()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        body = (request.form.get("body") or "").strip()
        priority = (request.form.get("priority") or "normal").strip()
        if not title or not body:
            flash("Announcement title and message are required.", "warning")
        else:
            if priority not in {"normal", "important", "critical"}:
                priority = "normal"
            con.execute(
                "INSERT INTO announcements(title,body,priority,created_by,created_at) VALUES(?,?,?,?,?)",
                (title[:120], body[:1200], priority, session.get("admin"), iso()),
            )
            con.commit()
            flash("Announcement published in the Command Center.", "success")
    context = admin_common_context(con)
    con.close()
    return render_template("admin_announcements.html", admin_active="announcements", **context)


@app.route("/admin/alerts", methods=["GET", "POST"])
@login_required
def admin_alerts():
    con = db()
    if request.method == "POST":
        title = (request.form.get("title") or "CivicOS authority alert").strip()[:120]
        message = (request.form.get("message") or "").strip()[:1000]
        scope = (request.form.get("scope") or "active").strip()
        scope_value = (request.form.get("scope_value") or "").strip()
        if not message:
            flash("Alert message is required.", "warning")
        else:
            sql = "SELECT id FROM complaints WHERE status!='Resolved'"
            params = []
            if scope == "department" and scope_value in DEPARTMENTS:
                sql += " AND department=?"
                params.append(scope_value)
            elif scope == "ward" and scope_value:
                sql += " AND ward=?"
                params.append(scope_value)
            targets = con.execute(sql, params).fetchall()
            for target in targets:
                create_notification(con, target["id"], title, message, "warning")
                add_timeline(con, target["id"], "Authority Alert", message)
            con.commit()
            flash(f"Alert sent to {len(targets)} active complaint record(s).", "success")
    context = admin_common_context(con)
    con.close()
    return render_template("admin_alerts.html", admin_active="alerts", **context)


@app.route("/admin/emergency")
@login_required
def admin_emergency():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    emergency_rows = [row for row in context["complaints"] if row["emergency"]]
    con.close()
    return render_template(
        "admin_emergency.html", admin_active="emergency", emergency_rows=emergency_rows, **context
    )


@app.route("/admin/intelligence")
@login_required
def admin_intelligence():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_intelligence.html", admin_active="intelligence", **context)


@app.route("/admin/intelligence/brief")
@login_required
def admin_intelligence_brief():
    """Printable decision brief assembled from deterministic CivicOS engines."""
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    con.close()
    return render_template("admin_intelligence_brief.html", admin_active="intelligence", **context)


@app.route("/admin/intelligence/optimizer", methods=["GET", "POST"])
@login_required
def admin_optimizer():
    sync_escalations()
    con = db()
    context = admin_common_context(con)
    budget = request.form.get("budget", request.args.get("budget", "1000000"))
    workers_limit = request.form.get("workers", request.args.get("workers", "20"))
    vehicles = request.form.get("vehicles", request.args.get("vehicles", "3"))
    days = request.form.get("days", request.args.get("days", "14"))
    try:
        budget_i = min(100000000, max(10000, int(float(budget))))
        workers_i = min(500, max(1, int(workers_limit)))
        vehicles_i = min(100, max(1, int(vehicles)))
        days_i = min(90, max(1, int(days)))
    except (ValueError, TypeError):
        budget_i, workers_i, vehicles_i, days_i = 1000000, 20, 3, 14
        flash("Invalid optimizer input was reset to safe demo defaults.", "warning")
    plan = optimize_public_value(context["complaints"], budget_i, workers_i, vehicles_i, days_i)
    con.close()
    return render_template("admin_optimizer.html", admin_active="intelligence", plan=plan, **context)


@app.route("/admin/intelligence/sweeps", methods=["GET", "POST"])
@login_required
def admin_sweeps():
    sync_escalations()
    con = db()
    if request.method == "POST":
        title = (request.form.get("title") or "Cross-Department Sweep").strip()[:140]
        description = (request.form.get("description") or "Coordinated CivicOS field sweep.").strip()[:1200]
        ids = []
        for token in (request.form.get("complaint_ids") or "").split(","):
            token = token.strip()
            if token.isdigit():
                ids.append(int(token))
        ids = list(dict.fromkeys(ids))[:20]
        if len(ids) < 2:
            flash("A sweep needs at least two connected complaints.", "warning")
        else:
            rows = con.execute(
                f"SELECT id,department FROM complaints WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
            departments = sorted({row["department"] for row in rows})
            if len(rows) < 2:
                flash("The selected complaints no longer exist.", "danger")
            else:
                cur = con.execute(
                    "INSERT INTO sweep_missions(title,description,departments,status,created_by,created_at) VALUES(?,?,?,?,?,?)",
                    (title, description, ",".join(departments), "Planned", session.get("admin"), iso()),
                )
                mission_id = cur.lastrowid
                for row in rows:
                    con.execute("INSERT OR IGNORE INTO sweep_items(mission_id,complaint_id) VALUES(?,?)", (mission_id, row["id"]))
                    add_timeline(con, row["id"], "Cross-Department Sweep", f"Included in coordinated sweep mission #{mission_id}: {title}")
                con.commit()
                flash(f"Sweep mission #{mission_id} created across {len(departments)} department(s).", "success")
                return redirect(url_for("admin_sweeps"))
    context = admin_common_context(con)
    missions = con.execute(
        """SELECT sm.*, COUNT(si.id) AS item_count FROM sweep_missions sm
           LEFT JOIN sweep_items si ON si.mission_id=sm.id
           GROUP BY sm.id ORDER BY sm.id DESC"""
    ).fetchall()
    con.close()
    return render_template("admin_sweeps.html", admin_active="intelligence", missions=missions, **context)


@app.route("/admin/intelligence/sweeps/<int:mission_id>/status", methods=["POST"])
@login_required
def admin_sweep_status(mission_id):
    status = (request.form.get("status") or "Planned").strip()
    if status not in {"Planned", "Active", "Completed"}:
        flash("Invalid sweep status.", "danger")
        return redirect(url_for("admin_sweeps"))
    con = db()
    con.execute("UPDATE sweep_missions SET status=? WHERE id=?", (status, mission_id))
    ids = con.execute("SELECT complaint_id FROM sweep_items WHERE mission_id=?", (mission_id,)).fetchall()
    for item in ids:
        add_timeline(con, item["complaint_id"], "Sweep Mission Update", f"Cross-department sweep #{mission_id} changed to {status}.")
    con.commit()
    con.close()
    flash(f"Sweep mission #{mission_id} is now {status}.", "success")
    return redirect(url_for("admin_sweeps"))


@app.route("/admin/disaster-mode", methods=["POST"])
@login_required
def toggle_disaster_mode():
    con = db()
    enabled = get_setting(con, "disaster_mode", "0") != "1"
    set_setting(con, "disaster_mode", "1" if enabled else "0")
    con.commit()
    con.close()
    flash(
        "Disaster Operations Mode enabled: emergency capacity is protected and non-critical auto-assignment is conservative."
        if enabled else "Disaster Operations Mode disabled: normal assignment policy restored.",
        "warning" if enabled else "success",
    )
    return redirect(request.referrer or url_for("admin"))


@app.route("/api/intelligence/complaint/<int:cid>")
def complaint_intelligence_api(cid):
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not row:
        con.close()
        return jsonify(ok=False, error="Complaint not found"), 404
    rows = con.execute("SELECT * FROM complaints").fetchall()
    related = [r for r in rows if r["id"] != cid and (r["ward"] or "").strip().lower() == (row["ward"] or "").strip().lower()]
    con.close()
    return jsonify(
        ok=True,
        impact=impact_score(row),
        delay7=cost_of_delay(row, 7),
        cascade=cascade_for(row, 7),
        related_count=len(related),
    )


@app.route("/admin/export")
@login_required
def admin_export():
    con = db()
    rows = con.execute("SELECT * FROM complaints ORDER BY id DESC").fetchall()
    con.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Complaint ID", "Title", "Category", "Department", "Ward", "Village", "Status",
        "Priority", "Emergency", "SLA Deadline", "Escalated", "Assigned Worker", "Citizen",
        "Phone", "Created At", "Resolved At"
    ])
    for row in rows:
        writer.writerow([
            row["id"], row["title"], row["category"], row["department"], row["ward"], row["village"],
            row["status"], row["priority"], row["emergency"], row["sla_deadline"], row["escalated"],
            row["assigned_worker"], row["citizen_name"], row["phone"], row["created_at"], row["resolved_at"]
        ])
    payload = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    payload.seek(0)
    return send_file(
        payload,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"CivicOS_Complaints_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
    )


@app.route("/admin/update/<int:cid>", methods=["POST"])
@login_required
def update_complaint(cid):
    status = request.form.get("status") or "Pending"
    worker_id = (request.form.get("assigned_worker") or "").strip() or None
    note = (request.form.get("admin_note") or "").strip()
    if status not in STATUS_ORDER:
        flash("Invalid complaint status.", "danger")
        return redirect(request.referrer or url_for("admin"))
    try:
        after_photo = save_file("after_photo")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(request.referrer or url_for("admin"))

    con = db()
    old = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not old:
        con.close()
        flash(t("complaint_not_found"), "danger")
        return redirect(url_for("admin"))

    selected_worker = get_worker(worker_id) if worker_id else None
    if worker_id and (not selected_worker or selected_worker["department"] != old["department"]):
        con.close()
        flash("That field team does not belong to the complaint department.", "danger")
        return redirect(request.referrer or url_for("admin"))

    if worker_id and status != "Resolved":
        busy_task = worker_active_task(con, worker_id, exclude_complaint_id=cid)
        if busy_task:
            con.close()
            flash(f"{worker_label(worker_id)} is already handling complaint #{busy_task['id']}. A team can take only one active task at a time.", "warning")
            return redirect(request.referrer or url_for("admin"))

    override_reserve = request.form.get("override_reserve") == "1"
    if (
        worker_id
        and worker_id != (old["assigned_worker"] or "")
        and status != "Resolved"
        and not override_reserve
        and reserve_assignment_blocked(
            con, old["department"], worker_id, bool(old["emergency"]), old["priority"], exclude_complaint_id=cid
        )
    ):
        con.close()
        flash(
            "Reserve Capacity Guard blocked this routine assignment because it would consume the department's final protected response team. Use the authority override only when operationally justified.",
            "warning",
        )
        return redirect(request.referrer or url_for("admin"))

    if worker_id and status == "Pending":
        status = "Assigned"
    if not worker_id and status in {"Assigned", "In Progress"}:
        status = "Pending"
    if status == "In Progress" and not worker_id:
        con.close()
        flash("Assign a field team before starting work.", "warning")
        return redirect(request.referrer or url_for("admin"))

    if status == "Resolved" and not (after_photo or old["after_photo"]):
        con.close()
        flash("Upload after-work photo evidence before marking a complaint Resolved. CivicOS requires proof of resolution.", "warning")
        return redirect(request.referrer or url_for("admin"))

    resolved_at = iso() if status == "Resolved" and old["status"] != "Resolved" else old["resolved_at"]
    if status != "Resolved" and old["status"] == "Resolved":
        resolved_at = None
    assigned_at = old["assigned_at"]
    if worker_id and old["assigned_worker"] != worker_id:
        assigned_at = iso()
    if not worker_id:
        assigned_at = None
    escalated = 0 if status == "Resolved" else old["escalated"]

    try:
        if after_photo:
            con.execute(
                """UPDATE complaints SET status=?,assigned_worker=?,admin_note=?,updated_at=?,assigned_at=?,resolved_at=?,escalated=?,after_photo=? WHERE id=?""",
                (status, worker_id, note, iso(), assigned_at, resolved_at, escalated, after_photo, cid),
            )
        else:
            con.execute(
                """UPDATE complaints SET status=?,assigned_worker=?,admin_note=?,updated_at=?,assigned_at=?,resolved_at=?,escalated=? WHERE id=?""",
                (status, worker_id, note, iso(), assigned_at, resolved_at, escalated, cid),
            )
    except sqlite3.IntegrityError:
        con.rollback()
        con.close()
        flash("Assignment blocked: the selected field team already has an active task.", "warning")
        return redirect(request.referrer or url_for("admin"))

    changes = []
    if old["status"] != status:
        add_timeline(con, cid, status, note or f"Status updated to {status}.")
        changes.append(f"Status changed to {status}.")
    if old["assigned_worker"] != worker_id:
        if worker_id:
            add_timeline(con, cid, "Worker Assigned", f"Assigned to {worker_label(worker_id)} under the one-task policy.")
            changes.append(f"Field team assigned: {worker_label(worker_id)}.")
        else:
            add_timeline(con, cid, "Queued for Worker", "The complaint was returned to the worker queue.")
            changes.append("Complaint returned to the field-team queue.")
    if after_photo:
        add_timeline(con, cid, "After Photo Uploaded", "Completion evidence was uploaded.")
        changes.append("After-work proof was uploaded.")
    if note and note != (old["admin_note"] or ""):
        changes.append(f"Authority note: {note}")

    if changes:
        kind = "success" if status == "Resolved" else ("warning" if escalated else "info")
        create_notification(con, cid, "Complaint update", " ".join(changes), kind)

    if status == "Resolved":
        if old["status"] != "Resolved":
            con.execute(
                "UPDATE complaints SET admin_verified_at=?, citizen_resolution='Pending', reopen_requested=0, resolution_cycle=COALESCE(resolution_cycle,0)+1 WHERE id=?",
                (iso(), cid),
            )
        refreshed = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        before_path = os.path.join(UPLOAD, refreshed["before_photo"]) if refreshed["before_photo"] else None
        after_path = os.path.join(UPLOAD, refreshed["after_photo"]) if refreshed["after_photo"] else None
        proof = proof_verification(before_path, after_path, bool(refreshed["citizen_confirmed"]))
        impact = impact_score(refreshed)
        con.execute(
            "UPDATE complaints SET verification_score=?, verification_status=?, impact_score=?, impact_label=? WHERE id=?",
            (proof["score"], proof["status"], impact["score"], impact["label"], cid),
        )
        add_timeline(con, cid, "Proof Checked", f"CivicOS evidence check: {proof['score']}/100 — {proof['status']}.")

    # Free the previous/current team and immediately pull the next queued task.
    freed_workers = set()
    if old["assigned_worker"] and old["assigned_worker"] != worker_id:
        freed_workers.add(old["assigned_worker"])
    if status == "Resolved" and worker_id:
        freed_workers.add(worker_id)
    for freed in freed_workers:
        assign_next_pending(con, freed)

    con.commit()
    con.close()
    if changes and status != "Resolved":
        send_optional_email(cid, f"CivicOS complaint #{cid} updated", " ".join(changes))
        flash(t("complaint_updated"), "success")
    elif status == "Resolved" and old["status"] != "Resolved":
        delivered = send_resolution_email(cid)
        if delivered:
            flash(f"Complaint #{cid} marked Resolved. Citizen feedback email sent to {old['email']}.", "success")
        else:
            flash(f"Complaint #{cid} marked Resolved, but the citizen feedback email failed: {app.config.get('LAST_EMAIL_ERROR') or 'Check SMTP settings and the citizen email address.'}", "warning")
    else:
        flash(t("complaint_updated"), "success")
    return redirect(request.referrer or url_for("admin"))


@app.route("/department/<dept>")
@login_required
def department(dept):
    if dept not in DEPARTMENTS:
        flash("Unknown department.", "warning")
        return redirect(url_for("admin"))
    sync_escalations()
    con = db()
    complaints = con.execute(
        "SELECT * FROM complaints WHERE department=? ORDER BY escalated DESC, priority DESC, id DESC",
        (dept,),
    ).fetchall()
    stats = {
        "total": len(complaints),
        "resolved": sum(1 for complaint in complaints if complaint["status"] == "Resolved"),
        "pending": sum(1 for complaint in complaints if complaint["status"] != "Resolved"),
        "escalated": sum(1 for complaint in complaints if complaint["escalated"] and complaint["status"] != "Resolved"),
    }
    worker_stats = [item for item in calculate_worker_stats(con) if item["department"] == dept]
    con.close()
    return render_template("department.html", dept=dept, title=DEPARTMENTS[dept], complaints=complaints, stats=stats, worker_stats=worker_stats)


@app.route("/workers")
@login_required
def workers_dashboard():
    sync_escalations()
    con = db()
    worker_stats = calculate_worker_stats(con)
    totals = {
        "workers": len(worker_stats),
        "active": sum(item["active"] for item in worker_stats),
        "awaiting_review": sum(item["awaiting_review"] for item in worker_stats),
        "completed": sum(item["completed"] for item in worker_stats),
        "escalated": sum(item["escalated"] for item in worker_stats),
        "available": sum(1 for item in worker_stats if not item["busy"]),
        "incentive_eligible": sum(1 for item in worker_stats if item["incentive_eligible"]),
    }
    con.close()
    return render_template("workers.html", worker_stats=worker_stats, totals=totals)


@app.route("/worker/<worker_id>")
@login_required
def worker_dashboard(worker_id):
    return render_worker_dashboard(worker_id, worker_view=False)


@app.route("/worker/update/<int:cid>", methods=["POST"])
@worker_required
def worker_update(cid):
    """Worker-owned field update endpoint.

    Administrators may inspect worker performance through the admin Worker Center,
    but they cannot operate a worker's field dashboard or submit updates on the
    worker's behalf. This route therefore requires an authenticated worker session
    and enforces assignment ownership for every update.
    """
    requested_status = request.form.get("status") or "In Progress"
    if requested_status not in {"Assigned", "In Progress", "Resolved"}:
        flash("Invalid worker status update.", "warning")
        return redirect(url_for("worker_portal"))
    note = (request.form.get("admin_note") or "").strip()
    try:
        after_photo = save_file("after_photo")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("worker_portal"))

    con = db()
    old = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    submitted_worker = (request.form.get("worker_id") or "").strip()
    signed_worker_id = session.get("worker_id")
    if old:
        if signed_worker_id != (old["assigned_worker"] or "") or submitted_worker != signed_worker_id:
            con.close()
            flash("You can update only the task assigned to your authenticated worker account.", "danger")
            return redirect(url_for("worker_portal"))
    if not old or not old["assigned_worker"]:
        con.close()
        flash("This task is not assigned to a field team.", "warning")
        return redirect(url_for("worker_portal"))
    if old["status"] in {"Resolved", "Awaiting Admin Verification"}:
        con.close()
        flash("Completion has already been submitted. The authority must review it before the case can proceed.", "warning")
        return redirect(url_for("worker_portal"))

    completion_submit = requested_status == "Resolved"
    if completion_submit and not (after_photo or old["after_photo"]):
        con.close()
        flash("Upload after-work photo evidence before submitting completion for authority verification.", "warning")
        return redirect(url_for("worker_portal"))

    status = "Awaiting Admin Verification" if completion_submit else requested_status
    updated = iso()
    if after_photo:
        con.execute(
            "UPDATE complaints SET status=?,admin_note=?,after_photo=?,updated_at=?,worker_completion_requested_at=? WHERE id=?",
            (status, note, after_photo, updated, updated if completion_submit else old["worker_completion_requested_at"], cid),
        )
    else:
        con.execute(
            "UPDATE complaints SET status=?,admin_note=?,updated_at=?,worker_completion_requested_at=? WHERE id=?",
            (status, note, updated, updated if completion_submit else old["worker_completion_requested_at"], cid),
        )

    changes = []
    if old["status"] != status:
        if completion_submit:
            add_timeline(con, cid, "Worker Completion Submitted", note or "Field team submitted completion proof for authority verification.")
            changes.append("Field team submitted completion proof. Authority verification is now required before closure.")
        else:
            add_timeline(con, cid, status, note or f"Field team updated status to {status}.")
            changes.append(f"Field work status changed to {status}.")
    if after_photo:
        add_timeline(con, cid, "After Photo Uploaded", "Field team uploaded completion evidence for authority review.")
        changes.append("After-work proof was uploaded.")
    if note and note != (old["admin_note"] or ""):
        changes.append(f"Field update: {note}")

    if completion_submit:
        current_after = after_photo or old["after_photo"]
        before_path = os.path.join(UPLOAD, old["before_photo"]) if old["before_photo"] else None
        after_path = os.path.join(UPLOAD, current_after) if current_after else None
        proof = proof_verification(before_path, after_path, False)
        con.execute(
            "UPDATE complaints SET verification_score=?,verification_status=?,impact_score=?,impact_label=? WHERE id=?",
            (proof["score"], proof["status"], impact_score(old)["score"], impact_score(old)["label"], cid),
        )
        add_timeline(con, cid, "Proof Precheck", f"Automated evidence precheck: {proof['score']}/100 — {proof['status']}. Final authority review pending.")
        create_notification(con, cid, "Completion proof submitted", "The field team submitted completion proof. CivicOS is waiting for authority verification before asking you to confirm the real-world result.", "info")
        audit_action(con, "Worker Completion Submitted", f"{worker_label(old['assigned_worker'])} requested final authority verification.", cid, actor_type="worker", actor_id=old["assigned_worker"])
        # Worker has completed field execution and can receive a new task while QA is handled by the authority.
        assign_next_pending(con, old["assigned_worker"])
    elif changes:
        create_notification(con, cid, "Field team update", " ".join(changes), "info")
        audit_action(con, "Worker Status Updated", " ".join(changes), cid, actor_type="worker", actor_id=old["assigned_worker"])

    con.commit(); con.close()
    if changes and not completion_submit:
        send_optional_email(cid, f"CivicOS complaint #{cid} field update", " ".join(changes))
    flash("Completion submitted for authority verification." if completion_submit else t("task_updated"), "success")
    return redirect(url_for("worker_portal"))


@app.route("/verify-resolution/<int:cid>", methods=["POST"])
def verify_resolution(cid):
    if not session.get("citizen_id"):
        flash("Sign in to verify a resolved civic issue. Each account can verify once per resolution cycle.", "warning")
        return redirect(url_for("citizen_login", next=url_for("track", cid=cid)))
    citizen = current_citizen()
    if not citizen or not citizen["email_verified"]:
        flash("Verify your Civic Account email before community-verifying resolved work.", "warning")
        return redirect(url_for("citizen_profile"))
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not row or row["status"] != "Resolved":
        con.close(); flash("Only a resolved civic case can be community-verified.", "warning")
        return redirect(url_for("track", cid=cid))
    existing = con.execute("SELECT id FROM resolution_reviews WHERE complaint_id=? AND user_id=? AND resolution_cycle=?", (cid, session["citizen_id"], int(row["resolution_cycle"] or 1))).fetchone()
    if existing:
        con.close(); flash("You already verified this civic case. Each account can respond once.", "warning")
        return redirect(url_for("track", cid=cid))
    con.execute(
        "INSERT INTO resolution_reviews(complaint_id,user_id,worker_id,resolution_cycle,verdict,rating,feedback,review_status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (cid, session["citizen_id"], row["assigned_worker"], int(row["resolution_cycle"] or 1), "Community Confirmed", None, "Nearby citizen confirmed the visible resolution.", "Community Verification", iso()),
    )
    add_timeline(con, cid, "Community Resolution Verification", "A verified Civic Account confirmed the resolved work once.")
    audit_action(con, "Community Verified Resolution", f"Citizen account verified resolved case #{cid}.", cid)
    con.commit(); con.close()
    flash("Your one-time community verification was recorded.", "success")
    return redirect(url_for("track", cid=cid))


@app.route("/complaint/<int:cid>")
def complaint_detail(cid):
    sync_escalations()
    con = db()
    comp = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    timeline = con.execute("SELECT * FROM timeline WHERE complaint_id=? ORDER BY id", (cid,)).fetchall()
    feedback_rows = con.execute("SELECT * FROM feedback WHERE complaint_id=? ORDER BY id DESC", (cid,)).fetchall()
    notifications = con.execute("SELECT * FROM notifications WHERE complaint_id=? ORDER BY id DESC LIMIT 10", (cid,)).fetchall()
    worker_stats = calculate_worker_stats(con) if session.get("admin") else []
    worker_states = {item["id"]: item for item in worker_stats}
    reserve_guard_enabled = get_setting(con, "reserve_guard_enabled", "1") == "1" if session.get("admin") else False
    disaster_mode = get_setting(con, "disaster_mode", "0") == "1" if session.get("admin") else False
    trust_assessment = con.execute("SELECT * FROM complaint_trust_assessments WHERE complaint_id=?", (cid,)).fetchone() if comp else None
    con.close()
    if not comp:
        return render_template("complaint_detail.html", comp=None, timeline=[], feedback=[]), 404
    if session.get("worker_id") and not session.get("admin") and comp["assigned_worker"] != session.get("worker_id"):
        flash("Worker accounts can open only complaints assigned to their own field team.", "danger")
        return redirect(url_for("worker_portal"))
    complaint_intelligence = {
        "impact": impact_score(comp),
        "delay": cost_of_delay(comp, 7),
        "cascade": cascade_for(comp, 7),
    }
    before_path = os.path.join(UPLOAD, comp["before_photo"]) if comp["before_photo"] else None
    after_path = os.path.join(UPLOAD, comp["after_photo"]) if comp["after_photo"] else None
    proof = proof_verification(before_path, after_path, bool(comp["citizen_confirmed"]))
    return render_template(
        "complaint_detail.html",
        comp=comp,
        timeline=timeline,
        feedback=feedback_rows,
        notifications=notifications,
        worker_states=worker_states,
        complaint_intelligence=complaint_intelligence,
        proof=proof,
        reserve_guard_enabled=reserve_guard_enabled,
        disaster_mode=disaster_mode,
        trust_assessment=trust_assessment,
    )


@app.route("/transparency")
def transparency():
    sync_escalations()
    con = db()
    complaints = con.execute(
        """SELECT c.* FROM complaints c
           LEFT JOIN complaint_trust_assessments a ON a.complaint_id=c.id
           WHERE COALESCE(a.public_visibility,'Normal')!='Quarantined'
           ORDER BY c.id DESC LIMIT 30"""
    ).fetchall()
    stats = get_stats(con)
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    con.close()
    return render_template("transparency.html", complaints=complaints, stats=stats, dept_perf=dept_perf, ward_data=ward_data)


@app.route("/api/reverse-geocode")
def reverse_geocode_api():
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except ValueError:
        return jsonify(ok=False, error="Invalid coordinates"), 400

    query = urllib.parse.urlencode({
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "addressdetails": 1,
        "zoom": 18,
    })
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/reverse?{query}",
        headers={"User-Agent": "CivicOS-Hackathon/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
        address = data.get("address", {}) or {}
        ordered_keys = (
            "house_number", "road", "pedestrian", "neighbourhood", "suburb",
            "village", "town", "city", "city_district", "county", "state_district",
            "state", "postcode", "country"
        )
        exact_parts = []
        for key in ordered_keys:
            value = str(address.get(key) or "").strip()
            if value and value not in exact_parts:
                exact_parts.append(value)
        exact_address = ", ".join(exact_parts) or data.get("display_name") or f"GPS location: {lat:.6f}, {lon:.6f}"
        locality = next((str(address.get(k) or "").strip() for k in ("neighbourhood", "suburb", "village", "town", "city", "county") if str(address.get(k) or "").strip()), "Live location")
        district = next((str(address.get(k) or "").strip() for k in ("city_district", "state_district", "county") if str(address.get(k) or "").strip() and str(address.get(k) or "").strip() != locality), "")
        short_label = f"{locality}, {district}" if district else locality
        return jsonify(
            ok=True,
            display_name=data.get("display_name") or exact_address,
            exact_address=exact_address,
            short_label=short_label,
            coordinates={"lat": round(lat, 7), "lon": round(lon, 7)},
            address=address,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        fallback = f"GPS location: {lat:.7f}, {lon:.7f}"
        return jsonify(ok=False, display_name=fallback, exact_address=fallback, short_label=f"{lat:.4f}, {lon:.4f}", coordinates={"lat": round(lat, 7), "lon": round(lon, 7)}, offline=True)


@app.route("/api/geocode")
def geocode_api():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify(ok=False, results=[], error="Enter at least 3 characters"), 400
    query = urllib.parse.urlencode({"format": "jsonv2", "q": q, "limit": 5, "addressdetails": 1})
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{query}",
        headers={"User-Agent": "CivicOS-Hackathon/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = [
            {"display_name": item.get("display_name"), "lat": item.get("lat"), "lon": item.get("lon")}
            for item in data
            if item.get("lat") and item.get("lon")
        ]
        return jsonify(ok=True, results=results)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return jsonify(ok=False, results=[], error="Address search is temporarily unavailable"), 503


@app.route("/api/dashboard-data")
def dashboard_data():
    sync_escalations()
    con = db()
    if session.get("admin"):
        rows = con.execute("SELECT * FROM complaints").fetchall()
    else:
        rows = con.execute(
            """SELECT c.* FROM complaints c
               LEFT JOIN complaint_trust_assessments a ON a.complaint_id=c.id
               WHERE COALESCE(a.public_visibility,'Normal')!='Quarantined'"""
        ).fetchall()
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    worker_stats = calculate_worker_stats(con)
    con.close()
    status = {}
    markers = []
    for row in rows:
        status[row["status"]] = status.get(row["status"], 0) + 1
        if row["latitude"] is None or row["longitude"] is None:
            continue
        markers.append(
            {
                "id": row["id"],
                "title": row["title"],
                "lat": row["latitude"],
                "lon": row["longitude"],
                "priority": row["priority"],
                "village": row["village"],
                "ward": row["ward"],
                "address": row["address"] or row["location"],
                "department": row["department"],
                "departmentLabel": DEPARTMENTS.get(row["department"], row["department"]),
                "status": row["status"],
                "escalated": bool(row["escalated"]),
                "category": row["category"],
                "sla": sla_label(row),
            }
        )
    return jsonify(status=status, departmentPerformance=dept_perf, wardAnalytics=ward_data, workers=worker_stats, markers=markers)


# ============================================================
# GOVERNMENT ASSET MANAGEMENT ROUTES
# ============================================================


def asset_visual_svg(category, name, size=180):
    """Return a polished civic asset illustration instead of a QR code."""
    key = (category or "").lower().strip()
    palettes = {
        "roads": ("#f59e0b", "#92400e"),
        "water": ("#38bdf8", "#075985"),
        "electricity": ("#facc15", "#854d0e"),
        "safety": ("#a78bfa", "#5b21b6"),
        "health": ("#34d399", "#065f46"),
        "fire": ("#fb7185", "#9f1239"),
    }
    accent, dark = palettes.get(key, ("#60a5fa", "#1e3a8a"))
    safe_name = escape(str(name or "Government Asset"))
    safe_category = escape(str(category or "municipal"))
    if key == "roads":
        object_svg = '''<path d="M58 132L90 48h36l32 84" fill="none" stroke="#475569" stroke-width="18" stroke-linecap="round"/><path d="M108 56v22m0 14v22m0 14v10" stroke="#fff" stroke-width="5" stroke-linecap="round"/><path d="M45 139h126" stroke="#334155" stroke-width="8" stroke-linecap="round"/>'''
    elif key == "water":
        object_svg = '''<rect x="57" y="58" width="102" height="73" rx="18" fill="#bae6fd" stroke="#0369a1" stroke-width="7"/><path d="M70 84h76M70 105h76" stroke="#0284c7" stroke-width="7" stroke-linecap="round"/><path d="M108 40v18M90 40h36" stroke="#075985" stroke-width="8" stroke-linecap="round"/><path d="M108 132v16h38" stroke="#075985" stroke-width="8" stroke-linecap="round"/>'''
    elif key == "electricity":
        object_svg = '''<path d="M108 36v108M78 56h60M83 83h50M68 144h80" stroke="#854d0e" stroke-width="8" stroke-linecap="round"/><path d="M83 52l-16 12m74-12l16 12" stroke="#854d0e" stroke-width="6"/><path d="M116 62l-18 32h17l-12 30 31-42h-18z" fill="#facc15" stroke="#a16207" stroke-width="4"/>'''
    elif key == "safety":
        object_svg = '''<path d="M108 38l48 19v37c0 31-20 49-48 61-28-12-48-30-48-61V57z" fill="#ede9fe" stroke="#6d28d9" stroke-width="7"/><path d="M108 65v50M83 90h50" stroke="#7c3aed" stroke-width="8" stroke-linecap="round"/>'''
    elif key == "health":
        object_svg = '''<rect x="58" y="48" width="100" height="96" rx="12" fill="#ecfdf5" stroke="#047857" stroke-width="7"/><path d="M108 62v40M88 82h40" stroke="#10b981" stroke-width="10" stroke-linecap="round"/><path d="M76 119h64" stroke="#047857" stroke-width="6" stroke-linecap="round"/><path d="M48 144h120" stroke="#065f46" stroke-width="8" stroke-linecap="round"/>'''
    elif key == "fire":
        object_svg = '''<path d="M108 42c13 18 30 29 30 53 0 24-14 43-30 43s-30-19-30-43c0-17 10-29 22-42 0 12 5 19 10 23 7-11 4-22-2-34z" fill="#fb7185" stroke="#be123c" stroke-width="6"/><path d="M108 73c7 10 14 17 14 29 0 11-6 21-14 21s-14-10-14-21c0-7 4-13 9-18 0 5 2 8 5 10 3-7 2-13 0-21z" fill="#fbbf24"/>'''
    else:
        object_svg = '''<rect x="60" y="48" width="96" height="96" rx="18" fill="#dbeafe" stroke="#2563eb" stroke-width="7"/><path d="M108 70v52M82 96h52" stroke="#2563eb" stroke-width="10" stroke-linecap="round"/>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 216 216" role="img" aria-label="{safe_name} object illustration"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="{accent}" stop-opacity=".18"/><stop offset="1" stop-color="{dark}" stop-opacity=".08"/></linearGradient></defs><rect x="6" y="6" width="204" height="204" rx="34" fill="url(#g)" stroke="{accent}" stroke-opacity=".28" stroke-width="2"/><circle cx="108" cy="108" r="76" fill="#fff" fill-opacity=".72"/>{object_svg}<text x="108" y="181" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" font-weight="800" fill="{dark}">{safe_category.upper()}</text></svg>'''


def asset_visual_data_uri(category, name):
    import base64
    return "data:image/svg+xml;base64," + base64.b64encode(asset_visual_svg(category, name, 240).encode("utf-8")).decode("ascii")



def safe_asset_specs(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def ensure_asset_visual_file(asset):
    """Create a real image file for every current asset when it has no uploaded photo."""
    photo = asset["photo"] if "photo" in asset.keys() else None
    if photo and os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], photo)):
        return photo
    visual_dir = os.path.join(app.config["UPLOAD_FOLDER"], "asset_visuals")
    os.makedirs(visual_dir, exist_ok=True)
    filename = f"{secure_filename(asset['asset_uid'])}.svg"
    path = os.path.join(visual_dir, filename)
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(asset_visual_svg(asset["category"], asset["name"], 520))
    return os.path.join("asset_visuals", filename).replace("\\", "/")


def asset_image_url(asset):
    photo = asset["photo"] if "photo" in asset.keys() else None
    if photo and os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], photo)):
        return url_for("static", filename="uploads/" + photo)
    generated = ensure_asset_visual_file(asset)
    return url_for("static", filename="uploads/" + generated)


def asset_coordinates_from_request(request_obj, location=""):
    """Use submitted browser GPS first, then geocode the typed address."""
    lat = lon = None
    try:
        lat_raw = (request_obj.form.get("latitude") or "").strip()
        lon_raw = (request_obj.form.get("longitude") or "").strip()
        if lat_raw and lon_raw:
            lat, lon = float(lat_raw), float(lon_raw)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
    except (TypeError, ValueError):
        lat = lon = None
    if lat is not None and lon is not None:
        return lat, lon, "gps"
    location = (location or "").strip()
    if not location:
        return None, None, "none"
    query = urllib.parse.urlencode({"format":"jsonv2", "q":location, "limit":1, "addressdetails":1})
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{query}",
        headers={"User-Agent":"CivicOS-Hackathon/1.0","Accept":"application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=7) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data and data[0].get("lat") and data[0].get("lon"):
            return float(data[0]["lat"]), float(data[0]["lon"]), "address"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        pass
    return None, None, "none"

@app.route("/admin/assets")
@login_required
def admin_assets():
    """Government Asset Registry — visual, GPS-first asset management console."""
    sync_escalations()
    selected_category = (request.args.get("category") or "all").strip()
    ward_filter = (request.args.get("ward") or "all").strip()
    status_filter = (request.args.get("status") or "all").strip()
    dept_filter = (request.args.get("department") or "all").strip()
    search_query = (request.args.get("q") or "").strip()
    con = db()
    context = admin_common_context(con)
    all_assets = con.execute("SELECT * FROM assets ORDER BY id DESC").fetchall()
    wards_set = sorted({a["ward"] for a in all_assets if a["ward"]}) or ["Ward 1 · Central", "Ward 2 · East", "Ward 3 · North"]
    filtered = all_assets
    if selected_category != "all": filtered = [a for a in filtered if a["category"] == selected_category]
    if ward_filter != "all": filtered = [a for a in filtered if a["ward"] == ward_filter]
    if status_filter != "all": filtered = [a for a in filtered if a["status"] == status_filter]
    if dept_filter != "all": filtered = [a for a in filtered if a["department"] == dept_filter]
    if search_query:
        q = search_query.lower()
        filtered = [a for a in filtered if any(q in str(a[k] or "").lower() for k in ("asset_uid","name","location","village","ward","specifications"))]
    marker_data = []
    for a in filtered:
        marker_data.append({"id":a["id"],"uid":a["asset_uid"],"name":a["name"],"category":a["category"],"lat":a["latitude"],"lon":a["longitude"],"condition":a["condition_score"] or 100,"status":a["status"],"ward":a["ward"],"location":a["location"]})
    category_options = [(k, v.get("name", k), v.get("department", "")) for k,v in ASSET_CATEGORIES.items() if k != "auto"]
    status_options = list(ASSET_STATUS_OPTIONS)
    worker_options = WORKERS
    image_urls = {a["id"]: asset_image_url(a) for a in all_assets}
    con.close()
    return render_template_string("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CivicOS · Government Assets</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--panel:#fff;--bg:#f5f7fb;--brand:#2563eb;--good:#059669;--shadow:0 12px 32px rgba(15,23,42,.08)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{max-width:1500px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:20px}.eyebrow{font-size:11px;font-weight:900;letter-spacing:.12em;text-transform:uppercase;color:var(--brand)}h1{margin:3px 0;font-size:30px;letter-spacing:-.03em}.sub{color:var(--muted)}.actions{display:flex;gap:9px;flex-wrap:wrap}.btn{border:0;border-radius:12px;padding:10px 14px;font-weight:800;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:7px}.btn.primary{background:var(--brand);color:white}.btn.soft{background:#eaf2ff;color:#1d4ed8}.btn.dark{background:#0f172a;color:#fff}.btn.green{background:#ecfdf5;color:#047857}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.stat{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:17px;box-shadow:var(--shadow)}.stat b{font-size:25px;display:block}.stat span{color:var(--muted);font-weight:700;font-size:12px}.layout{display:grid;grid-template-columns:1.35fr .85fr;gap:18px;align-items:start}.panel{background:var(--panel);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden}.panel-head{padding:17px 19px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:12px}.panel-head h2{font-size:16px;margin:0}.filters{padding:14px;display:grid;grid-template-columns:1.6fr repeat(4,1fr);gap:9px;border-bottom:1px solid var(--line)}input,select,textarea{width:100%;border:1px solid #cbd5e1;background:#fff;border-radius:10px;padding:10px 11px;color:var(--ink);font:inherit}textarea{min-height:78px;resize:vertical}.asset-list{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;padding:14px}.asset{border:1px solid var(--line);border-radius:18px;padding:14px;background:#fff;display:grid;grid-template-columns:104px 1fr;gap:14px}.asset-img{width:104px;height:104px;border-radius:16px;background:#f8fafc;display:block;object-fit:cover;border:1px solid var(--line)}.asset h3{margin:0 0 2px;font-size:16px}.uid{font-size:11px;font-weight:900;color:var(--muted);letter-spacing:.06em}.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.chip{padding:4px 8px;border-radius:999px;background:#f1f5f9;color:#475569;font-size:11px;font-weight:800}.chip.good{background:#ecfdf5;color:#047857}.chip.warn{background:#fff7ed;color:#c2410c}.loc{color:#475569;font-size:12px}.asset-actions{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap}.small{padding:7px 9px;font-size:11px}.map{height:430px}.form{padding:18px}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.full{grid-column:1/-1}.gps{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.gps-status{font-size:12px;color:var(--muted);font-weight:700}.section-note{background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af;border-radius:12px;padding:10px 12px;font-size:12px;margin-bottom:12px}.empty{padding:35px;text-align:center;color:var(--muted)}@media(max-width:1050px){.layout{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.shell{padding:13px}.top{align-items:flex-start;flex-direction:column}.filters{grid-template-columns:1fr 1fr}.asset-list{grid-template-columns:1fr}.formgrid{grid-template-columns:1fr}.full{grid-column:auto}}
</style></head><body><div class="shell">
<div class="top"><div><div class="eyebrow">CivicOS · Municipal Registry</div><h1>Government Assets</h1><div class="sub">Visual asset intelligence, GPS verification and preventive maintenance in one workspace.</div></div><div class="actions"><a class="btn soft" href="{{ url_for('admin_asset_analytics') }}">Analytics</a><a class="btn dark" href="{{ url_for('admin_assets_export') }}">Export Ledger</a><a class="btn" style="background:#e2e8f0;color:#334155" href="{{ url_for('admin') }}">Command Center</a></div></div>
<div class="grid"><div class="stat"><span>REGISTERED ASSETS</span><b>{{ all_assets|length }}</b></div><div class="stat"><span>VISIBLE RESULTS</span><b>{{ filtered|length }}</b></div><div class="stat"><span>CRITICAL / DEFECTIVE</span><b>{{ all_assets|selectattr('status','equalto','Critical / Defective')|list|length }}</b></div><div class="stat"><span>GPS-MAPPED</span><b>{{ all_assets|selectattr('latitude')|list|length }}</b></div></div>
<div class="layout"><div class="panel"><div class="panel-head"><h2>Asset Registry</h2><span class="sub">{{ filtered|length }} record(s)</span></div><form class="filters" method="get"><input name="q" value="{{ search_query }}" placeholder="Search asset, UID, location…"><select name="category"><option value="all">All categories</option>{% for k,n,d in category_options %}<option value="{{k}}" {% if selected_category==k %}selected{% endif %}>{{n}}</option>{% endfor %}</select><select name="ward"><option value="all">All wards</option>{% for w in wards_list %}<option value="{{w}}" {% if ward_filter==w %}selected{% endif %}>{{w}}</option>{% endfor %}</select><select name="status"><option value="all">All statuses</option>{% for st in status_options %}<option value="{{st}}" {% if status_filter==st %}selected{% endif %}>{{st}}</option>{% endfor %}</select><select name="department"><option value="all">All departments</option>{% for k,v in departments.items() %}<option value="{{k}}" {% if dept_filter==k %}selected{% endif %}>{{v}}</option>{% endfor %}</select></form><div class="asset-list">{% for a in filtered %}<article class="asset"><img class="asset-img" src="{{image_urls[a.id]}}" alt="{{a.name|e}}"><div><div class="uid">{{a['asset_uid']}}</div><h3>{{a['name']}}</h3><div class="chips"><span class="chip">{{a['category']|title}}</span><span class="chip {% if a['status']=='Operational' %}good{% elif a['status']=='Critical / Defective' %}warn{% endif %}">{{a['status']}}</span><span class="chip">Condition {{a['condition_score'] or 100}}%</span></div><div class="loc">📍 {{a['location']}} · {{a['ward']}}</div><div class="asset-actions"><a class="btn primary small" href="{{url_for('admin_asset_detail',aid=a['id'])}}">Open asset</a><a class="btn soft small" target="_blank" href="{{url_for('admin_asset_visual',asset_uid=a['asset_uid'])}}">Print visual</a></div></div></article>{% else %}<div class="empty full">No government assets match the current filters.</div>{% endfor %}</div></div>
<div class="panel"><div class="panel-head"><h2>Register Government Asset</h2><span class="chip good">GPS-first</span></div><form class="form" method="post" enctype="multipart/form-data" action="{{url_for('admin_assets_new')}}"><div class="section-note">Use <b>Detect current GPS</b> to capture the device location, reverse-geocode it into a readable address, and store the exact coordinates with the asset.</div><div class="formgrid"><div class="full"><label>Asset name</label><input name="name" required placeholder="e.g. Ward 2 Water Tank"></div><div><label>Category</label><select name="category">{% for k,n,d in category_options %}<option value="{{k}}">{{n}}</option>{% endfor %}</select></div><div><label>Ward</label><select name="ward">{% for w in wards_list %}<option value="{{w}}">{{w}}</option>{% endfor %}</select></div><div><label>Village / locality</label><input name="village" value="Talegaon Central"></div><div><label>Assigned field team</label><select name="assigned_worker"><option value="">Unassigned</option>{% for w in worker_options %}<option value="{{w.id}}">{{w.id}} · {{w.name}}</option>{% endfor %}</select></div><div class="full"><label>Asset location / address</label><input id="asset-location" name="location" placeholder="GPS or address"></div><div class="full gps"><button type="button" class="btn green" id="gpsBtn">◎ Detect current GPS</button><span id="gpsStatus" class="gps-status">Click to detect the device location.</span></div><input type="hidden" id="latitude" name="latitude"><input type="hidden" id="longitude" name="longitude"><div><label>Condition score</label><input type="number" min="0" max="100" name="condition_score" value="100"></div><div><label>Estimated value (₹)</label><input type="number" min="0" step="100" name="estimated_value" value="0"></div><div class="full upload"><label>Asset photo (optional)</label><input type="file" name="photo" accept="image/png,image/jpeg,image/webp"><div class="gps-status">If no photo is uploaded, CivicOS shows the correct object image for the asset category.</div></div><div class="full"><label>Notes</label><textarea name="notes" placeholder="Asset specifications, inspection notes, landmarks…"></textarea></div><div class="full"><button class="btn primary" style="width:100%;justify-content:center">Add asset to registry</button></div></div></form></div></div>
<div class="panel" style="margin-top:18px"><div class="panel-head"><h2>Live Asset Map</h2><span class="sub">Markers use stored GPS coordinates</span></div><div id="assetMap" class="map"></div></div></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const markers={{ marker_data|tojson }}; const map=L.map('assetMap').setView([20.5937,78.9629],5); L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors'}).addTo(map); const bounds=[];
markers.forEach(a=>{if(a.lat==null||a.lon==null)return; const m=L.marker([a.lat,a.lon]).addTo(map); m.bindPopup('<b>'+String(a.name).replace(/</g,'&lt;')+'</b><br>'+String(a.uid).replace(/</g,'&lt;')+'<br>'+String(a.location||'').replace(/</g,'&lt;')); bounds.push([a.lat,a.lon]);}); if(bounds.length)map.fitBounds(bounds,{padding:[25,25],maxZoom:15});
const gpsBtn=document.getElementById('gpsBtn'),gpsStatus=document.getElementById('gpsStatus'),loc=document.getElementById('asset-location'); function detectGPS(){if(!navigator.geolocation){gpsStatus.textContent='This browser does not support GPS.';return}gpsBtn.disabled=true;gpsStatus.textContent='Requesting precise location…';navigator.geolocation.getCurrentPosition(async p=>{const lat=p.coords.latitude,lon=p.coords.longitude;document.getElementById('latitude').value=lat;document.getElementById('longitude').value=lon;gpsStatus.textContent='GPS captured. Resolving address…';try{const r=await fetch('{{url_for("reverse_geocode_api")}}?lat='+encodeURIComponent(lat)+'&lon='+encodeURIComponent(lon));const d=await r.json();loc.value=d.exact_address||('GPS location: '+lat.toFixed(6)+', '+lon.toFixed(6));gpsStatus.textContent='✓ Location verified: '+lat.toFixed(6)+', '+lon.toFixed(6)}catch(e){loc.value='GPS location: '+lat.toFixed(6)+', '+lon.toFixed(6);gpsStatus.textContent='✓ GPS captured; address lookup unavailable.'}gpsBtn.disabled=false},e=>{const msg={1:'Location permission was denied. Allow location access and try again.',2:'Location unavailable. Check device GPS/network and retry.',3:'GPS request timed out. Try again.'}[e.code]||'Could not detect location.';gpsStatus.textContent=msg;gpsBtn.disabled=false},{enableHighAccuracy:true,timeout:15000,maximumAge:0})}gpsBtn.addEventListener('click',detectGPS);</script></body></html>""", all_assets=all_assets, filtered=filtered, selected_category=selected_category, ward_filter=ward_filter, status_filter=status_filter, dept_filter=dept_filter, search_query=search_query, wards_list=wards_set, category_options=category_options, status_options=status_options, worker_options=worker_options, marker_data=marker_data, image_urls=image_urls, departments=DEPARTMENTS, asset_visual_svg=asset_visual_svg, **context)

@app.route("/admin/assets/new", methods=["POST"])
@login_required
def admin_assets_new():
    name = (request.form.get("name") or "").strip()
    category = (request.form.get("category") or "roads").strip()
    ward = (request.form.get("ward") or "Ward 1 · Central").strip()
    village = (request.form.get("village") or "Talegaon Central").strip()
    location = (request.form.get("location") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    assigned_worker = (request.form.get("assigned_worker") or "").strip() or None

    if not name:
        flash("Asset name is required.", "danger")
        return redirect(url_for("admin_assets"))

    cat_info = ASSET_CATEGORIES.get(category)
    if not cat_info:
        flash("Invalid asset category.", "danger")
        return redirect(url_for("admin_assets"))
    dept = cat_info["department"]

    # Browser GPS is preferred; typed address is a fallback.
    prefix = f"AST-{category[:3].upper()}"
    con = db()
    count_row = con.execute("SELECT COUNT(*) AS c FROM assets WHERE category=?", (category,)).fetchone()
    seq = (count_row["c"] or 0) + 1
    asset_uid = f"{prefix}-{seq:03d}"
    while con.execute("SELECT 1 FROM assets WHERE asset_uid=?", (asset_uid,)).fetchone():
        seq += 1
        asset_uid = f"{prefix}-{seq:03d}"

    lat_raw = (request.form.get("latitude") or "").strip()
    lon_raw = (request.form.get("longitude") or "").strip()
    lat = lon = None
    if lat_raw and lon_raw:
        try:
            lat, lon = float(lat_raw), float(lon_raw)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (ValueError, TypeError):
            lat = lon = None
    # GPS is preferred, but a typed address can still be geocoded as a safe fallback.
    if lat is None or lon is None:
        query = urllib.parse.urlencode({"format":"jsonv2","q":location,"limit":1,"addressdetails":1})
        req = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{query}",
            headers={"User-Agent":"CivicOS-Hackathon/1.0","Accept":"application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=7) as response:
                geo = json.loads(response.read().decode("utf-8"))
            if geo and geo[0].get("lat") and geo[0].get("lon"):
                lat, lon = float(geo[0]["lat"]), float(geo[0]["lon"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
    if lat is None or lon is None:
        con.close()
        flash("Could not determine the asset GPS location. Click Detect current GPS or enter a more specific address.", "danger")
        return redirect(url_for("admin_assets"))

    try:
        condition_score = int(request.form.get("condition_score") or 100)
    except ValueError:
        condition_score = 100

    try:
        estimated_val = float(request.form.get("estimated_value") or 0)
    except ValueError:
        estimated_val = 0.0

    photo = None
    try:
        photo = save_file("photo")
    except ValueError as exc:
        con.close()
        flash(str(exc), "danger")
        return redirect(url_for("admin_assets"))

    install_date = request.form.get("install_date") or datetime.now().strftime("%Y-%m-%d")
    default_days = cat_info.get("default_maintenance_days", 90)
    next_maint = (datetime.now() + timedelta(days=default_days)).strftime("%Y-%m-%d")

    # Extract dynamic specs from form
    specs = {}
    for k, v in request.form.items():
        if k.startswith("spec_") and v:
            spec_key = k[5:]
            specs[spec_key] = v

    con.execute(
        """INSERT INTO assets(
            asset_uid, name, category, department, ward, village, location,
            latitude, longitude, status, condition_score, install_date,
            last_inspection_date, next_maintenance_due, estimated_value,
            replacement_cost, specifications, photo, assigned_worker, notes,
            created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            asset_uid, name, category, dept, ward, village, location,
            lat, lon, "Operational", condition_score, install_date,
            install_date, next_maint, estimated_val, estimated_val * 1.15,
            json.dumps(specs), photo, assigned_worker, notes, iso(), iso()
        )
    )
    aid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()
    con.close()
    flash(f"Asset #{asset_uid} created successfully and added to municipal registry.", "success")
    return redirect(url_for("admin_asset_detail", aid=aid))

@app.route("/admin/assets/<int:aid>")
@login_required
def admin_asset_detail(aid):
    sync_escalations()
    con = db()
    asset = con.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    if not asset:
        con.close()
        flash("Asset record not found.", "warning")
        return redirect(url_for("admin_assets"))
    maintenance_logs = con.execute("SELECT * FROM asset_maintenance_logs WHERE asset_id=? ORDER BY id DESC", (aid,)).fetchall()
    linked_complaints = con.execute("SELECT * FROM complaints WHERE asset_id=? ORDER BY id DESC", (aid,)).fetchall()
    available_complaints = con.execute("SELECT * FROM complaints WHERE department=? AND (asset_id IS NULL OR asset_id!=?) ORDER BY id DESC LIMIT 30", (asset["department"], aid)).fetchall()
    context = admin_common_context(con)
    con.close()
    cat_info = ASSET_CATEGORIES.get(asset["category"], {})
    specs = safe_asset_specs(asset["specifications"])
    visual = asset_visual_svg(asset["category"], asset["name"], 210)
    image_url = asset_image_url(asset)
    return render_template_string("""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{asset.name}} · CivicOS Asset</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f5f7fb;--panel:#fff;--blue:#2563eb;--green:#059669;--orange:#d97706;--red:#dc2626;--shadow:0 12px 30px rgba(15,23,42,.08)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 Inter,system-ui,sans-serif}.wrap{max-width:1450px;margin:auto;padding:22px}.top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:18px}.crumb{color:var(--muted);font-size:12px;font-weight:800}.top h1{font-size:29px;margin:5px 0 2px;letter-spacing:-.03em}.uid{color:var(--muted);font-weight:900;letter-spacing:.06em}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:0;border-radius:11px;padding:9px 13px;font-weight:800;text-decoration:none;cursor:pointer;display:inline-flex;align-items:center;gap:7px}.primary{background:var(--blue);color:white}.soft{background:#eaf2ff;color:#1d4ed8}.green{background:#ecfdf5;color:#047857}.dark{background:#0f172a;color:#fff}.panel{background:var(--panel);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden}.hero{display:grid;grid-template-columns:240px 1fr 260px;gap:20px;padding:20px}.hero-img{width:240px;height:240px;object-fit:cover;border-radius:18px;border:1px solid var(--line);background:#f8fafc}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.fact{border:1px solid var(--line);border-radius:13px;padding:11px;background:#fbfdff}.fact span{display:block;color:var(--muted);font-size:11px;font-weight:800;text-transform:uppercase}.fact b{font-size:14px}.condition{border-radius:18px;background:linear-gradient(135deg,#eff6ff,#f8fafc);padding:18px}.score{font-size:42px;font-weight:950}.meter{height:10px;border-radius:99px;background:#dbeafe;overflow:hidden;margin:9px 0}.meter i{display:block;height:100%;background:var(--blue);width:{{asset.condition_score if asset.condition_score is not none else 0}}%}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}.panel-head{padding:16px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:10px}.panel-head h2{margin:0;font-size:16px}.body{padding:17px}label{display:block;font-size:11px;font-weight:900;color:#475569;margin:0 0 5px;text-transform:uppercase}input,select,textarea{width:100%;border:1px solid #cbd5e1;border-radius:10px;padding:9px 10px;font:inherit}textarea{min-height:80px}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.full{grid-column:1/-1}.log{border:1px solid var(--line);border-radius:15px;padding:13px;margin-bottom:10px;background:#fff}.log:last-child{margin-bottom:0}.logtop{display:flex;justify-content:space-between;gap:12px}.logtop b{font-size:13px}.muted{color:var(--muted);font-size:12px}.tag{padding:4px 8px;border-radius:999px;background:#ecfdf5;color:#047857;font-size:10px;font-weight:900;white-space:nowrap}.complaint{border:1px solid var(--line);border-radius:15px;padding:13px;margin-bottom:10px}.complaint a{color:var(--blue);font-weight:900;text-decoration:none}.complaint .row{display:flex;justify-content:space-between;gap:10px}.empty{padding:25px;text-align:center;color:var(--muted);border:1px dashed #cbd5e1;border-radius:14px}.map{height:300px}.specs{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.spec{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:9px}.spec small{display:block;color:var(--muted);font-weight:800}.danger{color:#b91c1c}@media(max-width:1000px){.hero{grid-template-columns:190px 1fr}.condition{grid-column:1/-1}.two{grid-template-columns:1fr}}@media(max-width:680px){.wrap{padding:12px}.top{flex-direction:column}.hero{grid-template-columns:1fr}.facts,.formgrid,.specs{grid-template-columns:1fr}.full{grid-column:auto}}
</style></head><body><div class="wrap">
<div class="top"><div><div class="crumb">Government Assets / Asset Detail</div><h1>{{asset.name}}</h1><div class="uid">{{asset.asset_uid}} · {{cat_info.get('name',asset.category)}}</div></div><div class="actions"><a class="btn soft" href="{{url_for('admin_assets')}}">← Asset Registry</a><a class="btn dark" target="_blank" href="{{url_for('admin_asset_visual',asset_uid=asset.asset_uid)}}">Print object visual</a></div></div>
<div class="panel hero"><img class="hero-img" src="{{image_url}}" alt="{{asset.name|e}}"><div><div class="facts"><div class="fact"><span>Status</span><b>{{asset.status}}</b></div><div class="fact"><span>Department</span><b>{{department_label(asset.department)}}</b></div><div class="fact"><span>Ward</span><b>{{asset.ward}}</b></div><div class="fact"><span>Village</span><b>{{asset.village}}</b></div><div class="fact"><span>Next maintenance</span><b>{{asset.next_maintenance_due or 'Not scheduled'}}</b></div><div class="fact"><span>Assigned team</span><b>{{worker_label(asset.assigned_worker)}}</b></div></div><div style="margin-top:12px" class="muted">📍 {{asset.location}}</div><div style="margin-top:8px" class="muted">GPS: {{asset.latitude or '—'}}, {{asset.longitude or '—'}}</div></div><div class="condition"><div class="muted">ASSET CONDITION</div><div class="score">{{asset.condition_score or 100}}%</div><div class="meter"><i></i></div><div class="muted">Last inspection: {{asset.last_inspection_date or 'Not recorded'}}</div></div></div>
<div class="two"><div class="panel"><div class="panel-head"><h2>Preventive Maintenance & Inspection</h2><span class="tag">{{maintenance_logs|length}} log(s)</span></div><div class="body"><form method="post" action="{{url_for('admin_asset_maintenance',aid=asset.id)}}"><div class="formgrid"><div><label>Activity type</label><select name="maintenance_type"><option>Preventive Maintenance</option><option>Routine Inspection</option><option>Corrective Maintenance</option><option>Emergency Repair</option></select></div><div><label>Performed by</label><input name="performed_by" value="{{session.get('admin','Field Crew')}}"></div><div><label>Condition after</label><input name="condition_after" type="number" min="0" max="100" value="{{asset.condition_score or 100}}"></div><div><label>Cost (₹)</label><input name="cost" type="number" min="0" step="100" value="0"></div><div><label>Status after</label><select name="status_after">{% for st in asset_status_options %}<option value="{{st}}" {% if st==asset.status %}selected{% endif %}>{{st}}</option>{% endfor %}</select></div><div class="full"><label>Inspection / maintenance notes</label><textarea name="notes" placeholder="Record findings, parts replaced, safety checks and next actions…"></textarea></div><div class="full"><button class="btn primary">Save inspection log</button></div></div></form><hr style="border:0;border-top:1px solid var(--line);margin:18px 0">{% for log in maintenance_logs %}<div class="log"><div class="logtop"><b>{{log.maintenance_type}}</b><span class="tag">{{log.status_after}}</span></div><div class="muted">{{log.performed_at}} · {{log.performed_by}} · ₹{{'{:,.0f}'.format(log.cost or 0)}}</div><div style="margin-top:7px">{{log.notes}}</div><div class="muted" style="margin-top:6px">Condition after: <b>{{log.condition_after}}%</b></div></div>{% else %}<div class="empty">No inspection or maintenance activity has been recorded yet.</div>{% endfor %}</div></div>
<div class="panel"><div class="panel-head"><h2>Linked Citizen Complaints</h2><span class="tag">{{linked_complaints|length}} linked</span></div><div class="body"><form method="post" action="{{url_for('admin_asset_link_complaint',aid=asset.id)}}"><label>Link a department complaint to this asset</label><div style="display:flex;gap:8px"><select name="complaint_id" required style="flex:1"><option value="">Select complaint…</option>{% for c in available_complaints %}<option value="{{c.id}}">#{{c.id}} · {{c.title}} · {{c.status}}</option>{% endfor %}</select><button class="btn green">Link complaint</button></div></form><hr style="border:0;border-top:1px solid var(--line);margin:18px 0">{% for c in linked_complaints %}<div class="complaint"><div class="row"><a href="{{url_for('complaint_detail',cid=c.id)}}">#{{c.id}} · {{c.title}}</a><span class="tag">{{c.status}}</span></div><div class="muted">Citizen: {{c.citizen_name or 'Anonymous'}} · Ward: {{c.ward}} · Priority: {{c.priority}}</div><div style="margin-top:7px">{{c.description}}</div></div>{% else %}<div class="empty">No citizen complaints are linked to this asset. Linking complaints here creates a traceable asset-to-service history.</div>{% endfor %}</div></div></div>
<div class="two"><div class="panel"><div class="panel-head"><h2>Asset Information & Edit</h2></div><div class="body"><form method="post" enctype="multipart/form-data" action="{{url_for('admin_asset_edit',aid=asset.id)}}"><div class="formgrid"><div><label>Asset name</label><input name="name" value="{{asset.name}}"></div><div><label>Status</label><select name="status">{% for st in asset_status_options %}<option value="{{st}}" {% if st==asset.status %}selected{% endif %}>{{st}}</option>{% endfor %}</select></div><div><label>Ward</label><input name="ward" value="{{asset.ward}}"></div><div><label>Village</label><input name="village" value="{{asset.village}}"></div><div><label>Assigned field team</label><select name="assigned_worker"><option value="">Unassigned</option>{% for w in workers %}<option value="{{w.id}}" {% if w.id==asset.assigned_worker %}selected{% endif %}>{{w.id}} · {{w.name}}</option>{% endfor %}</select></div><div class="full"><label>Location</label><input name="location" value="{{asset.location}}"></div><div><label>Latitude</label><input id="editLat" name="latitude" type="number" step="0.0000001" min="-90" max="90" value="{{asset.latitude if asset.latitude is not none else ''}}"></div><div><label>Longitude</label><input id="editLon" name="longitude" type="number" step="0.0000001" min="-180" max="180" value="{{asset.longitude if asset.longitude is not none else ''}}"></div><div class="full"><button type="button" class="btn green" id="editGps">◎ Detect current GPS</button> <span id="editGpsStatus" class="muted"></span></div><div><label>Condition score</label><input name="condition_score" type="number" min="0" max="100" value="{{asset.condition_score or 100}}"></div><div><label>Next maintenance</label><input name="next_maintenance_due" type="date" value="{{asset.next_maintenance_due}}"></div><div class="full upload"><label>Replace asset photo</label><input type="file" name="photo" accept="image/png,image/jpeg,image/webp"></div><div class="full"><label>Notes</label><textarea name="notes">{{asset.notes or ''}}</textarea></div><div class="full"><button class="btn primary">Save asset changes</button></div></div></form></div></div><div class="panel"><div class="panel-head"><h2>Asset GPS Location</h2><span class="tag">{{'GPS available' if asset.latitude and asset.longitude else 'GPS missing'}}</span></div><div id="map" class="map"></div><div class="body"><div class="muted">Coordinates are stored with the asset record: <b>{{asset.latitude or '—'}}, {{asset.longitude or '—'}}</b>.</div>{% if specs %}<div class="specs" style="margin-top:12px">{% for k,v in specs.items() %}<div class="spec"><small>{{k|replace('_',' ')|title}}</small>{{v}}</div>{% endfor %}</div>{% endif %}</div></div></div></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>const lat={{asset.latitude if asset.latitude is not none else 20.5937}},lon={{asset.longitude if asset.longitude is not none else 78.9629}};const map=L.map('map').setView([lat,lon],{{15 if asset.latitude and asset.longitude else 5}});L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors'}).addTo(map);{% if asset.latitude is not none and asset.longitude is not none %}L.marker([lat,lon]).addTo(map).bindPopup('<b>{{asset.name|e}}</b><br>{{asset.asset_uid|e}}').openPopup();{% endif %}</script></body></html>""", asset=asset, cat_info=cat_info, visual=visual, specs=specs, condition=calculate_condition_index(asset["condition_score"] or 100), maintenance_logs=maintenance_logs, linked_complaints=linked_complaints, available_complaints=available_complaints, image_url=image_url, **context)

@app.route("/admin/assets/<int:aid>/edit", methods=["POST"])
@login_required
def admin_asset_edit(aid):
    con = db()
    asset = con.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    if not asset:
        con.close()
        flash("Asset not found.", "danger")
        return redirect(url_for("admin_assets"))

    name = (request.form.get("name") or asset["name"]).strip()
    status = (request.form.get("status") or asset["status"]).strip()
    ward = (request.form.get("ward") or asset["ward"]).strip()
    village = (request.form.get("village") or asset["village"]).strip()
    location = (request.form.get("location") or asset["location"]).strip()
    notes = (request.form.get("notes") or "").strip()
    assigned_worker = (request.form.get("assigned_worker") or asset["assigned_worker"] or "").strip() or None
    next_maint = (request.form.get("next_maintenance_due") or asset["next_maintenance_due"]).strip()

    try:
        cond_score = max(0, min(100, int(request.form.get("condition_score") or asset["condition_score"] or 100)))
    except (TypeError, ValueError):
        cond_score = asset["condition_score"] or 100

    try:
        est_val = float(request.form.get("estimated_value") or asset["estimated_value"])
    except (TypeError, ValueError):
        est_val = asset["estimated_value"]
    lat, lon, _ = asset_coordinates_from_request(request, location)
    if lat is None or lon is None:
        lat, lon = asset["latitude"], asset["longitude"]
    new_photo = None
    try:
        new_photo = save_file("photo")
    except ValueError as exc:
        con.close()
        flash(str(exc), "danger")
        return redirect(url_for("admin_asset_detail", aid=aid))
    con.execute(
        """UPDATE assets SET
            name=?, status=?, ward=?, village=?, location=?, latitude=?, longitude=?,
            condition_score=?, estimated_value=?, assigned_worker=?,
            next_maintenance_due=?, notes=?, photo=COALESCE(?,photo), updated_at=?
            WHERE id=?""",
        (name, status, ward, village, location, lat, lon, cond_score, est_val, assigned_worker, next_maint, notes, new_photo, iso(), aid)
    )
    con.commit()
    con.close()
    flash(f"Asset {asset['asset_uid']} updated.", "success")
    return redirect(url_for("admin_asset_detail", aid=aid))

@app.route("/admin/assets/<int:aid>/maintenance", methods=["POST"])
@login_required
def admin_asset_maintenance(aid):
    m_type = (request.form.get("maintenance_type") or "Routine Inspection").strip()
    performed_by = (request.form.get("performed_by") or session.get("admin", "Field Crew")).strip()
    status_after = (request.form.get("status_after") or "Operational").strip()
    if status_after not in ASSET_STATUS_OPTIONS:
        status_after = "Operational"
    notes = (request.form.get("notes") or "Maintenance activity completed.").strip()
    
    try:
        cond_after = max(0, min(100, int(request.form.get("condition_after") or 100)))
    except (TypeError, ValueError):
        cond_after = 100

    try:
        cost = float(request.form.get("cost") or 0)
    except ValueError:
        cost = 0.0

    con = db()
    asset = con.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    if not asset:
        con.close()
        flash("Asset not found.", "danger")
        return redirect(url_for("admin_assets"))

    cat_info = ASSET_CATEGORIES.get(asset["category"], {})
    interval_days = cat_info.get("default_maintenance_days", 90)
    today_str = datetime.now().strftime("%Y-%m-%d")
    next_maint = (datetime.now() + timedelta(days=interval_days)).strftime("%Y-%m-%d")

    # Insert maintenance log
    con.execute(
        """INSERT INTO asset_maintenance_logs(asset_id, maintenance_type, performed_by, cost, notes, status_after, condition_after, performed_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (aid, m_type, performed_by, cost, notes, status_after, cond_after, iso())
    )

    # Update asset
    con.execute(
        """UPDATE assets SET
            status=?, condition_score=?, last_inspection_date=?,
            next_maintenance_due=?, updated_at=? WHERE id=?""",
        (status_after, cond_after, today_str, next_maint, iso(), aid)
    )
    con.commit()
    con.close()
    flash(f"Maintenance activity logged for {asset['asset_uid']}. Next inspection scheduled for {next_maint}.", "success")
    return redirect(url_for("admin_asset_detail", aid=aid))

@app.route("/admin/assets/<int:aid>/link-complaint", methods=["POST"])
@login_required
def admin_asset_link_complaint(aid):
    cid_raw = (request.form.get("complaint_id") or "").strip()
    if not cid_raw.isdigit():
        flash("Please select a valid complaint.", "warning")
        return redirect(url_for("admin_asset_detail", aid=aid))

    cid = int(cid_raw)
    con = db()
    asset = con.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    if not asset:
        con.close()
        flash("Asset not found.", "danger")
        return redirect(url_for("admin_assets"))
    complaint = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not complaint:
        con.close()
        flash("Complaint not found.", "warning")
        return redirect(url_for("admin_asset_detail", aid=aid))
    if complaint["department"] != asset["department"]:
        con.close()
        flash("Only complaints from the asset's department can be linked.", "warning")
        return redirect(url_for("admin_asset_detail", aid=aid))
    if complaint["asset_id"] is not None and int(complaint["asset_id"]) != aid:
        con.close()
        flash("This complaint is already linked to another asset.", "warning")
        return redirect(url_for("admin_asset_detail", aid=aid))
    con.execute("UPDATE complaints SET asset_id=?, updated_at=? WHERE id=?", (aid, iso(), cid))
    add_timeline(con, cid, "Asset Linked", f"Complaint officially associated with municipal asset {asset['asset_uid']} ({asset['name']}).")
    con.commit()
    flash(f"Complaint #{cid} linked to asset {asset['asset_uid']}.", "success")
    con.close()
    return redirect(url_for("admin_asset_detail", aid=aid))

@app.route("/admin/assets/analytics")
@login_required
def admin_asset_analytics():
    sync_escalations()
    con = db()
    all_assets = con.execute("SELECT * FROM assets ORDER BY id DESC").fetchall()
    context = admin_common_context(con)
    con.close()

    portfolio = summarize_asset_portfolio(all_assets, context["complaints"])
    critical_assets = [a for a in all_assets if (a["condition_score"] or 100) < 50 or a["status"] == "Critical / Defective"]
    replacement_needed = sum(float(a["replacement_cost"] or (float(a["estimated_value"] or 0) * 1.2)) for a in critical_assets)

    return render_template(
        "admin_asset_analytics.html",
        admin_active="assets",
        portfolio=portfolio,
        critical_assets=critical_assets,
        replacement_needed=replacement_needed,
        **context
    )

@app.route("/admin/assets/visual/<string:asset_uid>")
@login_required
def admin_asset_visual(asset_uid):
    con = db()
    asset = con.execute("SELECT * FROM assets WHERE asset_uid=?", (asset_uid,)).fetchone()
    con.close()
    if not asset:
        flash("Asset not found.", "warning")
        return redirect(url_for("admin_assets"))
    cat_info = ASSET_CATEGORIES.get(asset["category"], {})
    visual = asset_visual_svg(asset["category"], asset["name"], 260)
    return render_template_string("""<!doctype html><html><head><meta charset='utf-8'><title>Asset Visual · {{ asset.asset_uid }}</title><style>body{font-family:Inter,system-ui,sans-serif;background:#f1f5f9;padding:40px;display:flex;justify-content:center}.card{width:430px;background:#fff;border:1px solid #dbe4ee;border-radius:28px;padding:28px;text-align:center;box-shadow:0 18px 50px rgba(15,23,42,.12)}.eyebrow{font-size:11px;font-weight:900;letter-spacing:.12em;color:#2563eb;text-transform:uppercase}h1{font-size:22px;margin:8px 0 4px;color:#0f172a}.uid{font-weight:800;color:#64748b}.visual{margin:18px auto;width:260px;height:260px}.meta{text-align:left;border-top:1px solid #e2e8f0;margin-top:18px;padding-top:16px;color:#475569;line-height:1.8;font-size:13px}</style></head><body onload='window.print()'><div class='card'><div class='eyebrow'>Government Municipal Asset</div><h1>{{ asset.name }}</h1><div class='uid'>{{ asset.asset_uid }}</div><div class='visual'>{{ visual|safe }}</div><div class='meta'><b>Category:</b> {{ cat_info.get('name', asset.category) }}<br><b>Ward:</b> {{ asset.ward }}<br><b>Department:</b> {{ asset.department|upper }}<br><b>Location:</b> {{ asset.location }}</div></div></body></html>""", asset=asset, cat_info=cat_info, visual=visual)

@app.route("/admin/assets/qr/<string:asset_uid>")
@login_required
def admin_asset_qr(asset_uid):
    """Printable official asset badge compatibility route."""
    return admin_asset_visual(asset_uid)


@app.route("/admin/assets/export")
@login_required
def admin_assets_export():
    con = db()
    rows = con.execute("SELECT * FROM assets ORDER BY id ASC").fetchall()
    con.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Asset UID", "Name", "Category", "Department", "Ward", "Village",
        "Location", "Latitude", "Longitude", "Status", "Condition Score",
        "Valuation (INR)", "Replacement Cost", "Install Date", "Next Maintenance Due",
        "Assigned Crew", "Specifications"
    ])
    for r in rows:
        writer.writerow([
            r["asset_uid"], r["name"], r["category"], r["department"], r["ward"], r["village"],
            r["location"], r["latitude"], r["longitude"], r["status"], r["condition_score"],
            r["estimated_value"], r["replacement_cost"], r["install_date"], r["next_maintenance_due"],
            r["assigned_worker"], r["specifications"]
        ])
    payload = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    payload.seek(0)
    return send_file(
        payload,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"CivicOS_Asset_Ledger_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
    )

@app.route("/assets")
def public_assets():
    con = db()
    rows = con.execute("SELECT * FROM assets ORDER BY id DESC").fetchall()
    con.close()

    # Pre-render JSON payload for client map
    amenities_list = []
    for a in rows:
        cat_info = ASSET_CATEGORIES.get(a["category"], {})
        amenities_list.append({
            "id": a["id"],
            "asset_uid": a["asset_uid"],
            "name": a["name"],
            "category": a["category"],
            "categoryLabel": cat_info.get("name", a["category"]),
            "icon": cat_info.get("icon", "🏛️"),
            "ward": a["ward"],
            "village": a["village"],
            "location": a["location"],
            "status": a["status"],
            "condition_score": a["condition_score"],
            "latitude": a["latitude"],
            "longitude": a["longitude"]
        })

    return render_template(
        "public_assets.html",
        public_amenities=rows,
        public_amenities_json=json.dumps(amenities_list)
    )

@app.route("/asset/view/<string:asset_uid>")
def public_asset_view(asset_uid):
    con = db()
    asset = con.execute("SELECT * FROM assets WHERE asset_uid=?", (asset_uid,)).fetchone()
    con.close()
    if not asset:
        flash("Municipal asset record not found.", "warning")
        return redirect(url_for("public_assets"))

    cat_info = ASSET_CATEGORIES.get(asset["category"], {})
    condition = calculate_condition_index(asset["condition_score"] or 100)
    asset_visual = asset_visual_svg(asset["category"], asset["name"], 180)
    image_url = asset_image_url(asset)

    return render_template(
        "public_asset_view.html",
        asset=asset,
        cat_info=cat_info,
        condition=condition,
        qr_svg=asset_visual,
        asset_visual=asset_visual,
        image_url=image_url
    )

@app.route("/api/assets/map")
def api_assets_map():
    category = request.args.get("category", "all")
    con = db()
    sql = "SELECT * FROM assets"
    params = []
    if category != "all":
        sql += " WHERE category=?"
        params.append(category)
    rows = con.execute(sql, params).fetchall()
    con.close()

    markers = []
    for r in rows:
        cat_info = ASSET_CATEGORIES.get(r["category"], {})
        markers.append({
            "id": r["id"],
            "uid": r["asset_uid"],
            "name": r["name"],
            "category": r["category"],
            "icon": cat_info.get("icon", "🏛️"),
            "lat": r["latitude"],
            "lon": r["longitude"],
            "condition": r["condition_score"],
            "status": r["status"],
            "ward": r["ward"],
            "location": r["location"]
        })
    return jsonify(ok=True, markers=markers)



@app.after_request
def inject_finance_admin_link(response):
    """Keep the recovery snapshot current and expose Finance in the admin UI."""
    try:
        # Every successful request advances the last-known-good snapshot. This
        # means a blackout occurring between two user actions can recover to the
        # most recent committed state instead of a stale demo seed.
        if response.status_code < 500 and _integrity_ok(DB):
            create_recovery_snapshot()
    except Exception:
        pass
    try:
        if (session.get("admin") and response.status_code == 200
                and response.content_type and response.content_type.startswith("text/html")
                and request.path.startswith("/admin")
                and not request.path.startswith("/admin/finance")):
            body=response.get_data(as_text=True)
            if "</body>" in body and "CivicOSFinanceNav" not in body:
                link=(
                    '<a id="CivicOSFinanceNav" href="/admin/finance" '
                    'style="position:fixed;right:20px;bottom:20px;z-index:99999;'
                    'display:inline-flex;align-items:center;gap:8px;padding:11px 15px;'
                    'border-radius:999px;background:#0f172a;color:#fff;font:800 13px Inter,system-ui,sans-serif;'
                    'text-decoration:none;box-shadow:0 12px 28px rgba(15,23,42,.22)">'
                    '💰 Finance</a>'
                )
                body=body.replace("</body>",link+"</body>",1)
                response.set_data(body)
    except Exception:
        pass
    return response

init_db()
init_trust_db()
init_finance_db()
init_procurement_db()
init_contractors_db()
# Establish a known-good recovery point before the app starts serving traffic.
create_recovery_snapshot()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=os.environ.get('FLASK_DEBUG', '1') == '1')
