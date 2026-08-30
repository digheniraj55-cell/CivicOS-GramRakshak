"""CivicOS intelligence engines.

Hackathon-ready, deterministic decision-support logic built entirely on top of the
existing CivicOS complaint database. The calculations are deliberately explainable:
judges can see why a score or recommendation exists instead of being asked to trust
an opaque AI output.

This module does not replace the operational workflow. It reasons over it:
Civic Memory -> root-cause clues -> risk/impact -> optimization -> prevention.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Iterable
import os

CATEGORY_COST = {
    "water": 85000,
    "electricity": 70000,
    "road": 125000,
    "safety": 45000,
    "health": 55000,
    "fire": 65000,
}

CATEGORY_CASCADE = {
    "water": ["Water leakage", "Soil weakening", "Road deterioration", "Drain obstruction", "Waterlogging"],
    "road": ["Road damage", "Traffic slowdown", "Emergency-route delay", "School/Hospital access impact"],
    "electricity": ["Electrical fault", "Street blackout", "Public safety risk", "Fire risk"],
    "health": ["Waste / sanitation issue", "Vector risk", "Public health exposure", "Neighbouring-area spread"],
    "safety": ["Safety incident", "Reduced public access", "Emergency response demand", "Community risk"],
    "fire": ["Fire hazard", "Property exposure", "Power / traffic disruption", "Emergency evacuation demand"],
}

ROOT_CAUSE_RULES = [
    ({"water", "road"}, "Possible underground water leakage weakening the road base", "Inspect the water line before resurfacing the road."),
    ({"water", "health", "road"}, "Possible drainage / water-system failure creating sanitation and road damage", "Run a joint drainage, water and road inspection."),
    ({"electricity", "fire"}, "Possible electrical fault increasing local fire risk", "Isolate electrical risk and inspect the feeder/transformer before routine repair."),
    ({"health", "road"}, "Possible drainage or waste-management failure affecting the road corridor", "Inspect drainage and sanitation conditions before repeated road work."),
    ({"safety", "electricity"}, "Low-light public-space risk may be contributing to safety incidents", "Coordinate street-light restoration with a public-safety patrol."),
]


def value(row: Any, key: str, default: Any = None) -> Any:
    try:
        val = row[key]
    except Exception:
        val = getattr(row, key, default)
    return default if val is None else val


def parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
        except (ValueError, TypeError):
            continue
    return None


def age_days(row: Any, now: datetime | None = None) -> float:
    now = now or datetime.now()
    created = parse_dt(value(row, "created_at")) or now
    end = parse_dt(value(row, "resolved_at")) if value(row, "status") == "Resolved" else now
    end = end or now
    return max(0.0, (end - created).total_seconds() / 86400.0)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def nearby(row_a: Any, row_b: Any, radius_km: float = 0.45) -> bool:
    la, loa = value(row_a, "latitude"), value(row_a, "longitude")
    lb, lob = value(row_b, "latitude"), value(row_b, "longitude")
    if la is not None and loa is not None and lb is not None and lob is not None:
        try:
            return haversine_km(float(la), float(loa), float(lb), float(lob)) <= radius_km
        except (ValueError, TypeError):
            pass
    ward_a = str(value(row_a, "ward", "")).strip().lower()
    ward_b = str(value(row_b, "ward", "")).strip().lower()
    village_a = str(value(row_a, "village", "")).strip().lower()
    village_b = str(value(row_b, "village", "")).strip().lower()
    return bool(ward_a and ward_a == ward_b and (not village_a or not village_b or village_a == village_b))


def criticality_bonus(row: Any) -> int:
    text = " ".join(str(value(row, k, "")) for k in ("title", "description", "address", "location", "ward")).lower()
    bonus = 0
    keywords = {
        "school": 12, "college": 8, "hospital": 15, "clinic": 10, "bus stand": 8,
        "bridge": 12, "market": 7, "highway": 12, "main road": 8, "temple": 3,
        "elderly": 8, "senior": 8, "children": 10, "ambulance": 15,
    }
    for token, score in keywords.items():
        if token in text:
            bonus += score
    return min(30, bonus)


def impact_score(row: Any, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    priority = int(value(row, "priority", 0) or 0)
    emergency = bool(value(row, "emergency", 0))
    escalated = bool(value(row, "escalated", 0))
    upvotes = int(value(row, "upvotes", 0) or 0)
    age = age_days(row, now)
    criticality = criticality_bonus(row)
    recurrence_hint = 8 if value(row, "duplicate_group") else 0
    safety = min(100, priority + (18 if emergency else 0) + (10 if escalated else 0))
    exposure = min(100, 35 + criticality * 2 + min(upvotes * 4, 20) + (12 if emergency else 0))
    duration = min(100, 20 + age * 7)
    cascade = min(100, 30 + criticality + (20 if value(row, "category") in {"water", "road", "electricity", "fire"} else 8))
    score = round(min(100, safety * 0.34 + exposure * 0.25 + duration * 0.16 + cascade * 0.25 + recurrence_hint))
    if score >= 80:
        label = "Critical"
    elif score >= 65:
        label = "High"
    elif score >= 45:
        label = "Medium"
    else:
        label = "Low"
    estimated_people = max(40, round((exposure ** 1.35) * 8 + criticality * 55))
    return {
        "score": score,
        "label": label,
        "safety": round(safety),
        "exposure": round(exposure),
        "duration": round(duration),
        "cascade": round(cascade),
        "criticality": criticality,
        "estimated_people": estimated_people,
        "age_days": round(age, 1),
    }


def cost_of_delay(row: Any, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    info = impact_score(row, now)
    base_cost = CATEGORY_COST.get(str(value(row, "category", "")), 60000)
    recurrence = 1.0 + (0.22 if value(row, "duplicate_group") else 0)
    emergency = 1.35 if value(row, "emergency", 0) else 1.0
    slope = 0.035 + (info["score"] / 100) * 0.055
    future_cost = int(base_cost * recurrence * emergency * (1 + slope * max(1, days)))
    present_cost = int(base_cost * recurrence * emergency)
    danger_now = info["score"]
    danger_future = min(100, round(danger_now + days * (2.2 + info["cascade"] / 45)))
    return {
        "days": days,
        "cost_now": present_cost,
        "cost_future": future_cost,
        "extra_cost": max(0, future_cost - present_cost),
        "danger_now": danger_now,
        "danger_future": danger_future,
        "danger_delta": max(0, danger_future - danger_now),
    }


def civic_debt(rows: Iterable[Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    active = [r for r in rows if value(r, "status") != "Resolved"]
    items = []
    total_points = 0.0
    estimated_liability = 0
    for row in active:
        impact = impact_score(row, now)
        age_factor = 1 + min(3.0, impact["age_days"] / 14)
        points = impact["score"] * age_factor * (1.22 if value(row, "escalated", 0) else 1)
        delay = cost_of_delay(row, 7, now)
        total_points += points
        estimated_liability += delay["extra_cost"]
        items.append({"row": row, "debt": round(points), "impact": impact, "delay": delay})
    items.sort(key=lambda x: x["debt"], reverse=True)
    normalized = min(100, round(total_points / max(1, len(active)) / 2.0)) if active else 0
    label = "Critical" if normalized >= 75 else "High" if normalized >= 55 else "Moderate" if normalized >= 30 else "Controlled"
    return {"score": normalized, "label": label, "points": round(total_points), "estimated_liability": estimated_liability, "top": items[:8]}


def build_civic_memory(rows: Iterable[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        lat, lon = value(row, "latitude"), value(row, "longitude")
        if lat is not None and lon is not None:
            try:
                key = f"geo:{round(float(lat), 3)}:{round(float(lon), 3)}"
            except (TypeError, ValueError):
                key = ""
        else:
            key = ""
        if not key:
            key = "place:" + "|".join([
                str(value(row, "village", "")).strip().lower(),
                str(value(row, "ward", "")).strip().lower(),
                str(value(row, "address", value(row, "location", ""))).strip().lower()[:80],
            ])
        grouped[key].append(row)

    memories = []
    for key, items in grouped.items():
        cats = Counter(str(value(r, "category", "unknown")) for r in items)
        resolved = sum(value(r, "status") == "Resolved" for r in items)
        escalated = sum(bool(value(r, "escalated", 0)) for r in items)
        avg_priority = round(sum(int(value(r, "priority", 0) or 0) for r in items) / max(1, len(items)))
        repeated = max(cats.values()) if cats else 0
        recurrence = min(100, 20 + repeated * 12 + max(0, len(items) - 1) * 6 + escalated * 4)
        sample = items[-1]
        memories.append({
            "key": key,
            "label": str(value(sample, "address", value(sample, "location", "Unknown location"))) or "Unknown location",
            "ward": value(sample, "ward", "—"),
            "village": value(sample, "village", "—"),
            "total": len(items),
            "resolved": resolved,
            "active": len(items) - resolved,
            "escalated": escalated,
            "avg_priority": avg_priority,
            "recurrence": recurrence,
            "categories": cats.most_common(),
            "complaints": sorted(items, key=lambda r: int(value(r, "id", 0)), reverse=True)[:6],
        })
    memories.sort(key=lambda x: (x["recurrence"], x["total"], x["avg_priority"]), reverse=True)
    return memories


def causal_clusters(rows: Iterable[Any], radius_km: float = 0.45) -> list[dict[str, Any]]:
    rows = list(rows)
    # Build connected components using geography/ward similarity. O(n^2) is fine for a local-government MVP dataset.
    parents = list(range(len(rows)))

    def find(x: int) -> int:
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parents[rb] = ra

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if nearby(rows[i], rows[j], radius_km):
                union(i, j)

    comps: dict[int, list[Any]] = defaultdict(list)
    for i, row in enumerate(rows):
        comps[find(i)].append(row)

    output = []
    for items in comps.values():
        if len(items) < 2:
            continue
        categories = {str(value(r, "category", "")) for r in items}
        departments = {str(value(r, "department", "")) for r in items}
        if len(items) < 3 and len(departments) < 2:
            continue
        root = "Recurring local infrastructure stress"
        recommendation = "Inspect the shared location before repeating isolated repairs."
        for needed, cause, action in ROOT_CAUSE_RULES:
            if needed.issubset(categories):
                root, recommendation = cause, action
                break
        recurrence = max(Counter(str(value(r, "category", "")) for r in items).values())
        active = sum(value(r, "status") != "Resolved" for r in items)
        confidence = min(96, round(47 + len(items) * 4 + len(departments) * 7 + recurrence * 2 + active))
        sample = max(items, key=lambda r: int(value(r, "priority", 0) or 0))
        output.append({
            "id": "cluster-" + str(min(int(value(r, "id", 0) or 0) for r in items)),
            "label": f"{value(sample, 'ward', 'Area')} · {value(sample, 'village', '')}".strip(" ·"),
            "root_cause": root,
            "recommendation": recommendation,
            "confidence": confidence,
            "count": len(items),
            "active": active,
            "departments": sorted(departments),
            "categories": sorted(categories),
            "complaints": sorted(items, key=lambda r: int(value(r, "priority", 0) or 0), reverse=True),
        })
    output.sort(key=lambda x: (x["confidence"], x["count"]), reverse=True)
    return output


def ward_risk(rows: Iterable[Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        ward = str(value(row, "ward", "Unknown Ward")).strip() or "Unknown Ward"
        groups[ward].append(row)
    result = []
    for ward, items in groups.items():
        active = [r for r in items if value(r, "status") != "Resolved"]
        escalated = sum(bool(value(r, "escalated", 0)) for r in active)
        emergency = sum(bool(value(r, "emergency", 0)) for r in active)
        recurrence = max(Counter(str(value(r, "category", "")) for r in items).values()) if items else 0
        avg_priority = sum(int(value(r, "priority", 0) or 0) for r in active) / max(1, len(active))
        diversity = len({value(r, "category") for r in items})
        score = min(96, round(18 + avg_priority * 0.45 + escalated * 5 + emergency * 6 + recurrence * 2.3 + diversity * 2))
        reasons = []
        if recurrence >= 3:
            reasons.append(f"{recurrence} repeated incidents in the dominant category")
        if escalated:
            reasons.append(f"{escalated} SLA-breached active cases")
        if emergency:
            reasons.append(f"{emergency} emergency case(s)")
        if diversity >= 3:
            reasons.append("multiple infrastructure systems affected")
        if not reasons:
            reasons.append("historical complaint and priority pattern")
        result.append({
            "ward": ward,
            "risk": score,
            "active": len(active),
            "total": len(items),
            "escalated": escalated,
            "emergency": emergency,
            "recurrence": recurrence,
            "reasons": reasons,
        })
    result.sort(key=lambda x: x["risk"], reverse=True)
    return result


def blind_spots(rows: Iterable[Any]) -> list[dict[str, Any]]:
    risks = ward_risk(rows)
    if not risks:
        return []
    avg_reports = sum(x["total"] for x in risks) / max(1, len(risks))
    max_risk = max(x["risk"] for x in risks) or 1
    output = []
    for item in risks:
        # Prototype expected-stress signal combines historical risk and neighbouring-system diversity.
        expected = min(100, round(item["risk"] * 0.85 + item["recurrence"] * 5 + item["emergency"] * 4))
        reporting = min(100, round((item["total"] / max(1, avg_reports * 1.6)) * 100))
        blind = max(0, expected - reporting)
        if blind >= 12 or (item["risk"] >= 65 and item["total"] <= max(2, round(avg_reports * 0.6))):
            confidence = min(93, 55 + round(blind * 0.55) + item["recurrence"] * 2)
            output.append({**item, "expected_stress": expected, "reporting_signal": reporting, "blind_score": blind, "confidence": confidence})
    output.sort(key=lambda x: (x["blind_score"], x["risk"]), reverse=True)
    return output


def chronic_failures(rows: Iterable[Any]) -> list[dict[str, Any]]:
    memory = build_civic_memory(rows)
    output = []
    for item in memory:
        if item["total"] < 3:
            continue
        dominant = item["categories"][0] if item["categories"] else ("unknown", 0)
        if dominant[1] < 2:
            continue
        annualized_waste = dominant[1] * CATEGORY_COST.get(dominant[0], 60000)
        output.append({
            **item,
            "dominant_category": dominant[0],
            "repeat_count": dominant[1],
            "estimated_repeat_spend": annualized_waste,
            "recommendation": "Investigate the shared root cause instead of repeating the same surface-level repair.",
        })
    output.sort(key=lambda x: (x["recurrence"], x["repeat_count"]), reverse=True)
    return output


def civic_health(rows: Iterable[Any]) -> list[dict[str, Any]]:
    risks = ward_risk(rows)
    debt_by_ward: dict[str, float] = defaultdict(float)
    for row in rows:
        if value(row, "status") == "Resolved":
            continue
        debt_by_ward[str(value(row, "ward", "Unknown Ward"))] += impact_score(row)["score"]
    output = []
    for item in risks:
        debt_penalty = min(25, debt_by_ward[item["ward"]] / 18)
        health = max(5, round(100 - item["risk"] * 0.62 - debt_penalty))
        trend = "↓" if health < 60 else "→" if health < 78 else "↑"
        output.append({**item, "health": health, "trend": trend})
    output.sort(key=lambda x: x["health"])
    return output


def service_equity(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Flag unequal *service outcomes* without demographic profiling.

    CivicOS intentionally does not infer caste, religion, income, gender, or other
    protected characteristics. This prototype compares only operational evidence:
    unresolved burden, SLA breaches, age of open cases and recurrence by ward.
    """
    groups: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        ward = str(value(row, "ward", "Unknown Ward") or "Unknown Ward").strip()
        groups[ward].append(row)
    if not groups:
        return []

    output = []
    for ward, items in groups.items():
        active = [r for r in items if value(r, "status") != "Resolved"]
        resolved = [r for r in items if value(r, "status") == "Resolved"]
        breached = sum(1 for r in active if value(r, "escalated", 0))
        avg_open_age = sum(age_days(r) for r in active) / max(1, len(active))
        repeated_categories = Counter(str(value(r, "category", "unknown")) for r in items)
        recurrence = sum(max(0, count - 1) for count in repeated_categories.values())
        resolution_rate = len(resolved) / max(1, len(items))
        pressure = min(100, round(
            len(active) * 8
            + breached * 16
            + min(24, avg_open_age * 3)
            + min(20, recurrence * 4)
            + (1 - resolution_rate) * 18
        ))
        label = "High attention" if pressure >= 68 else "Watch" if pressure >= 45 else "Balanced"
        reasons = []
        if breached:
            reasons.append(f"{breached} SLA-breached active case(s)")
        if avg_open_age >= 2:
            reasons.append(f"open cases average {avg_open_age:.1f} days")
        if recurrence >= 2:
            reasons.append(f"{recurrence} repeat-service signals")
        if not reasons:
            reasons.append("service outcomes are currently within the normal range")
        output.append({
            "ward": ward,
            "pressure": pressure,
            "label": label,
            "active": len(active),
            "total": len(items),
            "breached": breached,
            "avg_open_age": round(avg_open_age, 1),
            "resolution_rate": round(resolution_rate * 100),
            "reasons": reasons,
            "recommendation": (
                "Audit response coverage and schedule a preventive inspection before adding more reactive work."
                if pressure >= 68 else
                "Compare response time and recurrence with neighbouring wards before reallocating capacity."
                if pressure >= 45 else
                "Maintain current service coverage and continue monitoring outcomes."
            ),
        })
    output.sort(key=lambda x: (x["pressure"], x["active"]), reverse=True)
    return output


