"""Excel exports (A6, A11). Loads use the same weights as the dashboard, so totals match."""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models import Adjustment, Duty, Faculty, WorkLog
from app.services import fairness, workload
from app.services.timetable import periods_label

HEADER_FILL = PatternFill("solid", fgColor="E8E4DA")
BOLD = Font(bold=True)
SUMMARY_COLUMNS = [
    ("theory", "Theory periods"),
    ("lab", "Lab periods"),
    ("duty", "Duty slots"),
    ("meeting", "Meeting hours"),
    ("substitution", "Substitution periods"),
]


def _sheet(ws, headers: list[str], rows: list[list], total_row: list | None = None) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = BOLD
        cell.fill = HEADER_FILL
    for row in rows:
        ws.append(row)
    if total_row:
        ws.append(total_row)
        for cell in ws[ws.max_row]:
            cell.font = BOLD
    ws.freeze_panes = "A2"
    for i, header in enumerate(headers, start=1):
        width = max([len(str(header))] + [len(str(r[i - 1])) for r in rows if i - 1 < len(r)] + [8])
        ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 50)


def summary_rows(db: Session, start: date, end: date) -> list[dict]:
    w = workload.weights(db)
    units = workload.units_by_type(db, start, end)
    loads = workload.weighted_loads(db, start, end, w)
    out = []
    for fac in db.query(Faculty).order_by(Faculty.id).all():
        by_type = units.get(fac.id, {})
        out.append(
            {
                "faculty_id": fac.id,
                "name": fac.name,
                "designation": fac.designation,
                **{key: by_type.get(key, 0.0) for key, _ in SUMMARY_COLUMNS},
                "load": round(loads.get(fac.id, 0.0), 2),
            }
        )
    return out


def _to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def logs_workbook(db: Session, start: date, end: date) -> bytes:
    w = workload.weights(db)
    logs = (
        db.query(WorkLog)
        .filter(WorkLog.date >= start, WorkLog.date <= end)
        .order_by(WorkLog.date, WorkLog.faculty_id, WorkLog.period)
        .all()
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Logs"
    rows = []
    total_units = total_load = 0.0
    for log in logs:
        per_unit = float(w.get(log.type, 0))
        load = round(log.units * per_unit, 2)
        total_units += log.units
        total_load += load
        rows.append([
            log.date.isoformat(), log.faculty.name, log.faculty.designation, log.type, log.section or "",
            log.subject or "", log.period or "", log.topic or "", log.units, per_unit, load, log.tag or "",
        ])
    _sheet(
        ws,
        ["Date", "Faculty", "Designation", "Type", "Section", "Subject", "Period", "Topic", "Units",
         "Weight per unit", "Weighted load", "Tag"],
        rows,
        ["TOTAL", "", "", "", "", "", "", "", round(total_units, 2), "", round(total_load, 2), ""],
    )

    summary = summary_rows(db, start, end)
    ws2 = wb.create_sheet("Summary")
    _sheet(
        ws2,
        ["Faculty", "Designation"] + [label for _, label in SUMMARY_COLUMNS] + ["Weighted load"],
        [[r["name"], r["designation"]] + [r[k] for k, _ in SUMMARY_COLUMNS] + [r["load"]] for r in summary],
        ["TOTAL", ""] + [round(sum(r[k] for r in summary), 2) for k, _ in SUMMARY_COLUMNS]
        + [round(sum(r["load"] for r in summary), 2)],
    )
    ws3 = wb.create_sheet("About")
    ws3.append(["Date range", f"{start.isoformat()} to {end.isoformat()}"])
    ws3.append(["Weights", ", ".join(f"{k} {v}" for k, v in w.items())])
    return _to_bytes(wb)


def report_data(db: Session, start: date, end: date) -> dict:
    """A11: load, duty and adjustment statistics for NAAC/NBA (used by the Excel and printable report)."""
    summary = summary_rows(db, start, end)
    loads = [r["load"] for r in summary]
    mean, sd = fairness.mean_sd(loads)
    for r in summary:
        r["flag"] = fairness.classify(r["load"], mean, sd)
        r["share"] = round(100 * r["load"] / sum(loads), 1) if sum(loads) else 0.0
    adjustments = (
        db.query(Adjustment)
        .filter(Adjustment.date >= start, Adjustment.date <= end)
        .order_by(Adjustment.date, Adjustment.id)
        .all()
    )
    adj_rows = []
    for a in adjustments:
        taker = next((c for c in a.candidates if c.state == "accepted"), None)
        adj_rows.append(
            {
                "date": a.date.isoformat(),
                "requester": a.requester.name,
                "section": a.section,
                "subject": a.subject,
                "periods": periods_label(a.periods),
                "kind": taker.kind if taker else "",
                "taken_by": taker.candidate.name if taker else "",
                "status": a.status,
                "reason": a.reason,
            }
        )
    duties = db.query(Duty).filter(Duty.date >= start, Duty.date <= end).order_by(Duty.date, Duty.period).all()
    report = fairness.fairness_report(db, end)
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "summary": summary,
        "totals": {k: round(sum(r[k] for r in summary), 2) for k, _ in SUMMARY_COLUMNS} | {"load": round(sum(loads), 2)},
        "fairness": {"score": fairness.score_from_gini(fairness.gini(loads)), "gini": round(fairness.gini(loads), 3),
                     "mean": round(mean, 2), "sd": round(sd, 2)},
        "trend": report["trend"],
        "adjustments": adj_rows,
        "adjustment_counts": {
            "total": len(adj_rows),
            "accepted": sum(1 for r in adj_rows if r["status"] == "accepted"),
            "swaps": sum(1 for r in adj_rows if r["kind"] == "swap"),
            "substitutions": sum(1 for r in adj_rows if r["kind"] == "substitute"),
        },
        "duties": [
            {"date": d.date.isoformat(), "faculty": db.get(Faculty, d.faculty_id).name, "period": d.period, "kind": d.kind}
            for d in duties
        ],
        "weights": workload.weights(db),
    }


