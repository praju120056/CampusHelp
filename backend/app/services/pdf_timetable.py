"""Read class timetables from PDF (C2).

Two readers, both producing the same "draft":
  1. A local parser (pdfplumber). Free, offline, nothing leaves the laptop. It understands text PDFs whose
     cells look like "OS (SGS)". Anything it cannot read for certain (lab batches, subject-only cells,
     scans) is flagged instead of guessed.
  2. Gemini, which reads the PDF as an image. It handles scans and complicated cells, but the PDF,
     including the faculty names printed on it, is sent to Google. It only runs when the HOD asks
     for it (mode "ai") or when mode "auto" finds cells the local parser cannot read.

A draft is plain JSON the HOD reviews and edits before anything is saved:
  {"source", "pages": [{"semester", "section", "cells": [...], "skipped": [...]}],
   "codes": {"VS": "Vijayalakshmi S"}, "warnings": [...]}
A cell is {"day": 0-5, "period": 1-7, "batch": None | "A1", "subject", "codes": ["VS"], "type"}.
NSS / PE / Yoga, library hours, tea and lunch breaks are left out on purpose.
Real names are only in the draft and the gitignored name map; the database gets Faculty N."""
import base64
import json
import logging
import re
import time
from io import BytesIO
from typing import Optional

import httpx

from app.config import get_settings
from app.services.timetable import DAY_NAMES, DAY_PERIODS

log = logging.getLogger("educrew.pdf_timetable")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

RETRIES = 2  # Gemini says 503/429 when it is busy; waiting a few seconds usually fixes it
BUSY_STATUSES = (429, 500, 502, 503, 504)
RETRY_WAIT_SECONDS = 4  # 5xx: Gemini is busy for a moment
QUOTA_WAIT_SECONDS = 25  # 429: the per-minute quota; it refills within a minute

DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
# Start time of each period column (24 h). Tea/lunch columns start at 11:10 and 13:20, so they match nothing.
PERIOD_BY_START = {(9, 20): 1, (10, 15): 2, (11, 30): 3, (12, 25): 4, (14, 5): 5, (15, 0): 6, (15, 55): 7}

EXCLUDED = re.compile(r"\b(library|nss|yoga|music|tea|lunch|break)\b|\bpe\b", re.I)
NO_FACULTY = re.compile(r"societal|mini\s*project|coursera|skills?\s*lab", re.I)
SIMPLE_CELL = re.compile(
    r"^(?P<subject>[A-Za-z][A-Za-z&.\- ]*?)\s*\((?P<codes>[A-Za-z]{1,5}(?:\s*[,+/&]\s*[A-Za-z]{1,5})*)\)$"
)
TITLES = re.compile(r"^(dr|ms|mrs|mr|prof|smt|shri)\b\.?\s*", re.I)


class PdfReadError(Exception):
    """Something the HOD can act on; the message is shown as is."""


class GeminiBusy(PdfReadError):
    """The model is overloaded or too slow right now; another model may answer."""


# ---------------------------------------------------------------- small helpers
def canonical_name(name: str) -> str:
    """'MS. VIJAYALAKSHMI S' and 'Ms Vijayalakshmi S' are the same person."""
    text = " ".join(str(name or "").replace(".", " ").split())
    while True:
        stripped = TITLES.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    return text.title()


def _clean(text: Optional[str]) -> str:
    return " ".join(str(text or "").split())


def _semester(value) -> Optional[int]:
    text = _clean(value).upper().rstrip(".")
    if text in ROMAN:
        return ROMAN[text]
    return int(text) if text.isdigit() and 1 <= int(text) <= 8 else None


def _day(value) -> Optional[int]:
    if isinstance(value, int) and 0 <= value <= 5:
        return value
    return DAY_INDEX.get(_clean(value).lower()[:3])


def _split_codes(text: str) -> list[str]:
    return [c.upper() for c in re.split(r"[,+/&\s]+", text) if re.fullmatch(r"[A-Za-z]{1,5}", c)]


