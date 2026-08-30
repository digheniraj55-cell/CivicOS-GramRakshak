"""CivicOS Trust & Verification Layer.

Pure-Python helpers for explainable claim matching and coordinated-submission
risk analysis. The module intentionally avoids external AI/API dependencies so
core verification signals continue to work during network outages.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from datetime import datetime, timedelta

STOPWORDS = {
    "the","a","an","and","or","to","of","in","on","for","is","are","was","were",
    "this","that","it","as","at","by","be","from","with","has","have","had","will",
    "can","our","your","you","we","they","their","i","my","me","but","not","now",
}

REPUTATION_TERMS = {
    "fraud","fraudulent","scam","scammer","corrupt","corruption","thief","stolen",
    "criminal","fake","bribe","bribery","cheat","cheating","poison","contaminated",
    "dangerous","cancelled","canceled","illegal",
}

FORWARDING_TERMS = {
    "forwarded","forward this","share urgently","urgent message","whatsapp","viral",
    "everyone share","send to everyone","breaking","must share","official message",
}


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_set(text: str) -> set[str]:
    return {w for w in normalize_text(text).split() if len(w) > 2 and w not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Blend token overlap with character-sequence similarity, 0..1."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    ta, tb = token_set(na), token_set(nb)
    union = ta | tb
    jaccard = len(ta & tb) / len(union) if union else 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    # Token overlap is more robust to forwarded-message formatting changes.
    return round((0.62 * jaccard) + (0.38 * seq), 4)


def trust_label(score: int) -> str:
    score = int(score or 0)
    if score >= 80:
        return "High Risk"
    if score >= 60:
        return "Needs Review"
    if score >= 35:
        return "Watch"
    return "Low Risk"


def trust_tone(label: str) -> str:
    return {
        "High Risk": "danger",
        "Needs Review": "warning",
        "Watch": "watch",
        "Low Risk": "safe",
        "Cleared": "safe",
        "Coordinated Abuse": "danger",
        "False Submission": "danger",
    }.get(label or "", "neutral")


def verdict_tone(verdict: str) -> str:
    return {
        "False": "danger",
        "Misleading": "warning",
        "True": "safe",
        "Verified": "safe",
        "Official Update": "info",
        "Unverified": "neutral",
    }.get(verdict or "Unverified", "neutral")


def _row_value(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default


def find_best_bulletin_match(text, bulletins):
    best = None
    best_score = 0.0
    for row in bulletins:
        title = str(_row_value(row, "title", "") or "")
        claim = str(_row_value(row, "claim_summary", "") or "")
        fact = str(_row_value(row, "fact_text", "") or "")
        keywords = str(_row_value(row, "keywords", "") or "")
        # Compare most strongly against the circulating-claim wording. A full
        # bulletin corpus can dilute an otherwise obvious match with correction text.
        score = max(
            similarity(text, claim),
            similarity(text, f"{title} {claim} {keywords}"),
            similarity(text, f"{claim} {fact}"),
        )
        if score > best_score:
            best_score, best = score, row
    return best, best_score


def evaluate_submission(con, title, description, citizen_user_id=None, has_photo=False,
                        ward="", category="", now=None, exclude_id=None):
    """Return an explainable misinformation/coordination risk assessment.

    This is a triage score, not a truth verdict. It never declares a citizen's
    statement false on its own; it only prioritizes human verification.
    """
    now = now or datetime.now()
    text = f"{title or ''} {description or ''}".strip()
    norm = normalize_text(text)
    score = 8
    signals = []
    similar_ids = []

    if citizen_user_id:
        score -= 8
        signals.append("Reporter identity is linked to a verified Civic Account.")
    else:
        score += 12
        signals.append("Reporter identity is not linked to a verified Civic Account.")

    if has_photo:
        score -= 6
        signals.append("Submission includes photo evidence.")
    else:
        score += 10
        signals.append("No photo evidence was attached; facts may need independent confirmation.")

    lower = norm
    rep_hits = sorted({term for term in REPUTATION_TERMS if term in lower})
    if rep_hits:
        add = min(18, 5 + len(rep_hits) * 3)
        score += add
        signals.append("High-impact/reputational language detected: " + ", ".join(rep_hits[:4]) + ".")

    forward_hits = sorted({term for term in FORWARDING_TERMS if term in lower})
    if forward_hits:
        score += 14
        signals.append("Forwarded/viral-message language detected; source verification is recommended.")

    # Compare against recent submissions for coordinated-copy patterns.
    since = (now - timedelta(hours=48)).isoformat(timespec="seconds")
    if exclude_id is None:
        rows = con.execute(
            "SELECT id,title,description,ward,category,citizen_user_id,created_at FROM complaints "
            "WHERE created_at>=? ORDER BY id DESC LIMIT 140",
            (since,),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT id,title,description,ward,category,citizen_user_id,created_at FROM complaints "
            "WHERE created_at>=? AND id!=? ORDER BY id DESC LIMIT 140",
            (since, int(exclude_id)),
        ).fetchall()
    strong_matches = []
    cross_identity = 0
    cross_area = 0
    for row in rows:
        other = f"{_row_value(row,'title','')} {_row_value(row,'description','')}"
        sim = similarity(text, other)
        if sim >= 0.72:
            strong_matches.append((row, sim))
            similar_ids.append(int(_row_value(row, "id", 0) or 0))
            if citizen_user_id and _row_value(row, "citizen_user_id") and int(_row_value(row, "citizen_user_id")) != int(citizen_user_id):
                cross_identity += 1
            if ward and _row_value(row, "ward") and str(_row_value(row, "ward")) != str(ward):
                cross_area += 1

    if strong_matches:
        score += min(24, 8 + (len(strong_matches) - 1) * 4)
        signals.append(f"Text is highly similar to {len(strong_matches)} recent submission(s).")
    if cross_identity >= 2:
        score += min(24, 10 + cross_identity * 4)
        signals.append(f"Near-identical text appears across {cross_identity + 1} different citizen identities.")
    if cross_area >= 2:
        score += 10
        signals.append("Near-identical wording appears across multiple wards, a possible coordination signal.")

    # A same-ward/category cluster can also be a legitimate infrastructure issue,
    # so it is only a light signal and never enough to block publication alone.
    same_context = [m for m in strong_matches if _row_value(m[0], "ward") == ward and _row_value(m[0], "category") == category]
    if same_context and cross_identity == 0:
        score -= 5
        signals.append("Similar reports are concentrated in the same service area, which may indicate a genuine shared issue.")

    # Very short accusatory claims are harder to verify and easier to weaponize.
    if len(token_set(text)) < 6 and rep_hits:
        score += 8
        signals.append("Claim is brief but accusatory, so supporting evidence should be checked before public amplification.")

    score = max(0, min(100, int(round(score))))
    return {
        "score": score,
        "label": trust_label(score),
        "signals": signals or ["No elevated misinformation signals detected by local triage rules."],
        "similar_ids": sorted(set(i for i in similar_ids if i)),
        "auto_quarantine": score >= 80,
    }