def report_workbook(db: Session, start: date, end: date) -> bytes:
    data = report_data(db, start, end)
    wb = Workbook()
    ws = wb.active
    ws.title = "Load summary"
    _sheet(
        ws,
        ["Faculty", "Designation"] + [label for _, label in SUMMARY_COLUMNS] + ["Weighted load", "Share %", "Flag"],
        [[r["name"], r["designation"]] + [r[k] for k, _ in SUMMARY_COLUMNS] + [r["load"], r["share"], r["flag"]]
         for r in data["summary"]],
        ["TOTAL", ""] + [data["totals"][k] for k, _ in SUMMARY_COLUMNS] + [data["totals"]["load"], 100, ""],
    )
    ws2 = wb.create_sheet("Adjustments")
    _sheet(
        ws2,
        ["Date", "Requested by", "Section", "Subject", "Periods", "Kind", "Taken by", "Status", "Reason"],
        [[r["date"], r["requester"], r["section"], r["subject"], r["periods"], r["kind"], r["taken_by"],
          r["status"], r["reason"]] for r in data["adjustments"]],
    )
    ws3 = wb.create_sheet("Duties")
    _sheet(ws3, ["Date", "Faculty", "Period", "Duty"],
           [[d["date"], d["faculty"], d["period"], d["kind"]] for d in data["duties"]])
    ws4 = wb.create_sheet("Fairness trend")
    _sheet(ws4, ["Window start", "Window end", "Fairness score (0–100)", "Gini index", "Mean load"],
           [[t["start"], t["end"], t["score"], t["gini"], t["mean"]] for t in data["trend"]])
    ws5 = wb.create_sheet("About")
    ws5.append(["Report", "Faculty workload, duty and class adjustment statistics (NAAC/NBA)"])
    ws5.append(["Date range", f"{start.isoformat()} to {end.isoformat()}"])
    ws5.append(["Fairness score", data["fairness"]["score"]])
    ws5.append(["Gini index", data["fairness"]["gini"]])
    ws5.append(["Weights", ", ".join(f"{k} {v}" for k, v in data["weights"].items())])
    return _to_bytes(wb)
