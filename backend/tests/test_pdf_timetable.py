from datetime import date
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from app.models import TimetableSlot
from app.services import importer, pdf_timetable
from app.services.timetable import DayView
from tests.conftest import auth

HEADER = ["Date / Time", "9:20-10.15", "10.15-11.10", "11:10-\n11:30", "11.30-12.25", "12.25-1.20",
          "1:20 –\n2:05", "2:05 - 3:00", "3.00-3.55", "3.55-4.50"]
LEGEND_HEAD = ["Course Code", "Course Title", "Code", "Faculty Name", "Contact No. (+91)", "Room Number"]


def make_pdf(day_rows: list[list], legend: list[list]) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    grid = Table([HEADER] + day_rows)
    legend_table = Table([LEGEND_HEAD] + legend)
    style = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 7)])
    grid.setStyle(style)
    legend_table.setStyle(style)
    doc.build([
        Paragraph("SEM: III &amp; SEC: A    CLASSROOM - 201    III SEM TIME TABLE    CLASS TEACHER - Ms. Example", getSampleStyleSheet()["Normal"]),
        Spacer(1, 12), grid, Spacer(1, 12), legend_table,
    ])
    return buf.getvalue()


LEGEND = [["25X1", "OS : OPERATING SYSTEM", "SGS", "MS. SEEMA G S", "0000000000", "201"],
          ["25X2", "DSA : DATA STRUCTURES", "KVR", "DR. K V RAMASATISH", "0000000000", ""],
          ["25X3", "SPD : STATISTICS", "VS", "MS. VIJAYALAKSHMI S", "0000000000", ""]]


# ---------------------------------------------------------------- cells
def test_interpret_cell():
    assert pdf_timetable.interpret_cell("OS\n(SGS)") == {"kind": "class", "subject": "OS", "codes": ["SGS"]}
    assert pdf_timetable.interpret_cell("DSA (KVR)")["codes"] == ["KVR"]
    assert pdf_timetable.interpret_cell("OS (HSR / SGS)")["codes"] == ["HSR", "SGS"]
    assert pdf_timetable.interpret_cell("")["kind"] == "empty"
    for text in ("LIBRARY\nHOUR", "NSS/PE/YOGA/\nMUSIC", "TEA BREAK"):
        assert pdf_timetable.interpret_cell(text)["kind"] == "excluded"
    assert pdf_timetable.interpret_cell("SOCIETAL PROJECT")["kind"] == "no_faculty"
    assert pdf_timetable.interpret_cell("DS-A1 - AI / DS-A2 - Coding")["kind"] == "unresolved"
    assert pdf_timetable.interpret_cell("PEC")["kind"] == "unresolved"  # PEC is not "PE"


def test_canonical_name_ignores_titles_and_case():
    assert pdf_timetable.canonical_name("MS. VIJAYALAKSHMI S") == pdf_timetable.canonical_name("Ms Vijayalakshmi S")
    assert pdf_timetable.canonical_name("DR. K V RAMASATISH") == "K V Ramasatish"


def test_merged_cell_covers_both_periods():
    table = [HEADER, ["THURSDAY", "SPD\n(VS)", None, "", "OS\n(SGS)", "", "", "", "", ""]]
    cells, skipped = pdf_timetable.grid_cells(table)
    assert [(c["period"], c["subject"]) for c in cells] == [(1, "SPD"), (2, "SPD"), (3, "OS")]
    assert skipped == [] and all(c["day"] == 3 for c in cells)


# ---------------------------------------------------------------- local PDF reader
def test_local_parser_reads_a_text_pdf():
    rows = [
        ["MONDAY", "DSA\n(KVR)", "SPD\n(VS)", "", "OS\n(SGS)", "SPD\n(VS)", "", "SPD\n(VS)", "LIBRARY\nHOUR", ""],
        ["TUESDAY", "OS\n(SGS)", "DSA\n(KVR)", "", "SOCIETAL PROJECT", "", "", "", "", ""],
    ]
    draft = pdf_timetable.parse_pdf_locally(make_pdf(rows, LEGEND))
    assert draft["needs_ai"] is False
    page = draft["pages"][0]
    assert (page["semester"], page["section"]) == (3, "A")
    assert len(page["cells"]) == 7  # 5 on Monday, 2 on Tuesday; library hour and societal project are not classes
    assert any(s["text"] == "SOCIETAL PROJECT" for s in page["skipped"])
    assert draft["codes"] == {"SGS": "Seema G S", "KVR": "K V Ramasatish", "VS": "Vijayalakshmi S"}
    assert "0000000000" not in str(draft)  # phone numbers never enter the draft