def policy_insights(rows: Iterable[Any]) -> list[dict[str, Any]]:
    rows = list(rows)
    insights = []
    clusters = causal_clusters(rows)
    cross = next((c for c in clusters if len(c["departments"]) >= 2), None)
    if cross:
        insights.append({
            "title": "Coordinate infrastructure repair before repeated departmental work",
            "finding": f"{cross['count']} nearby incidents span {len(cross['departments'])} departments in {cross['label']}.",
            "recommendation": cross["recommendation"],
            "confidence": cross["confidence"],
        })
    chronic = chronic_failures(rows)
    if chronic:
        c = chronic[0]
        insights.append({
            "title": "Recurring repair pattern is creating avoidable civic debt",
            "finding": f"{c['label']} has {c['repeat_count']} repeated {c['dominant_category']} incidents and a recurrence score of {c['recurrence']}/100.",
            "recommendation": c["recommendation"],
            "confidence": min(95, 60 + c["repeat_count"] * 5),
        })
    risks = ward_risk(rows)
    if risks:
        r = risks[0]
        insights.append({
            "title": "Shift part of maintenance from reactive to preventive action",
            "finding": f"{r['ward']} currently carries the highest 7-day prototype failure risk ({r['risk']}%).",
            "recommendation": "Schedule a proactive inspection before the next high-load or rainfall period and verify the dominant recurring assets.",
            "confidence": min(92, 58 + round(r["risk"] * 0.32)),
        })
    if not insights:
        insights.append({"title": "More history required", "finding": "The policy engine needs additional complaints and repair outcomes before it can detect a stable structural pattern.", "recommendation": "Continue collecting evidence-rich complaint and resolution history.", "confidence": 45})
    return insights[:5]


