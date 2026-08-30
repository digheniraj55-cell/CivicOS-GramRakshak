"""CivicOS configuration kept separate from route/business logic.

Edit departments, field teams, skills, routing keywords, status order and upload
extensions here when the project grows.
"""

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

# Keep worker configuration in one place so teams/skills are easy to change later.
WORKERS = [
    {
        "id": "WTR-01",
        "name": "Water Field Team 01",
        "department": "water",
        "skills": ["pipeline", "leakage", "drainage", "water supply"],
        "available": True,
    },
    {
        "id": "WTR-02",
        "name": "Water Field Team 02",
        "department": "water",
        "skills": ["pump", "pipeline", "tap", "water supply"],
        "available": True,
    },
    {
        "id": "ELE-01",
        "name": "Electricity Crew 01",
        "department": "electricity",
        "skills": ["transformer", "wiring", "streetlight", "power"],
        "available": True,
    },
    {
        "id": "RD-01",
        "name": "Road Repair Team 01",
        "department": "road",
        "skills": ["pothole", "road", "footpath", "bridge"],
        "available": True,
    },
    {
        "id": "SAF-01",
        "name": "Safety Response Unit",
        "department": "police",
        "skills": ["women safety", "crime", "accident", "public safety"],
        "available": True,
    },
    {
        "id": "HLT-01",
        "name": "Health Response Team",
        "department": "health",
        "skills": ["medical", "ambulance", "sanitation", "waste"],
        "available": True,
    },
    {
        "id": "FIR-01",
        "name": "Fire Response Unit",
        "department": "fire",
        "skills": ["fire", "smoke", "rescue", "emergency"],
        "available": True,
    },
    {
        "id": "ELE-02",
        "name": "Electricity Crew 02 · Reserve",
        "department": "electricity",
        "skills": ["transformer", "wiring", "streetlight", "power", "emergency restoration"],
        "available": True,
    },
    {
        "id": "RD-02",
        "name": "Road Repair Team 02 · Reserve",
        "department": "road",
        "skills": ["pothole", "road", "footpath", "drain edge", "emergency access"],
        "available": True,
    },
    {
        "id": "SAF-02",
        "name": "Safety Response Unit 02 · Reserve",
        "department": "police",
        "skills": ["women safety", "crime", "accident", "crowd", "public safety"],
        "available": True,
    },
    {
        "id": "HLT-02",
        "name": "Health Response Team 02 · Reserve",
        "department": "health",
        "skills": ["medical", "ambulance", "sanitation", "waste", "outbreak"],
        "available": True,
    },
    {
        "id": "FIR-02",
        "name": "Fire Response Unit 02 · Reserve",
        "department": "fire",
        "skills": ["fire", "smoke", "rescue", "evacuation", "emergency"],
        "available": True,
    },
]

ROUTING_RULES = {
    "fire": ["fire", "smoke", "burn", "flame", "blast", "short circuit", "आग"],
    "health": [
        "medical",
        "ambulance",
        "health",
        "hospital",
        "sick",
        "disease",
        "garbage",
        "waste",
        "sanitation",
        "कचरा",
        "आरोग्य",
    ],
    "police": [
        "women",
        "safety",
        "theft",
        "harassment",
        "fight",
        "crime",
        "accident",
        "danger",
        "help",
        "महिला",
        "चोरी",
    ],
    "electricity": [
        "electric",
        "power",
        "light",
        "streetlight",
        "transformer",
        "wire",
        "spark",
        "pole",
        "लाईट",
        "वीज",
    ],
    "water": [
        "water",
        "pipeline",
        "pipe",
        "leak",
        "tap",
        "drainage",
        "sewage",
        "पाणी",
        "गळती",
    ],
    "road": ["road", "pothole", "bridge", "street", "footpath", "traffic", "रस्ता", "खड्डा"],
}

STATUS_ORDER = ["Pending", "Assigned", "In Progress", "Awaiting Admin Verification", "Resolved"]
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