# ---------------------------------------------------------------- local parser
def interpret_cell(text: Optional[str]) -> dict:
    """What a grid cell says. kind: empty | excluded | no_faculty | class | unresolved."""
    text = _clean(text)
    if not text:
        return {"kind": "empty"}
    if EXCLUDED.search(text):
        return {"kind": "excluded"}
    if NO_FACULTY.search(text):
        return {"kind": "no_faculty", "text": text}
    match = SIMPLE_CELL.match(text)
    if match:
        return {"kind": "class", "subject": _clean(match["subject"]), "codes": _split_codes(match["codes"])}
    return {"kind": "unresolved", "text": text}


def _period_for_header(text: Optional[str]) -> Optional[int]:
    match = re.match(r"\s*(\d{1,2})\s*[:.]\s*(\d{2})", str(text or ""))
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2])
    if hour < 8:
        hour += 12
    return PERIOD_BY_START.get((hour, minute))


def grid_cells(table: list[list]) -> tuple[list[dict], list[dict]]:
    """Turn a day × time table into cells and skipped notes. A merged cell (None after a value) covers
    every period it spans."""
    cols = {i: p for i, h in enumerate(table[0]) if (p := _period_for_header(h))}
    cells: list[dict] = []
    skipped: list[dict] = []
    for row in table[1:]:
        day = _day(_clean(row[0]) if row else "")
        if day is None:
            continue
        previous: Optional[str] = None
        for i, period in cols.items():
            raw = row[i] if i < len(row) else ""
            if raw is None and (i - 1) in cols:
                raw = previous
            previous = raw
            result = interpret_cell(raw)
            if result["kind"] == "class" and result["codes"]:
                cells.append({"day": day, "period": period, "batch": None, "subject": result["subject"],
                              "codes": result["codes"], "type": "theory"})
            elif result["kind"] in ("no_faculty", "unresolved"):
                reason = "no faculty listed" if result["kind"] == "no_faculty" else "needs the AI reader or a manual fix"
                skipped.append({"day": day, "period": period, "text": result["text"], "reason": reason})
    return cells, skipped


def legend_codes(tables: list[list[list]]) -> dict[str, str]:
    """code → name from the 'Code | Faculty Name' table at the foot of a page."""
    found: dict[str, str] = {}
    for table in tables:
        for r, row in enumerate(table):
            labels = [_clean(c).lower() for c in row]
            if "code" not in labels or not any("faculty" in c for c in labels):
                continue
            code_col = labels.index("code")
            name_col = next(i for i, c in enumerate(labels) if "faculty" in c)
            for body in table[r + 1:]:
                if max(code_col, name_col) >= len(body):
                    continue
                codes = _split_codes(_clean(body[code_col]))
                names = [n for n in re.split(r"\s/\s|/", _clean(body[name_col])) if n.strip()]
                if codes and len(codes) == len(names):
                    for code, name in zip(codes, names):
                        found.setdefault(code, canonical_name(name))
                elif len(codes) == 1 and names:
                    found.setdefault(codes[0], canonical_name(" ".join(names)))
    return found