def route_batches(rows: Iterable[Any], max_items: int = 4) -> list[dict[str, Any]]:
    candidates = [r for r in rows if value(r, "status") != "Resolved"]
    used: set[int] = set()
    batches = []
    sorted_rows = sorted(candidates, key=lambda r: int(value(r, "priority", 0) or 0), reverse=True)
    for seed in sorted_rows:
        sid = int(value(seed, "id", 0) or 0)
        if sid in used:
            continue
        group = [seed]
        for other in sorted_rows:
            oid = int(value(other, "id", 0) or 0)
            if oid in used or oid == sid:
                continue
            if len(group) >= max_items:
                break
            same_department = value(seed, "department") == value(other, "department")
            if same_department and nearby(seed, other, 0.8):
                group.append(other)
        if len(group) < 2:
            continue
        for r in group:
            used.add(int(value(r, "id", 0) or 0))
        estimated_saved_km = round(max(0.8, (len(group) - 1) * 1.6), 1)
        batches.append({
            "department": value(seed, "department"),
            "ward": value(seed, "ward"),
            "count": len(group),
            "complaints": group,
            "saved_km": estimated_saved_km,
            "note": "Inspection/route batch only. Individual repair assignments still obey the one-active-task-per-team rule.",
        })
    return batches[:8]


