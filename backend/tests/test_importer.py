from io import BytesIO

from openpyxl import Workbook

from app.models import TimetableSlot
from app.services import importer


def workbook(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(importer.COLUMNS)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_template_parses_cleanly(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    report = importer.import_timetable(db, importer.template_workbook(), commit=False, create_missing=True)
    assert report["errors"] == []
    assert report["valid_slots"] == 3


def test_validation_reports_clashes_and_missing_fields(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    data = workbook([
        ["Dr. A", "Mon", 1, "5A", "Machine Learning", "theory", ""],
        ["Dr. A", "Mon", 1, "5B", "Machine Learning", "theory", ""],  # faculty clash
        ["Dr. B", "Mon", 1, "5A", "Deep Learning", "theory", ""],  # section clash
        ["", "Tue", 2, "5A", "Something", "theory", ""],  # missing faculty
        ["Dr. C", "Funday", 2, "5A", "Something", "theory", ""],  # bad day
        ["Dr. D", "Mon", 3, "5A", "Something", "theory", ""],  # unknown faculty (not allowed to create)
    ])
    report = importer.import_timetable(db, data, commit=True, create_missing=False)
    text = " ".join(report["errors"])
    assert "clash" in text and "missing" in text and "unknown day" in text and "unknown faculty" in text
    assert report["committed"] is False


def test_commit_anonymises_and_replaces_timetable(db, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "NAME_MAP_PATH", tmp_path / "map.csv")
    data = workbook([
        ["Dr. Real Name", "Mon", 1, "5A", "Machine Learning", "theory", "BLK-A-F1-R101"],
        ["Dr. Real Name", "Tue", 3, "5A", "Machine Learning Lab", "lab", "BLK-A-F1-LAB105"],
        ["Dr. Real Name", "Tue", 4, "5A", "Machine Learning Lab", "lab", "BLK-A-F1-LAB105"],
    ])
    report = importer.import_timetable(db, data, commit=True, create_missing=True)
    assert report["committed"] is True
    assert report["new_faculty"] == ["Faculty 13"]
    assert db.query(TimetableSlot).count() == 3
    saved = (tmp_path / "map.csv").read_text()
    assert "Dr. Real Name" in saved and "Faculty 13" in saved
