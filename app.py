import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "civicos.db")
UPLOAD = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD, exist_ok=True)

import os
from flask import Flask

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path=""
)
app.secret_key = "civicos-demo-secret"
app.config["UPLOAD_FOLDER"] = UPLOAD
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

DEPARTMENTS = {
    "water": "Water Department",
    "electricity": "Electricity Department",
    "road": "Roads & Public Works",
    "police": "Police / Safety",
    "health": "Health Department",
    "fire": "Fire Department",
}

CATEGORY_LABELS = {
    "auto": "Auto-detect with CivicOS",
    "water": "Water",
    "electricity": "Electricity",
    "road": "Road / Public Works",
    "safety": "Police / Safety",
    "health": "Health",
    "fire": "Fire",
}

WORKERS = [
    {"id": "WTR-01", "name": "Water Field Team 01", "department": "water"},
    {"id": "WTR-02", "name": "Water Field Team 02", "department": "water"},
    {"id": "ELE-01", "name": "Electricity Crew 01", "department": "electricity"},
    {"id": "RD-01", "name": "Road Repair Team 01", "department": "road"},
    {"id": "SAF-01", "name": "Safety Response Unit", "department": "police"},
    {"id": "HLT-01", "name": "Health Response Team", "department": "health"},
    {"id": "FIR-01", "name": "Fire Response Unit", "department": "fire"},
]

ROUTING_RULES = {
    "fire": ["fire", "smoke", "burn", "flame", "blast", "short circuit", "आग"],
    "health": ["medical", "ambulance", "health", "hospital", "sick", "disease", "garbage", "waste", "sanitation", "कचरा", "आरोग्य"],
    "police": ["women", "safety", "theft", "harassment", "fight", "crime", "accident", "danger", "help", "महिला", "चोरी"],
    "electricity": ["electric", "power", "light", "streetlight", "transformer", "wire", "spark", "pole", "लाईट", "वीज"],
    "water": ["water", "pipeline", "pipe", "leak", "tap", "drainage", "sewage", "पाणी", "गळती"],
    "road": ["road", "pothole", "bridge", "street", "footpath", "traffic", "रस्ता", "खड्डा"],
}

STATUS_ORDER = ["Pending", "Assigned", "In Progress", "Resolved"]


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


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
        return datetime.now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()


def smart_route(title, description, selected="auto"):
    text = f"{title} {description}".lower()
    if selected and selected != "auto":
        dept = "police" if selected == "safety" else selected
        return selected, dept, f"Citizen selected {CATEGORY_LABELS.get(selected, selected)}; CivicOS confirmed routing to {DEPARTMENTS.get(dept, dept)}."

    scores = {key: 0 for key in ROUTING_RULES}
    for dept, words in ROUTING_RULES.items():
        for word in words:
            if word in text:
                scores[dept] += 1
    dept = max(scores, key=scores.get)
    if scores[dept] == 0:
        dept = "road"
        reason = "No strong keyword detected; routed to Roads & Public Works as the default civic action team."
    else:
        matched = [w for w in ROUTING_RULES[dept] if w in text][:3]
        reason = f"Matched: {', '.join(matched)} → routed to {DEPARTMENTS[dept]}."
    category = "safety" if dept == "police" else dept
    return category, dept, reason


def service_priority(title, description, category, emergency=False, upvotes=0, escalated=False):
    text = f"{title} {description} {category}".lower()
    score = 25
    critical = ["emergency", "women", "fire", "medical", "ambulance", "spark", "danger", "accident", "help", "आग", "महिला"]
    high = ["leak", "pipeline", "pothole", "transformer", "hospital", "school", "garbage", "water", "road", "light"]
    score += sum(11 for k in critical if k in text)
    score += sum(6 for k in high if k in text)
    score += min(int(upvotes) * 2, 24)
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
    remaining = deadline - datetime.now()
    if remaining.total_seconds() < 0:
        return "Overdue"
    if remaining <= timedelta(hours=6):
        return "Due Soon"
    return "On Track"


def worker_label(worker_id):
    for w in WORKERS:
        if w["id"] == worker_id:
            return f"{w['id']} · {w['name']}"
    return worker_id or "Unassigned"