def reserve_capacity(workers: Iterable[dict[str, Any]], rows: Iterable[Any]) -> list[dict[str, Any]]:
    active_worker_ids = {str(value(r, "assigned_worker", "")) for r in rows if value(r, "status") != "Resolved" and value(r, "assigned_worker")}
    by_dept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for worker in workers:
        by_dept[str(worker.get("department"))].append(worker)
    output = []
    for dept, teams in by_dept.items():
        busy = sum(1 for w in teams if w.get("id") in active_worker_ids)
        available = len(teams) - busy
        protected = 1 if len(teams) >= 2 else 0
        state = "Protected" if available >= protected + 1 else "Reserve only" if protected and available == protected else "Fully committed"
        output.append({"department": dept, "total": len(teams), "busy": busy, "available": available, "protected": protected, "state": state})
    output.sort(key=lambda x: (x["available"], x["department"]))
    return output


def build_sweep_suggestions(rows: Iterable[Any]) -> list[dict[str, Any]]:
    clusters = [c for c in causal_clusters(rows, 0.7) if len(c["departments"]) >= 2 and c["active"] >= 2]
    suggestions = []
    for c in clusters[:6]:
        suggestions.append({
            "title": f"Cross-Department Sweep · {c['label']}",
            "description": f"Coordinate {len(c['departments'])} departments around {c['count']} connected incidents. {c['root_cause']}.",
            "departments": c["departments"],
            "complaint_ids": [int(value(r, "id", 0)) for r in c["complaints"] if value(r, "status") != "Resolved"],
            "confidence": c["confidence"],
            "recommendation": c["recommendation"],
        })
    return suggestions


