import csv
import io
import json
import os
import re
import smtplib
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
    send_file,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

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
DB = os.path.join(BASE_DIR, "civicos.db")
UPLOAD = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-before-production")
app.config["UPLOAD_FOLDER"] = UPLOAD
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

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


def db():
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


def public_tracking_url(cid):
    base = (os.environ.get("CIVICOS_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        return f"{base}{url_for('track', cid=cid)}"
    return url_for("track", cid=cid, _external=True)


def send_optional_sms(phone, message):
    api_key = (os.environ.get("FAST2SMS_API_KEY") or "").strip()
    if not api_key:
        return False, "FAST2SMS_API_KEY is not configured"
    number = normalize_phone(phone)
    if len(number) == 12 and number.startswith("91"):
        number = number[-10:]
    if len(number) != 10:
        return False, "Fast2SMS requires a valid 10-digit Indian mobile number"
    payload = urllib.parse.urlencode({"route":"q","message":message,"numbers":number,"sms_details":"1"}).encode("utf-8")
    req = urllib.request.Request("https://www.fast2sms.com/dev/bulkV2", data=payload, headers={"Authorization":api_key,"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json","User-Agent":"CivicOS/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            body=response.read().decode("utf-8", errors="replace")
        try: data=json.loads(body)
        except json.JSONDecodeError: data={}
        return bool(data.get("return")) if isinstance(data,dict) else False, body[:500]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        app.logger.warning("Citizen SMS failed: %s", exc)
        return False, str(exc)


def send_complaint_registered_sms(cid, phone):
    return send_optional_sms(phone, f"CivicOS: Your complaint #{cid} has been registered successfully. Track live status: {public_tracking_url(cid)}")


def send_complaint_update_sms(cid, phone, status, details=""):
    message=f"CivicOS: Complaint #{cid} status is now {status}."
    clean=re.sub(r"\s+", " ", details).strip() if details else ""
    if clean: message += f" {clean[:80]}"
    message += f" Track: {public_tracking_url(cid)}"
    return send_optional_sms(phone, message)


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
    sql = "SELECT * FROM complaints WHERE assigned_worker=? AND status!='Resolved'"
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


def select_best_worker(con, department, required_skill=None, exclude_complaint_id=None):
    """Select only an idle team. This enforces the one-active-task policy."""
    candidates = []
    for worker in WORKERS:
        if worker["department"] != department or not worker.get("available", True):
            continue
        if worker_active_task(con, worker["id"], exclude_complaint_id):
            continue
        candidates.append((worker_skill_score(worker, required_skill), worker["id"], worker))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def save_file(field):
    file = request.files.get(field)
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Only PNG, JPG, JPEG and WEBP images are supported.")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", filename.rsplit(".", 1)[0])[:50] or "image"
    stored = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{stem}.{extension}"
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


def send_optional_email(cid, subject, message):
    """Best-effort email. In-app/browser notifications work even without SMTP."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return False
    con = db()
    row = con.execute("SELECT email FROM complaints WHERE id=?", (cid,)).fetchone()
    con.close()
    if not row or not row["email"]:
        return False

    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", username or "civicos@example.com")
    use_tls = os.environ.get("SMTP_USE_TLS", "1") != "0"
    mail = EmailMessage()
    mail["From"] = sender
    mail["To"] = row["email"]
    mail["Subject"] = subject
    mail.set_content(message)
    try:
        with smtplib.SMTP(host, port, timeout=6) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(mail)
        return True
    except (OSError, smtplib.SMTPException):
        return False


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
        WHERE assigned_worker IS NOT NULL AND TRIM(assigned_worker)!='' AND status!='Resolved'
        GROUP BY assigned_worker
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for duplicate in duplicates:
        worker_id = duplicate["assigned_worker"]
        rows = con.execute(
            "SELECT * FROM complaints WHERE assigned_worker=? AND status!='Resolved'",
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
        """CREATE TABLE IF NOT EXISTS system_settings(
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT
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

    # Fill backward-compatible fields in existing databases.
    con.execute("UPDATE complaints SET address=location WHERE address IS NULL OR TRIM(address)=''")
    rows = con.execute("SELECT id,phone,phone_key FROM complaints").fetchall()
    for row in rows:
        normalized = normalize_phone(row["phone"])
        if normalized and row["phone_key"] != normalized:
            con.execute("UPDATE complaints SET phone_key=? WHERE id=?", (normalized, row["id"]))

    if con.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0:
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
    # Database-level guarantee: a worker/team can have only one unresolved task.
    con.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_one_active_task
           ON complaints(assigned_worker)
           WHERE assigned_worker IS NOT NULL AND TRIM(assigned_worker)!='' AND status!='Resolved'"""
    )
    con.commit()
    con.close()


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
        active_rows = [task for task in tasks if task["status"] != "Resolved"]
        completed = sum(1 for task in tasks if task["status"] == "Resolved")
        current = active_rows[0] if active_rows else None
        output.append(
            {
                **worker,
                "total": len(tasks),
                "active": len(active_rows),
                "completed": completed,
                "escalated": sum(1 for task in active_rows if task["escalated"]),
                "high_priority": sum(1 for task in active_rows if task["priority"] >= 70),
                "rate": round((completed / len(tasks)) * 100) if tasks else 0,
                "busy": bool(current),
                "current_task_id": current["id"] if current else None,
                "current_task_title": current["title"] if current else None,
                "current_task_status": current["status"] if current else None,
            }
        )
    return output


def get_setting(con, key, default=""):
    row = con.execute("SELECT setting_value FROM system_settings WHERE setting_key=?", (key,)).fetchone()
    return row["setting_value"] if row and row["setting_value"] is not None else default


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
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            flash(t("login_required"), "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


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
    }


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
    recent = con.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 6").fetchall()
    con.close()
    return render_template("index.html", stats=stats, feedback=feedback_rows, recent=recent)


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        citizen_name = (request.form.get("citizen_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        email = (request.form.get("email") or "").strip()
        village = (request.form.get("village") or "").strip()
        ward = (request.form.get("ward") or "").strip()
        location = (request.form.get("location") or "").strip()
        selected = request.form.get("category", "auto")

        if not all([title, description, citizen_name, phone, village, ward]):
            flash("Please complete all required complaint and contact fields.", "danger")
            return render_template("report.html")
        if not valid_phone(phone):
            flash("Enter a valid phone number so your complaint ID can be recovered later.", "danger")
            return render_template("report.html")
        if not valid_email(email):
            flash("Enter a valid email address or leave the email field empty.", "danger")
            return render_template("report.html")

        try:
            category, department, required_skill, routing_reason = smart_route(title, description, selected)
        except ValueError:
            flash("Invalid complaint category.", "danger")
            return render_template("report.html")

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
                return render_template("report.html")
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                flash(t("invalid_location_coordinates"), "danger")
                return render_template("report.html")
            if not detected_address:
                detected_address = f"GPS location: {latitude:.6f}, {longitude:.6f}"
            if location_confirmed != "true":
                flash(t("confirm_detected_address"), "warning")
                return render_template("report.html")
            address = detected_address
            if not location:
                location = address
        else:
            latitude = None
            longitude = None
            address = location

        if not location:
            flash(t("enter_location_or_gps"), "danger")
            return render_template("report.html")

        try:
            before_photo = save_file("before_photo")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("report.html")

        con = db()
        duplicate = con.execute(
            "SELECT id FROM complaints WHERE village=? AND ward=? AND category=? AND status!='Resolved' LIMIT 1",
            (village, ward, category),
        ).fetchone()
        priority = service_priority(title, description, category, False, 0, bool(duplicate))
        hours = sla_hours(priority, False)
        created = datetime.now()
        worker = select_best_worker(con, department, required_skill)
        assigned_worker = worker["id"] if worker else None
        status = "Assigned" if worker else "Pending"
        assigned_at = iso(created) if worker else None

        con.execute(
            """INSERT INTO complaints(
                title,description,category,department,village,ward,location,address,
                latitude,longitude,status,priority,emergency,upvotes,before_photo,
                assigned_worker,citizen_name,phone,phone_key,email,required_skill,
                created_at,updated_at,assigned_at,sla_deadline,sla_hours,routing_reason,duplicate_group
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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

        add_timeline(
            con,
            cid,
            "Location Confirmed" if gps_used else "Location Added",
            f"Complaint location: {address}",
            created,
        )
        add_timeline(con, cid, "Reported", "Citizen submitted the issue with contact and location information.", created + timedelta(seconds=1))
        add_timeline(con, cid, "AI Analysis", f"Detected category: {category_label(category)}. Required skill: {required_skill}.", created + timedelta(minutes=1))
        add_timeline(con, cid, "Smart Department Routing", routing_reason, created + timedelta(minutes=2))
        if worker:
            add_timeline(con, cid, "Worker Assigned", f"Automatically assigned to {worker_label(worker['id'])}. One-task policy verified.", created + timedelta(minutes=3))
        else:
            add_timeline(con, cid, "Queued for Worker", "All suitable field teams are currently busy. The complaint is safely queued by priority.", created + timedelta(minutes=3))
        add_timeline(con, cid, "SLA Assigned", f"Resolution SLA: {hours} hours based on service priority.", created + timedelta(minutes=4))
        if duplicate:
            add_timeline(con, cid, "Duplicate / Cluster Flag", "A similar open issue exists in the same ward and category.", created + timedelta(minutes=5))

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
        sms_ok, sms_detail = send_complaint_registered_sms(cid, phone)
        if not sms_ok:
            app.logger.warning("Registration SMS not sent for complaint #%s: %s", cid, sms_detail)
        flash(f"Complaint submitted successfully. Your tracking ID is #{cid}. Save it, or recover it later using your name and phone number.", "success")
        return redirect(url_for("track", cid=cid))

    return render_template("report.html")


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
        worker = select_best_worker(con, department, required_skill)
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
            else:
                flash(t("complaint_not_found"), "warning")
            con.close()
    return render_template("track.html", comp=comp, timeline=timeline, feedback=feedback_rows, notifications=notifications)


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
def upvote(cid):
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if row:
        upvotes = int(row["upvotes"] or 0) + 1
        priority = service_priority(row["title"], row["description"], row["category"], bool(row["emergency"]), upvotes, bool(row["escalated"]))
        con.execute("UPDATE complaints SET upvotes=?, priority=?, updated_at=? WHERE id=?", (upvotes, priority, iso(), cid))
        add_timeline(con, cid, "Community Upvote", f"Community upvotes increased to {upvotes}.")
        con.commit()
    con.close()
    return redirect(request.referrer or url_for("track", cid=cid))


@app.route("/feedback/<int:cid>", methods=["POST"])
def feedback(cid):
    con = db()
    exists = con.execute("SELECT id FROM complaints WHERE id=?", (cid,)).fetchone()
    if exists:
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
        user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
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
            session["admin"] = username
            flash(t("command_center_login_success"), "success")
            destination = request.args.get("next")
            return redirect(destination if destination and destination.startswith("/") else url_for("admin"))
        flash(t("invalid_login"), "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("admin", None)
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
        con.commit()
        flash("Command Center settings updated.", "success")
    context = admin_common_context(con)
    con.close()
    return render_template("admin_settings.html", admin_active="settings", **context)


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

    if worker_id and status == "Pending":
        status = "Assigned"
    if not worker_id and status in {"Assigned", "In Progress"}:
        status = "Pending"
    if status == "In Progress" and not worker_id:
        con.close()
        flash("Assign a field team before starting work.", "warning")
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
    if changes:
        update_text = " ".join(changes)
        send_optional_email(cid, f"CivicOS complaint #{cid} updated", update_text)
        sms_ok, sms_detail = send_complaint_update_sms(cid, old["phone"], status, update_text)
        if not sms_ok:
            app.logger.warning("Status SMS not sent for complaint #%s: %s", cid, sms_detail)
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
def workers_dashboard():
    sync_escalations()
    con = db()
    worker_stats = calculate_worker_stats(con)
    totals = {
        "workers": len(worker_stats),
        "active": sum(item["active"] for item in worker_stats),
        "completed": sum(item["completed"] for item in worker_stats),
        "escalated": sum(item["escalated"] for item in worker_stats),
        "available": sum(1 for item in worker_stats if not item["busy"]),
    }
    con.close()
    return render_template("workers.html", worker_stats=worker_stats, totals=totals)


@app.route("/worker/<worker_id>")
def worker_dashboard(worker_id):
    sync_escalations()
    worker = get_worker(worker_id)
    if not worker:
        flash(t("worker_not_found"), "danger")
        return redirect(url_for("workers_dashboard"))
    con = db()
    tasks = con.execute(
        "SELECT * FROM complaints WHERE assigned_worker=? ORDER BY CASE WHEN status='Resolved' THEN 1 ELSE 0 END, id DESC",
        (worker_id,),
    ).fetchall()
    con.close()
    active = [task for task in tasks if task["status"] != "Resolved"]
    stats = {
        "total": len(tasks),
        "active": len(active),
        "done": sum(1 for task in tasks if task["status"] == "Resolved"),
        "escalated": sum(1 for task in active if task["escalated"]),
        "high_priority": sum(1 for task in active if task["priority"] >= 70),
        "available": not bool(active),
    }
    return render_template("worker.html", worker=worker, tasks=tasks, stats=stats, current_task=active[0] if active else None)


@app.route("/worker/update/<int:cid>", methods=["POST"])
def worker_update(cid):
    status = request.form.get("status") or "In Progress"
    if status not in {"Assigned", "In Progress", "Resolved"}:
        flash("Invalid worker status update.", "warning")
        return redirect(request.referrer or url_for("workers_dashboard"))
    note = (request.form.get("admin_note") or "").strip()
    try:
        after_photo = save_file("after_photo")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(request.referrer or url_for("workers_dashboard"))

    con = db()
    old = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    submitted_worker = (request.form.get("worker_id") or "").strip()
    demo_worker_access = os.environ.get("CIVICOS_DEMO_WORKER_ACCESS", "1") == "1"
    if not session.get("admin") and not demo_worker_access:
        con.close()
        flash("Worker updates require worker authentication in production mode.", "warning")
        return redirect(url_for("login", next=request.referrer or url_for("workers_dashboard")))
    if old and not session.get("admin") and submitted_worker != (old["assigned_worker"] or ""):
        con.close()
        flash("This field-team dashboard can update only its own assigned task.", "danger")
        return redirect(url_for("workers_dashboard"))
    if not old or not old["assigned_worker"]:
        con.close()
        flash("This task is not assigned to a field team.", "warning")
        return redirect(request.referrer or url_for("workers_dashboard"))
    if old["status"] == "Resolved":
        con.close()
        flash("Resolved tasks are read-only. Reassign a new complaint instead of reopening a completed task from the worker dashboard.", "warning")
        return redirect(request.referrer or url_for("worker_dashboard", worker_id=old["assigned_worker"]))

    resolved_at = iso() if status == "Resolved" else old["resolved_at"]
    escalated = 0 if status == "Resolved" else old["escalated"]
    if after_photo:
        con.execute(
            "UPDATE complaints SET status=?,admin_note=?,after_photo=?,updated_at=?,resolved_at=?,escalated=? WHERE id=?",
            (status, note, after_photo, iso(), resolved_at, escalated, cid),
        )
    else:
        con.execute(
            "UPDATE complaints SET status=?,admin_note=?,updated_at=?,resolved_at=?,escalated=? WHERE id=?",
            (status, note, iso(), resolved_at, escalated, cid),
        )

    changes = []
    if old["status"] != status:
        add_timeline(con, cid, status, note or f"Field team updated status to {status}.")
        changes.append(f"Field work status changed to {status}.")
    if after_photo:
        add_timeline(con, cid, "After Photo Uploaded", "Field team uploaded before/after resolution proof.")
        changes.append("After-work proof was uploaded.")
    if note and note != (old["admin_note"] or ""):
        changes.append(f"Field update: {note}")
    if changes:
        create_notification(con, cid, "Field team update", " ".join(changes), "success" if status == "Resolved" else "info")

    if status == "Resolved":
        assign_next_pending(con, old["assigned_worker"])
    con.commit()
    con.close()
    if changes:
        send_optional_email(cid, f"CivicOS complaint #{cid} field update", " ".join(changes))
    flash(t("task_updated"), "success")
    return redirect(request.referrer or url_for("workers_dashboard"))


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
    con.close()
    if not comp:
        return render_template("complaint_detail.html", comp=None, timeline=[], feedback=[]), 404
    return render_template(
        "complaint_detail.html",
        comp=comp,
        timeline=timeline,
        feedback=feedback_rows,
        notifications=notifications,
        worker_states=worker_states,
    )


@app.route("/transparency")
def transparency():
    sync_escalations()
    con = db()
    complaints = con.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 30").fetchall()
    stats = get_stats(con)
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    con.close()
    return render_template("transparency.html", complaints=complaints, stats=stats, dept_perf=dept_perf, ward_data=ward_data)


@app.route("/api/reverse-geocode")
def reverse_geocode_api():
    """Convert GPS coordinates to the fullest human-readable address available.

    Nominatim is the primary provider. Photon is a no-key fallback so a temporary
    Nominatim failure does not make the UI fall back immediately to raw lat/lon.
    """
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except ValueError:
        return jsonify(ok=False, error="Invalid coordinates"), 400

    def clean_parts(values):
        parts = []
        for value in values:
            value = str(value or "").strip()
            if value and value not in parts:
                parts.append(value)
        return parts

    headers = {
        "User-Agent": "CivicOS-Hackathon/1.1 (reverse-geocoding for civic complaint demo)",
        "Accept": "application/json",
        "Accept-Language": "en",
    }

    # 1) Primary: OpenStreetMap Nominatim. display_name is usually the fullest
    # address, so prefer it instead of rebuilding a shorter address ourselves.
    query = urllib.parse.urlencode({
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "addressdetails": 1,
        "namedetails": 1,
        "extratags": 1,
        "zoom": 18,
        "accept-language": "en",
    })
    try:
        req = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/reverse?{query}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))

        address = data.get("address", {}) or {}
        display_name = str(data.get("display_name") or "").strip()
        built = ", ".join(clean_parts([
            address.get("house_number"), address.get("building"), address.get("amenity"),
            address.get("road"), address.get("pedestrian"), address.get("neighbourhood"),
            address.get("suburb"), address.get("village"), address.get("town"),
            address.get("city"), address.get("city_district"), address.get("county"),
            address.get("state_district"), address.get("state"), address.get("postcode"),
            address.get("country"),
        ]))
        exact_address = display_name or built
        if exact_address:
            locality = next((str(address.get(k) or "").strip() for k in
                             ("neighbourhood", "suburb", "village", "town", "city", "county")
                             if str(address.get(k) or "").strip()), "Live location")
            district = next((str(address.get(k) or "").strip() for k in
                             ("city_district", "state_district", "county")
                             if str(address.get(k) or "").strip() and str(address.get(k) or "").strip() != locality), "")
            short_label = f"{locality}, {district}" if district else locality
            return jsonify(
                ok=True,
                provider="nominatim",
                display_name=exact_address,
                exact_address=exact_address,
                short_label=short_label,
                coordinates={"lat": round(lat, 7), "lon": round(lon, 7)},
                address=address,
            )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        pass

    # 2) Fallback: Photon (also based on OpenStreetMap data, no API key required).
    try:
        photon_query = urllib.parse.urlencode({"lat": lat, "lon": lon})
        req = urllib.request.Request(
            f"https://photon.komoot.io/reverse?{photon_query}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        features = data.get("features") or []
        props = (features[0].get("properties") or {}) if features else {}
        parts = clean_parts([
            props.get("name"), props.get("housenumber"), props.get("street"),
            props.get("district"), props.get("locality"), props.get("city"),
            props.get("county"), props.get("state"), props.get("postcode"),
            props.get("country"),
        ])
        exact_address = ", ".join(parts)
        if exact_address:
            locality = next((str(props.get(k) or "").strip() for k in
                             ("district", "locality", "city", "county") if str(props.get(k) or "").strip()), "Live location")
            state = str(props.get("state") or "").strip()
            short_label = f"{locality}, {state}" if state and state != locality else locality
            return jsonify(
                ok=True,
                provider="photon",
                display_name=exact_address,
                exact_address=exact_address,
                short_label=short_label,
                coordinates={"lat": round(lat, 7), "lon": round(lon, 7)},
                address=props,
            )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        pass

    # Do NOT pretend coordinates are a successful human-readable address.
    # The frontend can now clearly show an address-service failure instead.
    return jsonify(
        ok=False,
        error="Reverse geocoding providers are temporarily unavailable",
        coordinates={"lat": round(lat, 7), "lon": round(lon, 7)},
        offline=True,
    ), 503


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
    rows = con.execute("SELECT * FROM complaints").fetchall()
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


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "1") == "1")