def parse_pdf_locally(data: bytes) -> dict:
    import pdfplumber

    pages: list[dict] = []
    codes: dict[str, str] = {}
    warnings: list[str] = []
    needs_ai = False
    try:
        pdf = pdfplumber.open(BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise PdfReadError("That file could not be opened as a PDF.") from exc
    with pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            header = re.search(r"SEM\s*:?\s*([IVX]+|\d)\s*&?\s*SEC\s*:?\s*([A-Z])\b", text, re.I)
            tables = page.extract_tables()
            grid = next((t for t in tables if t and _clean(t[0][0] if t[0] else "").lower().startswith("date")), None)
            if len(text.strip()) < 60 or not header or grid is None:
                needs_ai = True
                warnings.append(f"Page {number}: no readable text or grid (probably a scan). The AI reader is needed.")
                continue
            semester = _semester(header[1])
            if semester is None:
                needs_ai = True
                warnings.append(f"Page {number}: could not read the semester. The AI reader is needed.")
                continue
            cells, skipped = grid_cells(grid)
            if skipped and any(s["reason"].startswith("needs") for s in skipped):
                needs_ai = True
            for code, name in legend_codes(tables).items():
                codes.setdefault(code, name)
            pages.append({"semester": semester, "section": header[2].upper(), "cells": cells, "skipped": skipped})
    return {"source": "parser", "pages": pages, "codes": codes, "warnings": warnings, "needs_ai": needs_ai}


# ---------------------------------------------------------------- Gemini reader
PROMPT = """You are reading college class timetables, one class section per page. Reply with ONE JSON object and nothing else.

Each page has a header like "SEM: III & SEC: A", a weekly grid (days Monday to Friday down the left, time slots across the top) and a table at the bottom listing courses and the faculty who teach them, with short faculty codes.

Period numbers (ignore the tea break and lunch break columns):
1 = 9:20-10:15, 2 = 10:15-11:10, 3 = 11:30-12:25, 4 = 12:25-1:20, 5 = 2:05-3:00, 6 = 3:00-3:55, 7 = 3:55-4:50.

Rules:
- Write one entry in "cells" per period per batch. A cell that spans two or more columns (a lab) is listed once for EACH period it covers.
- "codes" are the short faculty codes teaching that cell, uppercase, for example ["VZ","VD"]. Use the codes shown in the cell. If the cell shows only a subject, find the faculty code in the course table at the bottom of the page.
- Cells split by batch (A1/A2, B1/B2 and so on) get one entry per batch, with "batch" set to the batch name (for example "A1") and the faculty for that batch from the table at the bottom. Whole-class periods have "batch": null.
- A batch cell names a subject for each batch, for example "A1 - AEC / A2 - LDCO". Take each batch's faculty from the table row of THAT subject. Never copy the faculty of another subject that runs in the same period. If the subject has no per-batch row in the table (for example LDCO or a tutorial), its faculty is the subject's normal teacher for the class, the same person for both batches.
- Read faculty codes letter by letter. Codes that look alike are different people (for example DV and VD, SS and ST, CS and SS).
- "subject" is the short subject name as written (for example "OS", "DSA", "DS Lab", "AI Lab"). "type" is "lab" for lab, coding-lab and circuit-lab sessions, otherwise "theory".
- Leave out NSS, PE, Yoga, Music, library hour or activity, tea break and lunch break completely.
- If a cell has an activity but no faculty can be identified (societal project, mini project, Coursera activity, skills lab), do NOT put it in "cells". List it in "skipped" with its text and a short reason.
- "faculty" lists every code from the course tables with the person's name as printed, without titles such as Dr. or Ms. Do not include phone numbers or any other personal detail.
- Never invent a code or a name. If you cannot read something, skip that cell and add it to "skipped".

JSON shape:
{"pages":[{"semester":3,"section":"A","cells":[{"day":"Mon","period":1,"batch":null,"subject":"OS","codes":["SGS"],"type":"theory"}],"skipped":[{"day":"Tue","period":5,"text":"SOCIETAL PROJECT","reason":"no faculty listed"}]}],"faculty":[{"code":"VS","name":"Vijayalakshmi S"}]}
Days are Mon, Tue, Wed, Thu, Fri."""


def _gemini_json(payload: dict) -> dict:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise PdfReadError("Gemini's answer was cut off or not valid. Try again, or use the local reader.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        raise PdfReadError("Gemini's answer did not contain any timetable pages.")
    return data


def normalise_gemini(data: dict, page_offset: int = 0) -> dict:
    """Check Gemini's answer cell by cell. Whatever is invalid is dropped with a warning, never guessed."""
    pages: list[dict] = []
    warnings: list[str] = []
    for n, raw in enumerate(data["pages"], start=page_offset + 1):
        semester = _semester(raw.get("semester"))
        section = _clean(raw.get("section")).upper()
        if semester is None or not re.fullmatch(r"[A-Z]", section):
            warnings.append(f"AI page {n}: semester or section not readable, page left out.")
            continue
        cells: list[dict] = []
        dropped = 0
        for c in raw.get("cells") or []:
            day = _day(c.get("day"))
            try:
                period = int(c.get("period"))
            except (TypeError, ValueError):
                period = 0
            codes = [x for x in (_clean(k).upper() for k in c.get("codes") or []) if re.fullmatch(r"[A-Z]{1,5}", x)]
            subject = _clean(c.get("subject"))
            if day is None or not 1 <= period <= DAY_PERIODS[day] or not codes or not subject:
                dropped += 1
                continue
            batch = _clean(c.get("batch")).upper() or None
            cells.append({"day": day, "period": period, "batch": batch, "subject": subject, "codes": codes,
                          "type": "lab" if _clean(c.get("type")).lower() == "lab" else "theory"})
        if dropped:
            warnings.append(f"{semester}{section}: {dropped} unreadable cell(s) dropped.")
        skipped = [
            {"day": _day(s.get("day")), "period": s.get("period"), "text": _clean(s.get("text"))[:80],
             "reason": _clean(s.get("reason"))[:80]}
            for s in raw.get("skipped") or [] if isinstance(s, dict)
        ]
        pages.append({"semester": semester, "section": section, "cells": cells, "skipped": skipped})
    codes: dict[str, str] = {}
    for f in data.get("faculty") or []:
        if isinstance(f, dict):
            code, name = _clean(f.get("code")).upper(), canonical_name(f.get("name"))
            if re.fullmatch(r"[A-Z]{1,5}", code) and name:
                codes.setdefault(code, name)
    return {"source": "gemini", "pages": pages, "codes": codes, "warnings": warnings, "needs_ai": False}


def _ask_gemini(data: bytes, model: str) -> dict:
    """One request: a PDF in, Gemini's raw JSON out."""
    settings = get_settings()
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(data).decode()}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 32768},
    }
    try:
        for attempt in range(1, RETRIES + 1):
            response = httpx.post(
                GEMINI_URL.format(model=model),
                json=body,
                headers={"x-goog-api-key": settings.gemini_api_key},
                timeout=settings.gemini_pdf_timeout_seconds,
            )
            if response.status_code in BUSY_STATUSES and attempt < RETRIES:
                log.info("Gemini busy (%s); retrying", response.status_code)
                wait = QUOTA_WAIT_SECONDS if response.status_code == 429 else RETRY_WAIT_SECONDS * attempt
                time.sleep(wait)
                continue
            break
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise GeminiBusy("Gemini took too long to read the PDF. Try again, or use the local reader.") from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code  # never log the key; the status is enough
        log.warning("Gemini PDF read HTTP %s", code)
        if code == 429:
            raise GeminiBusy("Google says too many requests (the API key's free quota). Wait a minute and try again.") from exc
        hint = " Check GEMINI_MODEL and the API key." if code in (400, 401, 403, 404) else ""
        if code in BUSY_STATUSES:
            raise GeminiBusy(f"Gemini is busy right now ({code}). Try again in a minute.") from exc
        raise PdfReadError(f"Gemini returned an error ({code}).{hint}") from exc
    except httpx.HTTPError as exc:
        raise PdfReadError("Could not reach Gemini. Check the internet connection.") from exc
    return _gemini_json(payload)