def test_local_parser_flags_batch_cells_for_the_ai_reader():
    rows = [["MONDAY", "DS-A1 - AI /\nDS-A2 - Coding", "", "", "OS\n(SGS)", "", "", "", "", ""]]
    draft = pdf_timetable.parse_pdf_locally(make_pdf(rows, LEGEND))
    assert draft["needs_ai"] is True


def test_auto_mode_without_a_key_keeps_the_local_result(monkeypatch):
    monkeypatch.setattr(pdf_timetable, "get_settings", lambda: SimpleNamespace(gemini_api_key=""))
    rows = [["MONDAY", "DS-A1 - AI /\nDS-A2 - Coding", "", "", "OS\n(SGS)", "", "", "", "", ""]]
    draft = pdf_timetable.read_timetables([make_pdf(rows, LEGEND)], "auto")
    assert len(draft["pages"][0]["cells"]) == 1
    assert any("AI reader" in w for w in draft["warnings"])


def test_not_a_pdf_is_rejected():
    with pytest.raises(pdf_timetable.PdfReadError):
        pdf_timetable.read_timetables([b"hello"], "auto")


# ---------------------------------------------------------------- Gemini reader
GEMINI_ANSWER = """{"pages":[{"semester":"III","section":"a","cells":[
  {"day":"Mon","period":1,"batch":"a1","subject":"DS Lab","codes":["vz","vd"],"type":"lab"},
  {"day":"Mon","period":1,"batch":"A2","subject":"Coding Lab","codes":["RB"],"type":"lab"},
  {"day":"Mon","period":2,"batch":null,"subject":"OS","codes":["SGS"],"type":"theory"},
  {"day":"Sun","period":2,"batch":null,"subject":"Bad day","codes":["SGS"],"type":"theory"},
  {"day":"Tue","period":9,"batch":null,"subject":"Bad period","codes":["SGS"],"type":"theory"}],
  "skipped":[{"day":"Fri","period":5,"text":"SOCIETAL PROJECT","reason":"no faculty listed"}]}],
 "faculty":[{"code":"vz","name":"Vani Z"},{"code":"VD","name":"Vinutha D"},{"code":"RB","name":"Dr. Rashmi B C"},{"code":"SGS","name":"Ms. Seema G S"}]}"""