def workers_by_department():
    grouped = {k: [] for k in DEPARTMENTS}
    for w in WORKERS:
        grouped.setdefault(w["department"], []).append(w)
    return grouped


def save_file(field):
    f = request.files.get(field)
    if f and f.filename:
        name = datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(f.filename)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
        return name
    return None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            flash("Please login to access the Command Center.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        department TEXT NOT NULL,
        village TEXT NOT NULL,
        ward TEXT NOT NULL,
        location TEXT NOT NULL,
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
        created_at TEXT,
        updated_at TEXT,
        assigned_at TEXT,
        resolved_at TEXT,
        sla_deadline TEXT,
        sla_hours INTEGER,
        escalated INTEGER DEFAULT 0,
        routing_reason TEXT,
        duplicate_group TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS timeline(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER,
        step TEXT,
        note TEXT,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER,
        name TEXT,
        rating INTEGER,
        message TEXT,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")
    cur.execute("SELECT COUNT(*) c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", ("admin", "admin123", "admin"))
    cur.execute("SELECT COUNT(*) c FROM complaints")
    if cur.fetchone()["c"] == 0:
        seed(cur)
    con.commit()
    con.close()


def add_timeline(cur, cid, step, note, when=None):
    cur.execute("INSERT INTO timeline(complaint_id,step,note,created_at) VALUES(?,?,?,?)", (cid, step, note, iso(when)))


def insert_complaint(cur, *, title, description, category, department, village, ward, location, lat, lon, status="Pending", emergency=0, upvotes=0, before_photo=None, after_photo=None, worker=None, note=None, created_hours_ago=0):
    created = datetime.now() - timedelta(hours=created_hours_ago)
    priority = service_priority(title, description, category, bool(emergency), upvotes)
    hours = sla_hours(priority, bool(emergency))
    deadline = created + timedelta(hours=hours)
    assigned_at = iso(created + timedelta(hours=1)) if worker else None
    resolved_at = iso(created + timedelta(hours=min(hours, 4))) if status == "Resolved" else None
    escalated = int(status != "Resolved" and datetime.now() > deadline)
    reason = f"Demo seed: routed to {DEPARTMENTS.get(department, department)} based on issue type."
    cur.execute("""INSERT INTO complaints(title,description,category,department,village,ward,location,latitude,longitude,status,priority,emergency,upvotes,before_photo,after_photo,assigned_worker,admin_note,created_at,updated_at,assigned_at,resolved_at,sla_deadline,sla_hours,escalated,routing_reason,duplicate_group)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (title, description, category, department, village, ward, location, lat, lon, status, priority, emergency, upvotes, before_photo, after_photo, worker, note, iso(created), iso(), assigned_at, resolved_at, iso(deadline), hours, escalated, reason, title.lower()[:22]))
    cid = cur.lastrowid
    add_timeline(cur, cid, "Reported", "Citizen submitted complaint with location and photo evidence.", created)
    add_timeline(cur, cid, "Smart Department Routing", reason, created + timedelta(minutes=2))
    add_timeline(cur, cid, "SLA Assigned", f"Resolution SLA: {hours} hours.", created + timedelta(minutes=3))
    if worker:
        add_timeline(cur, cid, "Worker Assigned", f"Assigned to {worker_label(worker)}.", created + timedelta(hours=1))
    if status == "In Progress":
        add_timeline(cur, cid, "In Progress", note or "Field work started.", created + timedelta(hours=2))
    if escalated:
        add_timeline(cur, cid, "SLA Escalated", "Automatic escalation triggered because the SLA deadline passed.", deadline)
    if status == "Resolved":
        add_timeline(cur, cid, "Resolved", note or "Issue resolved with after-work proof.", parse_dt(resolved_at))
    return cid


def seed(cur):
    insert_complaint(cur, title="Pipeline leakage near ZP school", description="Water is continuously leaking and the road has become slippery.", category="water", department="water", village="Jamkhed", ward="Ward 2", location="ZP School Road", lat=18.733, lon=75.322, status="Assigned", upvotes=14, before_photo="water_before.png", worker="WTR-01", note="Inspection required", created_hours_ago=30)
    insert_complaint(cur, title="Transformer sparks near houses", description="Electric transformer is sparking near residential houses.", category="electricity", department="electricity", village="Karjat", ward="Ward 3", location="Market Road", lat=18.55, lon=75.00, status="In Progress", emergency=1, upvotes=18, before_photo="electric_before.png", worker="ELE-01", note="Power team reached the site", created_hours_ago=4)
    insert_complaint(cur, title="Large pothole on main road", description="Pothole is causing two-wheeler accidents near the bus stop.", category="road", department="road", village="Ashti", ward="Ward 5", location="Main Road", lat=19.38, lon=75.16, status="Assigned", upvotes=16, before_photo="road_before.png", worker="RD-01", note="Road repair team assigned", created_hours_ago=20)
    insert_complaint(cur, title="Medical emergency for senior citizen", description="Senior citizen needs ambulance support near health center.", category="health", department="health", village="Pathardi", ward="Ward 1", location="Health Center Road", lat=19.17, lon=75.17, status="Resolved", emergency=1, upvotes=7, before_photo="health_before.png", after_photo="health_after.png", worker="HLT-01", note="Ambulance support completed", created_hours_ago=9)
    insert_complaint(cur, title="Streetlight not working near temple", description="Streetlight failure is making the lane unsafe at night.", category="electricity", department="electricity", village="Jamkhed", ward="Ward 4", location="Temple Lane", lat=18.738, lon=75.319, status="Resolved", upvotes=5, before_photo="streetlight_before.png", after_photo="streetlight_after.png", worker="ELE-01", note="Streetlight repaired and verified", created_hours_ago=44)
    insert_complaint(cur, title="Fire risk near farm storage", description="Dry grass is burning near storage; smoke is spreading quickly.", category="fire", department="fire", village="Shrigonda", ward="Ward 6", location="Farm Storage Area", lat=18.62, lon=74.70, status="Pending", emergency=1, upvotes=11, before_photo="fire_before.png", worker="FIR-01", note="Fire response unit notified", created_hours_ago=8)
    insert_complaint(cur, title="Women safety alert near bus stand", description="Help needed near bus stand after harassment complaint.", category="safety", department="police", village="Jamkhed", ward="Ward 1", location="Central Bus Stand", lat=18.735, lon=75.314, status="Pending", emergency=1, upvotes=22, before_photo="safety_before.png", worker="SAF-01", note="Safety unit informed", created_hours_ago=2)
    insert_complaint(cur, title="Garbage near water tank", description="Garbage is creating smell and health risk near drinking water tank.", category="health", department="health", village="Jamkhed", ward="Ward 3", location="Water Tank Area", lat=18.731, lon=75.318, status="Pending", upvotes=9, before_photo="garbage_before.png", worker="HLT-01", note="Cleaning team pending", created_hours_ago=52)
    # Feedback for resolved complaints
    cur.execute("INSERT INTO feedback(complaint_id,name,rating,message,created_at) VALUES(?,?,?,?,?)", (4, "Asha", 5, "Emergency response was fast and clear.", iso(datetime.now() - timedelta(hours=3))))
    cur.execute("INSERT INTO feedback(complaint_id,name,rating,message,created_at) VALUES(?,?,?,?,?)", (5, "Ramesh", 4, "Tracking and after-photo proof made the process transparent.", iso(datetime.now() - timedelta(hours=8))))


def sync_escalations():
    con = db()
    cur = con.cursor()
    rows = cur.execute("SELECT * FROM complaints WHERE status!='Resolved' AND escalated=0").fetchall()
    changed = False
    for r in rows:
        if datetime.now() > parse_dt(r["sla_deadline"]):
            cur.execute("UPDATE complaints SET escalated=1, priority=?, updated_at=? WHERE id=?", (service_priority(r["title"], r["description"], r["category"], bool(r["emergency"]), r["upvotes"], True), iso(), r["id"]))
            add_timeline(cur, r["id"], "SLA Escalated", "Automatic escalation triggered because the SLA deadline passed.")
            changed = True
    if changed:
        con.commit()
    con.close()


def get_stats(con):
    rows = con.execute("SELECT * FROM complaints").fetchall()
    total = len(rows)
    pending = sum(1 for r in rows if r["status"] != "Resolved")
    resolved = sum(1 for r in rows if r["status"] == "Resolved")
    emergency = sum(1 for r in rows if r["emergency"])
    escalated = sum(1 for r in rows if r["escalated"] and r["status"] != "Resolved")
    feedback = con.execute("SELECT AVG(rating) avg_rating, COUNT(*) count_rating FROM feedback").fetchone()
    satisfaction = f"{feedback['avg_rating']:.1f}/5" if feedback and feedback["avg_rating"] else "—"
    return {"total": total, "pending": pending, "resolved": resolved, "emergency": emergency, "escalated": escalated, "satisfaction": satisfaction}


def calculate_department_performance(con):
    rows = con.execute("SELECT department, status, escalated FROM complaints").fetchall()
    data = []
    for dept, label in DEPARTMENTS.items():
        subset = [r for r in rows if r["department"] == dept]
        total = len(subset)
        resolved = sum(1 for r in subset if r["status"] == "Resolved")
        pending = total - resolved
        escalated = sum(1 for r in subset if r["escalated"] and r["status"] != "Resolved")
        rate = round((resolved / total) * 100) if total else 0
        data.append({"department": dept, "label": label, "total": total, "resolved": resolved, "pending": pending, "escalated": escalated, "rate": rate})
    return data


def calculate_ward_analytics(con):
    rows = con.execute("SELECT ward, status, escalated FROM complaints").fetchall()
    wards = sorted(set(r["ward"] for r in rows))
    data = []
    for ward in wards:
        subset = [r for r in rows if r["ward"] == ward]
        total = len(subset)
        resolved = sum(1 for r in subset if r["status"] == "Resolved")
        escalated = sum(1 for r in subset if r["escalated"] and r["status"] != "Resolved")
        data.append({"ward": ward, "total": total, "resolved": resolved, "pending": total - resolved, "escalated": escalated, "rate": round((resolved / total) * 100) if total else 0})
    return data


def calculate_worker_stats(con):
    rows = con.execute("SELECT assigned_worker, status, escalated, priority FROM complaints WHERE assigned_worker IS NOT NULL AND assigned_worker!=''").fetchall()
    data = []
    for w in WORKERS:
        subset = [r for r in rows if r["assigned_worker"] == w["id"]]
        total = len(subset)
        completed = sum(1 for r in subset if r["status"] == "Resolved")
        active = total - completed
        escalated = sum(1 for r in subset if r["escalated"] and r["status"] != "Resolved")
        high_priority = sum(1 for r in subset if r["priority"] >= 70 and r["status"] != "Resolved")
        rate = round((completed / total) * 100) if total else 0
        data.append({**w, "label": worker_label(w["id"]), "total": total, "completed": completed, "active": active, "escalated": escalated, "high_priority": high_priority, "rate": rate})
    return data


@app.context_processor
def inject_globals():
    return dict(
        departments=DEPARTMENTS,
        category_labels=CATEGORY_LABELS,
        workers=WORKERS,
        workers_by_dept=workers_by_department(),
        worker_label=worker_label,
        display_time=display_time,
        sla_label=sla_label,
    )


@app.route("/")
def index():
    sync_escalations()
    con = db()
    stats = get_stats(con)
    feedback = con.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 4").fetchall()
    recent = con.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 4").fetchall()
    con.close()
    return render_template("index.html", stats=stats, feedback=feedback, recent=recent)


@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "POST":
        title = request.form["title"].strip()
        desc = request.form["description"].strip()
        selected = request.form.get("category", "auto")
        category, dept, reason = smart_route(title, desc, selected)
        village = request.form["village"].strip()
        ward = request.form["ward"].strip()
        loc = request.form["location"].strip()
        lat = float(request.form.get("latitude") or 18.735)
        lon = float(request.form.get("longitude") or 75.314)
        photo = save_file("before_photo")
        con = db()
        dup = con.execute("SELECT id FROM complaints WHERE village=? AND ward=? AND category=? AND status!='Resolved'", (village, ward, category)).fetchone()
        priority = service_priority(title, desc, category, False, 0, bool(dup))
        hours = sla_hours(priority, False)
        created = datetime.now()
        con.execute("""INSERT INTO complaints(title,description,category,department,village,ward,location,latitude,longitude,priority,before_photo,citizen_name,phone,created_at,updated_at,sla_deadline,sla_hours,routing_reason,duplicate_group)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (title, desc, category, dept, village, ward, loc, lat, lon, priority, photo, request.form.get("citizen_name"), request.form.get("phone"), iso(created), iso(), iso(created + timedelta(hours=hours)), hours, reason, title.lower()[:22] if dup else None))
        cid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        add_timeline(con, cid, "Reported", "Citizen submitted complaint with location and photo evidence.", created)
        add_timeline(con, cid, "Smart Department Routing", reason, created + timedelta(minutes=1))
        add_timeline(con, cid, "SLA Assigned", f"Resolution SLA: {hours} hours based on service priority.", created + timedelta(minutes=2))
        if dup:
            add_timeline(con, cid, "Duplicate / Cluster Flag", "Similar open issue found in the same ward and category.", created + timedelta(minutes=3))
        con.commit()
        con.close()
        flash(f"Complaint submitted successfully. Tracking ID: {cid}. Routed to {DEPARTMENTS[dept]}.", "success")
        return redirect(url_for("track", cid=cid))
    return render_template("report.html")


@app.route("/sos", methods=["GET", "POST"])
def sos():
    if request.method == "POST":
        typ = request.form["type"]
        emergency_map = {"Women Safety": ("safety", "police"), "Medical Emergency": ("health", "health"), "Fire Emergency": ("fire", "fire")}
        category, dept = emergency_map.get(typ, ("safety", "police"))
        village = request.form["village"].strip()
        ward = request.form["ward"].strip()
        loc = request.form["location"].strip()
        lat = float(request.form.get("latitude") or 18.735)
        lon = float(request.form.get("longitude") or 75.314)
        created = datetime.now()
        priority = 100
        hours = sla_hours(priority, True)
        con = db()
        con.execute("""INSERT INTO complaints(title,description,category,department,village,ward,location,latitude,longitude,status,priority,emergency,assigned_worker,admin_note,created_at,updated_at,assigned_at,sla_deadline,sla_hours,routing_reason)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"{typ} Alert", "One-tap SOS generated by citizen.", category, dept, village, ward, loc, lat, lon, "Assigned", priority, 1, next((w["id"] for w in WORKERS if w["department"] == dept), None), "Automatic emergency escalation sent.", iso(created), iso(), iso(created), iso(created + timedelta(hours=hours)), hours, f"Emergency SOS routed directly to {DEPARTMENTS[dept]}."))
        cid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        add_timeline(con, cid, "Emergency Reported", "Citizen created SOS alert.", created)
        add_timeline(con, cid, "Smart Department Routing", f"Emergency SOS routed directly to {DEPARTMENTS[dept]}.", created + timedelta(minutes=1))
        add_timeline(con, cid, "Worker Assigned", "Emergency response team assigned automatically.", created + timedelta(minutes=2))
        add_timeline(con, cid, "SLA Assigned", f"Critical SLA: {hours} hours.", created + timedelta(minutes=3))
        con.commit()
        con.close()
        flash(f"Emergency alert sent. Tracking ID: {cid}.", "danger")
        return redirect(url_for("track", cid=cid))
    return render_template("emergency.html")


@app.route("/track")
def track():
    sync_escalations()
    cid = request.args.get("cid")
    comp = timeline = feedback = None
    if cid:
        con = db()
        comp = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        timeline = con.execute("SELECT * FROM timeline WHERE complaint_id=? ORDER BY id", (cid,)).fetchall()
        feedback = con.execute("SELECT * FROM feedback WHERE complaint_id=? ORDER BY id DESC", (cid,)).fetchall()
        con.close()
    return render_template("track.html", comp=comp, timeline=timeline or [], feedback=feedback or [])


@app.route("/upvote/<int:cid>", methods=["POST"])
def upvote(cid):
    con = db()
    row = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if row:
        ups = row["upvotes"] + 1
        priority = service_priority(row["title"], row["description"], row["category"], bool(row["emergency"]), ups, bool(row["escalated"]))
        con.execute("UPDATE complaints SET upvotes=?, priority=?, updated_at=? WHERE id=?", (ups, priority, iso(), cid))
        add_timeline(con, cid, "Community Upvote", f"Community upvotes increased to {ups}.")
        con.commit()
    con.close()
    return redirect(request.referrer or url_for("track", cid=cid))


@app.route("/feedback/<int:cid>", methods=["POST"])
def feedback(cid):
    con = db()
    exists = con.execute("SELECT id FROM complaints WHERE id=?", (cid,)).fetchone()
    if exists:
        con.execute("INSERT INTO feedback(complaint_id,name,rating,message,created_at) VALUES(?,?,?,?,?)", (cid, request.form.get("name") or "Citizen", int(request.form.get("rating") or 5), request.form.get("message") or "Satisfied with resolution.", iso()))
        add_timeline(con, cid, "Citizen Feedback", "Citizen submitted feedback after tracking/resolution.")
        con.commit()
        flash("Feedback submitted. Thank you.", "success")
    con.close()
    return redirect(url_for("track", cid=cid))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        con = db()
        user = con.execute("SELECT * FROM users WHERE username=? AND password=?", (request.form["username"], request.form["password"])).fetchone()
        con.close()
        if user:
            session["admin"] = user["username"]
            flash("Command Center login successful.", "success")
            return redirect(url_for("admin"))
        flash("Invalid username/password. Demo: admin / admin123", "danger")
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
    complaints = con.execute("SELECT * FROM complaints ORDER BY emergency DESC, escalated DESC, priority DESC, id DESC").fetchall()
    stats = get_stats(con)
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    worker_stats = calculate_worker_stats(con)
    con.close()
    return render_template("admin.html", complaints=complaints, stats=stats, dept_perf=dept_perf, ward_data=ward_data, worker_stats=worker_stats)


@app.route("/admin/update/<int:cid>", methods=["POST"])
@login_required
def update_complaint(cid):
    status = request.form.get("status")
    worker = request.form.get("assigned_worker")
    note = request.form.get("admin_note")
    after = save_file("after_photo")
    con = db()
    old = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not old:
        con.close()
        flash("Complaint not found.", "danger")
        return redirect(url_for("admin"))
    if worker and status == "Pending":
        status = "Assigned"
    if not worker and status == "Assigned":
        status = "Pending"
    resolved_at = iso() if status == "Resolved" else old["resolved_at"]
    assigned_at = old["assigned_at"] or (iso() if worker else None)
    escalated = old["escalated"]
    if status == "Resolved":
        escalated = 0
    params = [status, worker, note, iso(), assigned_at, resolved_at, escalated, cid]
    if after:
        con.execute("UPDATE complaints SET status=?, assigned_worker=?, admin_note=?, updated_at=?, assigned_at=?, resolved_at=?, escalated=?, after_photo=? WHERE id=?", (status, worker, note, iso(), assigned_at, resolved_at, escalated, after, cid))
    else:
        con.execute("UPDATE complaints SET status=?, assigned_worker=?, admin_note=?, updated_at=?, assigned_at=?, resolved_at=?, escalated=? WHERE id=?", params)
    if old["status"] != status:
        add_timeline(con, cid, status, note or f"Status updated to {status}.")
    if worker and old["assigned_worker"] != worker:
        add_timeline(con, cid, "Worker Assigned", f"Assigned to {worker_label(worker)}.")
    if after:
        add_timeline(con, cid, "After Photo Uploaded", "Field worker uploaded completion proof.")
    con.commit()
    con.close()
    flash("Complaint updated successfully.", "success")
    return redirect(request.referrer or url_for("admin"))


@app.route("/department/<dept>")
@login_required
def department(dept):
    sync_escalations()
    con = db()
    complaints = con.execute("SELECT * FROM complaints WHERE department=? ORDER BY escalated DESC, priority DESC, id DESC", (dept,)).fetchall()
    stats = {"total": len(complaints), "resolved": sum(1 for c in complaints if c["status"] == "Resolved"), "pending": sum(1 for c in complaints if c["status"] != "Resolved"), "escalated": sum(1 for c in complaints if c["escalated"] and c["status"] != "Resolved")}
    con.close()
    return render_template("department.html", dept=dept, title=DEPARTMENTS.get(dept, dept.title()), complaints=complaints, stats=stats)


@app.route("/workers")
@login_required
def workers_dashboard():
    sync_escalations()
    con = db()
    worker_stats = calculate_worker_stats(con)
    totals = {
        "workers": len(worker_stats),
        "active": sum(w["active"] for w in worker_stats),
        "completed": sum(w["completed"] for w in worker_stats),
        "escalated": sum(w["escalated"] for w in worker_stats),
    }
    con.close()
    return render_template("workers.html", worker_stats=worker_stats, totals=totals)


@app.route("/worker/<worker_id>")
@login_required
def worker_dashboard(worker_id):
    sync_escalations()
    con = db()
    worker = next((w for w in WORKERS if w["id"] == worker_id), None)
    tasks = con.execute("SELECT * FROM complaints WHERE assigned_worker=? ORDER BY escalated DESC, priority DESC, id DESC", (worker_id,)).fetchall()
    con.close()
    if not worker:
        flash("Worker not found.", "danger")
        return redirect(url_for("admin"))
    stats = {
        "total": len(tasks),
        "active": sum(1 for t in tasks if t["status"] != "Resolved"),
        "done": sum(1 for t in tasks if t["status"] == "Resolved"),
        "escalated": sum(1 for t in tasks if t["escalated"] and t["status"] != "Resolved"),
        "high_priority": sum(1 for t in tasks if t["priority"] >= 70 and t["status"] != "Resolved"),
    }
    return render_template("worker.html", worker=worker, tasks=tasks, stats=stats)


@app.route("/worker/update/<int:cid>", methods=["POST"])
@login_required
def worker_update(cid):
    status = request.form.get("status")
    note = request.form.get("admin_note")
    after = save_file("after_photo")
    con = db()
    old = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if old:
        resolved_at = iso() if status == "Resolved" else old["resolved_at"]
        if after:
            con.execute("UPDATE complaints SET status=?, admin_note=?, after_photo=?, updated_at=?, resolved_at=?, escalated=? WHERE id=?", (status, note, after, iso(), resolved_at, 0 if status == "Resolved" else old["escalated"], cid))
        else:
            con.execute("UPDATE complaints SET status=?, admin_note=?, updated_at=?, resolved_at=?, escalated=? WHERE id=?", (status, note, iso(), resolved_at, 0 if status == "Resolved" else old["escalated"], cid))
        if old["status"] != status:
            add_timeline(con, cid, status, note or f"Worker updated status to {status}.")
        if after:
            add_timeline(con, cid, "After Photo Uploaded", "Worker uploaded before/after resolution proof.")
        con.commit()
        flash("Task updated.", "success")
    con.close()
    return redirect(request.referrer or url_for("admin"))


@app.route("/complaint/<int:cid>")
def complaint_detail(cid):
    sync_escalations()
    con = db()
    comp = con.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    timeline = con.execute("SELECT * FROM timeline WHERE complaint_id=? ORDER BY id", (cid,)).fetchall()
    feedback = con.execute("SELECT * FROM feedback WHERE complaint_id=? ORDER BY id DESC", (cid,)).fetchall()
    con.close()
    return render_template("complaint_detail.html", comp=comp, timeline=timeline, feedback=feedback)


@app.route("/transparency")
def transparency():
    sync_escalations()
    con = db()
    complaints = con.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 20").fetchall()
    stats = get_stats(con)
    dept_perf = calculate_department_performance(con)
    ward_data = calculate_ward_analytics(con)
    con.close()
    return render_template("transparency.html", complaints=complaints, stats=stats, dept_perf=dept_perf, ward_data=ward_data)


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
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
        markers.append({
            "id": r["id"], "title": r["title"], "lat": r["latitude"], "lon": r["longitude"], "priority": r["priority"],
            "village": r["village"], "ward": r["ward"], "department": r["department"], "departmentLabel": DEPARTMENTS.get(r["department"], r["department"]),
            "status": r["status"], "escalated": bool(r["escalated"]), "category": r["category"], "sla": "Escalated" if r["escalated"] else "On Track"
        })
    return jsonify(status=status, departmentPerformance=dept_perf, wardAnalytics=ward_data, workers=worker_stats, markers=markers)


# Initialize automatically for beginner-friendly execution.
init_db()

if __name__ == "__main__":
    app.run(debug=True)