def optimize_public_value(rows: Iterable[Any], budget: int, workers: int, vehicles: int, days: int) -> dict[str, Any]:
    budget = max(0, int(budget))
    workers = max(1, int(workers))
    vehicles = max(1, int(vehicles))
    days = max(1, int(days))
    candidates = []
    for row in rows:
        if value(row, "status") == "Resolved":
            continue
        impact = impact_score(row)
        delay = cost_of_delay(row, max(3, min(days, 14)))
        category = str(value(row, "category", ""))
        cost = int(CATEGORY_COST.get(category, 60000) * (0.72 + int(value(row, "priority", 50) or 50) / 180))
        manpower = 1 + (1 if impact["score"] >= 75 else 0) + (1 if value(row, "emergency", 0) else 0)
        vehicle_need = 1
        prevented = max(1, round(impact["score"] / 10 + impact["cascade"] / 18 + (3 if value(row, "duplicate_group") else 0)))
        benefit = impact["estimated_people"] + prevented * 180 + delay["extra_cost"] / 350
        ratio = benefit / max(cost, 1)
        candidates.append({
            "row": row, "cost": cost, "manpower": manpower, "vehicles": vehicle_need,
            "impact": impact, "delay": delay, "prevented": prevented, "benefit": benefit, "ratio": ratio,
        })
    candidates.sort(key=lambda x: (x["ratio"], x["impact"]["score"]), reverse=True)

    selected = []
    spent = 0
    manpower_days = workers * days
    vehicle_days = vehicles * days
    used_manpower_days = 0
    used_vehicle_days = 0
    for item in candidates:
        work_days = 1 + (1 if item["impact"]["score"] >= 80 else 0)
        m_need = item["manpower"] * work_days
        v_need = item["vehicles"] * work_days
        if spent + item["cost"] > budget:
            continue
        if used_manpower_days + m_need > manpower_days or used_vehicle_days + v_need > vehicle_days:
            continue
        selected.append(item)
        spent += item["cost"]
        used_manpower_days += m_need
        used_vehicle_days += v_need

    return {
        "budget": budget, "workers": workers, "vehicles": vehicles, "days": days,
        "spent": spent, "remaining": max(0, budget - spent),
        "selected": selected,
        "citizens_benefited": sum(x["impact"]["estimated_people"] for x in selected),
        "incidents_prevented": sum(x["prevented"] for x in selected),
        "avoided_delay_cost": sum(x["delay"]["extra_cost"] for x in selected),
        "high_risk_reduced": sum(1 for x in selected if x["impact"]["score"] >= 70),
        "manpower_utilization": round(100 * used_manpower_days / max(1, manpower_days)),
        "vehicle_utilization": round(100 * used_vehicle_days / max(1, vehicle_days)),
    }