def read_with_gemini(data: bytes) -> dict:
    """The whole PDF in one request. (Reading pages in parallel made Google answer 429 Too Many Requests.)"""
    if not get_settings().gemini_api_key:
        raise PdfReadError("The AI reader needs GEMINI_API_KEY in .env.")
    settings = get_settings()
    models = [settings.gemini_model]
    if settings.gemini_fallback_model and settings.gemini_fallback_model not in models:
        models.append(settings.gemini_fallback_model)
    for number, model in enumerate(models, start=1):
        try:
            return normalise_gemini(_ask_gemini(data, model))
        except GeminiBusy:
            if number == len(models):
                raise
            log.info("Gemini model %s is busy; trying %s", model, models[number])


# ---------------------------------------------------------------- putting files together
def merge_drafts(drafts: list[dict]) -> dict:
    pages: list[dict] = []
    codes: dict[str, str] = {}
    warnings: list[str] = []
    for d in drafts:
        pages += d["pages"]
        warnings += d["warnings"]
        for code, name in d["codes"].items():
            if code in codes and codes[code] != name:
                warnings.append(f"Code {code} is used for two different names ({codes[code]}, {name}). Check the list.")
            codes.setdefault(code, name)
    sources = {d["source"] for d in drafts}
    seen: set[str] = set()
    for p in pages:
        label = f"{p['semester']}{p['section']}"
        if label in seen:
            warnings.append(f"Class {label} appears more than once. The later page will clash with the earlier one.")
        seen.add(label)
    return {"source": sources.pop() if len(sources) == 1 else "mixed", "pages": pages, "codes": codes, "warnings": warnings}