def fake_post(text: str, status: int = 200):
    def post(url, json=None, headers=None, timeout=None):
        assert "x-goog-api-key" in headers and timeout == 123
        assert json["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "application/pdf"
        request = httpx.Request("POST", url)
        body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        return httpx.Response(status, json=body, request=request)
    return post


@pytest.fixture
def gemini(monkeypatch):
    settings = SimpleNamespace(gemini_api_key="k", gemini_model="m", gemini_fallback_model="", gemini_pdf_timeout_seconds=123)
    monkeypatch.setattr(pdf_timetable, "get_settings", lambda: settings)


def test_gemini_answer_is_checked_cell_by_cell(gemini, monkeypatch):
    monkeypatch.setattr(pdf_timetable.httpx, "post", fake_post(GEMINI_ANSWER))
    draft = pdf_timetable.read_timetables([b"%PDF-1.4 fake"], "ai")
    page = draft["pages"][0]
    assert (page["semester"], page["section"]) == (3, "A")
    assert len(page["cells"]) == 3  # the Sunday and period-9 cells were dropped
    assert page["cells"][0]["batch"] == "A1" and page["cells"][0]["codes"] == ["VZ", "VD"]
    assert draft["codes"]["RB"] == "Rashmi B C"
    assert any("dropped" in w for w in draft["warnings"])


def test_gemini_failures_become_readable_errors(gemini, monkeypatch):
    monkeypatch.setattr(pdf_timetable.httpx, "post", fake_post("not json"))
    with pytest.raises(pdf_timetable.PdfReadError, match="not valid"):
        pdf_timetable.read_timetables([b"%PDF-1.4 fake"], "ai")
    monkeypatch.setattr(pdf_timetable.httpx, "post", fake_post("{}", status=404))
    with pytest.raises(pdf_timetable.PdfReadError, match="404"):
        pdf_timetable.read_timetables([b"%PDF-1.4 fake"], "ai")


def test_ai_mode_needs_a_key(monkeypatch):
    monkeypatch.setattr(pdf_timetable, "get_settings", lambda: SimpleNamespace(gemini_api_key=""))
    with pytest.raises(pdf_timetable.PdfReadError, match="GEMINI_API_KEY"):
        pdf_timetable.read_timetables([b"%PDF-1.4 fake"], "ai")


# ---------------------------------------------------------------- draft → database
def draft(extra_cells=()):
    cells = [
        {"day": 0, "period": 1, "batch": "A1", "subject": "DS Lab", "codes": ["VZ", "VD"], "type": "lab"},
        {"day": 0, "period": 1, "batch": "A2", "subject": "Coding Lab", "codes": ["RB"], "type": "lab"},
        {"day": 0, "period": 2, "batch": None, "subject": "OS", "codes": ["SGS"], "type": "theory"},
    ] + list(extra_cells)
    return {"pages": [{"semester": 3, "section": "A", "cells": cells, "skipped": []}],
            "codes": {"VZ": "Dr. Vani Z", "VD": "Ms Vinutha D", "RB": "Rashmi B C", "SGS": "Seema G S"}}


def run_import(db, d, **kw):
    rows, errors = pdf_timetable.draft_to_rows(d)
    return importer.import_rows(db, rows, earlier_errors=errors, create_missing=True, **kw)


def test_parallel_batches_and_co_teachers_do_not_clash(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    report = run_import(db, draft(), commit=True, replace_all=False)
    assert report["errors"] == [] and report["committed"] is True
    assert report["sections"] == ["3A"]
    assert db.query(TimetableSlot).filter_by(section="3A").count() == 4  # P1: three teachers in two batches, P2: one
    saved = (tmp_path / "map.csv").read_text()
    assert "Vani Z" in saved and "Faculty 13" in saved  # real names only in the gitignored map
    names = {u.name for u in db.query(importer.User)}
    assert "Vani Z" not in names  # the database holds Faculty N only
    # the day view sees no double-booking
    assert not [c for c in DayView(db, date(2026, 11, 9)).clashes() if "3A" in c[2]]


def test_a_real_clash_is_still_caught(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    whole_class = {"day": 0, "period": 1, "batch": None, "subject": "Maths", "codes": ["SGS"], "type": "theory"}
    report = run_import(db, draft([whole_class]), commit=True, replace_all=False)
    assert report["committed"] is False
    assert any("section 3A" in e for e in report["errors"])
    teacher = {"day": 0, "period": 1, "batch": "A2", "subject": "Other Lab", "codes": ["VZ"], "type": "lab"}
    report = run_import(db, draft([teacher]), commit=False, replace_all=False)
    assert any("already teaches" in e for e in report["errors"])


def test_unknown_code_is_reported_and_nothing_is_saved(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    d = draft()
    del d["codes"]["RB"]
    before = db.query(TimetableSlot).count()
    report = run_import(db, d, commit=True, replace_all=False)
    assert report["committed"] is False and any("RB" in e for e in report["errors"])
    assert db.query(TimetableSlot).count() == before


def test_import_replaces_only_the_sections_in_the_file(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    sevens = db.query(TimetableSlot).filter_by(section="7A").count()
    assert sevens > 0 and db.query(TimetableSlot).filter_by(section="5A").count() > 0
    d = draft()
    d["pages"][0].update(semester=5, section="A")
    assert run_import(db, d, commit=True, replace_all=False)["committed"] is True
    assert db.query(TimetableSlot).filter_by(section="7A").count() == sevens  # untouched
    assert db.query(TimetableSlot).filter_by(section="5A").count() == 4  # replaced, not added to
    run_import(db, d, commit=True, replace_all=True)
    assert db.query(TimetableSlot).filter_by(section="7A").count() == 0


def test_pdf_endpoints_need_the_hod_and_save_a_draft(client, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    body = {"draft": draft(), "commit": True}
    assert client.post("/timetable/pdf/import", json=body, headers=auth(client, "faculty1")).status_code == 403
    res = client.post("/timetable/pdf/import", json=body, headers=auth(client, "hod"))
    assert res.status_code == 200 and res.json()["committed"] is True
    bad = client.post("/timetable/pdf/read", files=[("files", ("x.pdf", b"hello", "application/pdf"))],
                      headers=auth(client, "hod"))
    assert bad.status_code == 422