def cascade_for(row: Any, days: int = 7) -> dict[str, Any]:
    impact = impact_score(row)
    category = str(value(row, "category", "road"))
    chain = CATEGORY_CASCADE.get(category, ["Civic issue", "Service disruption", "Public impact"])
    delay = cost_of_delay(row, days)
    probability = min(96, round(impact["cascade"] * 0.72 + days * 3.2 + (8 if value(row, "escalated", 0) else 0)))
    return {
        "chain": chain,
        "days": days,
        "probability": probability,
        "people": impact["estimated_people"],
        "delay": delay,
        "intervention_effect": max(20, probability - round(impact["score"] * 0.22)),
    }


def proof_verification(before_path: str | None, after_path: str | None, citizen_confirmed: bool = False) -> dict[str, Any]:
    """Score resolution evidence with transparent, non-generative checks.

    The engine intentionally treats image comparison as a *signal*, not proof by
    itself.  When Pillow is available it compares normalized before/after image
    content and basic capture quality; otherwise it safely falls back to a byte
    fingerprint difference check. Citizen confirmation is kept as a separate
    human-verification signal.
    """
    score = 0
    checks: list[tuple[str, str]] = []
    before = Path(before_path) if before_path else None
    after = Path(after_path) if after_path else None
    before_exists = bool(before and before.is_file())
    after_exists = bool(after and after.is_file())

    if before_exists:
        score += 15
        checks.append(("Before evidence", "PASS"))
    else:
        checks.append(("Before evidence", "MISSING"))

    if after_exists:
        score += 25
        checks.append(("After evidence", "PASS"))
    else:
        checks.append(("After evidence", "MISSING"))

    different = False
    visual_change_percent: float | None = None
    image_quality = "Unavailable"

    if before_exists and after_exists:
        try:
            # Pillow is optional at import time so the core civic engine remains
            # usable even if a deployment has not installed image extras yet.
            from PIL import Image, ImageChops, ImageOps, ImageStat

            with Image.open(before) as b_img, Image.open(after) as a_img:
                b_img = ImageOps.exif_transpose(b_img).convert("RGB")
                a_img = ImageOps.exif_transpose(a_img).convert("RGB")
                original_sizes = (b_img.size, a_img.size)
                sample_size = (128, 128)
                b_sample = b_img.resize(sample_size)
                a_sample = a_img.resize(sample_size)
                diff = ImageChops.difference(b_sample, a_sample)
                mean_channels = ImageStat.Stat(diff).mean
                raw_change = sum(mean_channels) / (3.0 * 255.0) * 100.0
                # Stretch the intuitive range slightly. Normal field photos of
                # the same location after repair often change only 5-20% of all
                # pixels, while completely unrelated photos become much larger.
                visual_change_percent = round(min(100.0, raw_change * 2.2), 1)
                different = visual_change_percent >= 5.0

                min_dimension = min(min(original_sizes[0]), min(original_sizes[1]))
                if min_dimension >= 720:
                    image_quality = "High"
                    score += 10
                    checks.append(("Image quality", "PASS"))
                elif min_dimension >= 360:
                    image_quality = "Usable"
                    score += 6
                    checks.append(("Image quality", "PASS"))
                else:
                    image_quality = "Low resolution"
                    checks.append(("Image quality", "REVIEW"))

                if visual_change_percent >= 10.0:
                    score += 30
                    checks.append(("Visual change", "PASS"))
                elif visual_change_percent >= 5.0:
                    score += 16
                    checks.append(("Visual change", "REVIEW"))
                else:
                    checks.append(("Visual change", "REVIEW"))
        except Exception:
            # Corrupt/unsupported images or missing Pillow must never break a
            # resolution workflow. A cryptographic fingerprint is a safe fallback
            # that only establishes that files are not byte-identical.
            try:
                b = before.read_bytes()
                a = after.read_bytes()
                different = sha256(b).digest() != sha256(a).digest()
                if different:
                    score += 20
                    checks.append(("Evidence change", "PASS"))
                else:
                    checks.append(("Evidence change", "REVIEW"))
            except OSError:
                checks.append(("Evidence change", "REVIEW"))

    if citizen_confirmed:
        score += 20
        checks.append(("Citizen confirmation", "PASS"))
    else:
        checks.append(("Citizen confirmation", "PENDING"))

    score = min(100, score)
    if not after_exists:
        status = "Evidence Needed"
    elif score >= 65 and citizen_confirmed:
        status = "Verified"
    elif score >= 65:
        status = "Strong Evidence"
    elif score >= 45:
        status = "Review"
    else:
        status = "Evidence Needed"

    return {
        "score": score,
        "status": status,
        "checks": checks,
        "different": different,
        "visual_change_percent": visual_change_percent,
        "image_quality": image_quality,
        "citizen_confirmed": bool(citizen_confirmed),
    }


def intelligence_bundle(rows: Iterable[Any], workers: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    risks = ward_risk(rows)
    return {
        "debt": civic_debt(rows),
        "memory": build_civic_memory(rows),
        "causal": causal_clusters(rows),
        "blind": blind_spots(rows),
        "risks": risks,
        "health": civic_health(rows),
        "equity": service_equity(rows),
        "chronic": chronic_failures(rows),
        "policy": policy_insights(rows),
        "batches": route_batches(rows),
        "reserve": reserve_capacity(workers, rows),
        "sweeps": build_sweep_suggestions(rows),
    }