def read_timetables(files: list[bytes], mode: str = "auto") -> dict:
    """mode: 'parser' = local only, 'ai' = Gemini only, 'auto' = local first, Gemini for what it cannot read."""
    if mode not in ("auto", "parser", "ai"):
        raise PdfReadError("Unknown reading mode.")
    if not files:
        raise PdfReadError("Choose at least one PDF.")
    have_key = bool(get_settings().gemini_api_key)
    drafts: list[dict] = []
    for number, data in enumerate(files, start=1):
        if not data.startswith(b"%PDF"):
            raise PdfReadError(f"File {number} is not a PDF.")
        if mode == "ai":
            drafts.append(read_with_gemini(data))
            continue
        local = parse_pdf_locally(data)
        if mode == "parser" or not local["needs_ai"]:
            drafts.append(local)
            continue
        if not have_key:
            if not local["pages"]:
                raise PdfReadError("This PDF looks scanned and the AI reader is not set up (GEMINI_API_KEY).")
            local["warnings"].append("Some cells need the AI reader, which is not set up. They were skipped.")
            drafts.append(local)
            continue
        try:
            drafts.append(read_with_gemini(data))
        except PdfReadError as exc:
            if not local["pages"]:
                raise
            local["warnings"].append(f"The AI reader failed ({exc}). Showing what the local reader found.")
            drafts.append(local)
    return merge_drafts(drafts)


# ---------------------------------------------------------------- draft → importer rows
def draft_to_rows(draft: dict) -> tuple[list[dict], list[str]]:
    """One row per faculty member per period, in the shape the importer validates."""
    codes = {str(k).upper(): canonical_name(v) for k, v in (draft.get("codes") or {}).items() if str(v).strip()}
    rows: list[dict] = []
    errors: list[str] = []
    missing: set[str] = set()
    for page in draft.get("pages") or []:
        section = f"{page['semester']}{page['section']}"
        for cell in page.get("cells") or []:
            for code in cell["codes"]:
                code = str(code).upper()
                if code not in codes:
                    if code not in missing:
                        missing.add(code)
                        errors.append(f"Faculty code {code} (class {section}) has no name. Type it in the faculty list.")
                    continue
                rows.append({
                    "line": len(rows) + 1,
                    "where": f"{section} {DAY_NAMES[cell['day']][:3]} P{cell['period']}",
                    "Faculty": codes[code], "Day": cell["day"], "Period": cell["period"], "Section": section,
                    "Subject": cell["subject"], "Type": cell.get("type", "theory"), "Room": None,
                    "Batch": cell.get("batch"),
                })
    return rows, errors


def draft_skipped(draft: dict) -> list[str]:
    out: list[str] = []
    for page in draft.get("pages") or []:
        for s in page.get("skipped") or []:
            day = DAY_NAMES[s["day"]][:3] if isinstance(s.get("day"), int) else "?"
            out.append(f"{page['semester']}{page['section']} {day} P{s.get('period', '?')}: skipped \"{s.get('text', '')}\" ({s.get('reason', '')})")
    return out
