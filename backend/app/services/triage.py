"""AI triage (B10–B13): Gemini when available, a keyword classifier otherwise.

The result is only a suggestion; the in-charge can override it. Never raises: ticket creation must
succeed even when Gemini is down, slow, or returns nonsense."""
import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import get_settings
from app.models.tickets import CATEGORIES, PRIORITIES

log = logging.getLogger("educrew.triage")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class TriageResult:
    category: str
    priority: str
    summary: str
    confidence: float
    source: str  # gemini | rules


# ---------------------------------------------------------------- rule-based fallback

# Words of 4+ letters also match their endings ("leak" matches "leaking"), so list each stem once.
KEYWORDS: dict[str, list[str]] = {
    "electrical": [
        "light", "tube", "bulb", "fan", "fans", "switch", "switch board", "switchboard", "socket", "plug",
        "power", "electric", "wire", "wiring", "spark", "shock", "mcb", "fuse", "ac", "air conditioner",
        "voltage", "short circuit", "lift", "elevator", "ups", "inverter",
    ],
    "plumbing": [
        "tap", "taps", "leak", "water", "pipe", "flush", "toilet", "sink", "drain", "overflow", "tank",
        "cooler", "washbasin", "basin", "geyser", "urinal",
    ],
    "housekeeping": [
        "dirty", "clean", "garbage", "dust", "trash", "bin", "bins", "smell", "stink", "spill", "sweep",
        "mop", "cobweb", "pest", "cockroach", "rat", "rats", "litter", "unhygienic",
    ],
    "it": [
        "wifi", "wi-fi", "internet", "network", "computer", "pc", "pcs", "system", "monitor", "keyboard",
        "mouse", "printer", "projector", "hdmi", "lan", "software", "login", "server", "boot", "laptop",
        "smart board", "cable",
    ],
    "civil": [
        "door", "window", "wall", "ceiling", "crack", "plaster", "floor", "tile", "bench", "desk", "chair",
        "table", "paint", "roof", "glass", "handle", "lock", "hinge", "seepage", "dampness",
    ],
}

CRITICAL_WORDS = [
    "fire", "smoke", "spark", "shock", "electrocut", "flood", "burst", "gas", "short circuit",
    "exposed wire", "trapped", "stuck in lift", "collapse", "injur", "falling", "fell",
]
HIGH_WORDS = [
    "leak", "leaking", "overflow", "overflowing", "not working", "no water", "power cut", "no power",
    "broken", "blocked", "clogged", "outage", "stopped", "dead", "won't", "not booting", "drops",
    "dropping", "jerk", "jerks", "stopping",
]

# Location kinds nudge ties: a washroom report is more likely plumbing than civil.
KIND_HINTS = {"washroom": "plumbing", "lab": "it", "lift": "electrical"}


def _count(text: str, words: list[str]) -> int:
    hits = 0
    for word in words:
        if " " in word or "-" in word or "'" in word:
            hits += text.count(word)
        elif len(word) <= 3:  # short words must match whole ("ac" must not match "access")
            hits += len(re.findall(rf"\b{re.escape(word)}\b", text))
        else:  # longer words also match their endings ("leak" → "leaking")
            hits += len(re.findall(rf"\b{re.escape(word)}", text))
    return hits


def make_summary(description: str, limit: int = 90) -> str:
    text = " ".join(description.strip().split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) > limit:
        first = first[: limit - 1].rsplit(" ", 1)[0] + "…"
    return first[:1].upper() + first[1:] if first else "Maintenance request"


def classify_rules(description: str, location_kind: Optional[str] = None) -> TriageResult:
    text = description.lower()
    scores = {cat: _count(text, words) for cat, words in KEYWORDS.items()}
    hint = KIND_HINTS.get(location_kind or "")
    if hint:
        scores[hint] += 0.4  # breaks ties only; never outweighs a real keyword
    best = max(scores, key=lambda c: scores[c])
    total = sum(scores.values())
    if scores[best] < 1:
        category, confidence = (hint or "civil"), 0.2
    else:
        category = best
        confidence = round(min(0.9, 0.35 + 0.55 * (scores[best] / total)), 2)

    if _count(text, CRITICAL_WORDS):
        priority = "critical"
    elif _count(text, HIGH_WORDS):
        priority = "high"
    else:
        priority = "normal"
    return TriageResult(category, priority, make_summary(description), confidence, "rules")


# ---------------------------------------------------------------- Gemini

PROMPT = """You triage maintenance reports for an engineering college campus.
Location: {location}
Report from a student or staff member: "{description}"

Reply with JSON only, with these keys:
- "category": one of {categories}
- "priority": one of critical, high, normal
    critical = safety risk (fire, sparks, shock, flooding, someone trapped) or a total outage needing action within hours
    high = something broken or unusable that disrupts classes or a washroom
    normal = minor issue
- "summary": one line, at most 12 words, for the maintenance in-charge
- "confidence": number from 0 to 1"""


def _parse_gemini(payload: dict) -> Optional[TriageResult]:
    parts = payload["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(text)
    category = str(data.get("category", "")).lower().strip()
    priority = str(data.get("priority", "")).lower().strip()
    if category not in CATEGORIES or priority not in PRIORITIES:
        return None
    summary = str(data.get("summary", "")).strip()[:200]
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    return TriageResult(category, priority, summary, round(confidence, 2), "gemini")


def classify_gemini(
    description: str,
    location: str,
    photo: Optional[bytes] = None,
    photo_mime: Optional[str] = None,
) -> Optional[TriageResult]:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    parts: list[dict] = [
        {"text": PROMPT.format(location=location, description=description[:2000], categories=", ".join(CATEGORIES))}
    ]
    if photo and photo_mime:
        parts.append({"inline_data": {"mime_type": photo_mime, "data": base64.b64encode(photo).decode()}})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    try:
        response = httpx.post(
            GEMINI_URL.format(model=settings.gemini_model),
            json=body,
            headers={"x-goog-api-key": settings.gemini_api_key},
            timeout=settings.gemini_timeout_seconds,
        )
        response.raise_for_status()
        result = _parse_gemini(response.json())
        if result is None:
            log.warning("Gemini triage returned an unusable answer; using rules")
        return result
    except httpx.HTTPStatusError as exc:
        # Never log the key; the status code is enough to debug.
        log.warning("Gemini triage HTTP %s; using rules", exc.response.status_code)
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini triage failed (%s); using rules", type(exc).__name__)
    return None


def triage(
    description: str,
    location: str,
    location_kind: Optional[str] = None,
    photo: Optional[bytes] = None,
    photo_mime: Optional[str] = None,
) -> TriageResult:
    result = classify_gemini(description, location, photo, photo_mime)
    if result is None:
        return classify_rules(description, location_kind)
    if not result.summary:
        result.summary = make_summary(description)
    return result
