from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models import Faculty, Setting
from app.services import adjustments as adj_service
from app.services import clock, fairness, workload
from app.services.settings_store import set_setting
from app.services.timetable import DayView
from tests.conftest import auth


def test_gini_known_values():
    assert fairness.gini([5, 5, 5, 5]) == 0
    assert fairness.gini([0, 0, 0, 10]) == pytest.approx(0.75)
    assert fairness.gini([]) == 0
    assert fairness.gini([0, 0]) == 0
    assert 0 < fairness.gini([1, 2, 3, 4]) < fairness.gini([1, 1, 1, 10])


def test_flags_use_mean_plus_minus_one_sd():
    mean, sd = fairness.mean_sd([2, 4, 4, 4, 5, 5, 7, 9])
    assert (mean, sd) == (5, 2)
    assert fairness.classify(7.1, mean, sd) == "overloaded"
    assert fairness.classify(7.0, mean, sd) == "normal"
    assert fairness.classify(2.9, mean, sd) == "underused"
    assert fairness.classify(5, 5, 0) == "normal"


def test_burnout_needs_three_consecutive_weeks():
    assert fairness.longest_run(["overloaded", "overloaded", "normal", "overloaded"]) == 2
    assert fairness.longest_run(["normal", "overloaded", "overloaded", "overloaded"]) == 3


def test_seeded_department_shows_the_intended_story(db):
    report = fairness.fairness_report(db)
    by_name = {r["name"]: r for r in report["faculty"]}
    assert by_name["Faculty 3"]["flag"] == by_name["Faculty 7"]["flag"] == "overloaded"
    assert by_name["Faculty 11"]["flag"] == by_name["Faculty 12"]["flag"] == "underused"
    assert by_name["Faculty 3"]["burnout"] or by_name["Faculty 7"]["burnout"]
    assert 0 < report["score"] < 100
    assert all(t["score"] is not None for t in report["trend"])  # 4 weeks of seeded logs


def test_weights_come_from_settings(db):
    start, end = clock.today().replace(day=1), clock.today()
    before = workload.weighted_loads(db, start, end)
    set_setting(db, "workload_weights", {"lab": 3.0})
    db.commit()
    after = workload.weighted_loads(db, start, end)
    assert after != before
    assert sum(after.values()) > sum(before.values())


def test_substitution_counts_on_top_of_own_classes(db):
    d = clock.today()
    fac = db.query(Faculty).first()
    periods, _ = DayView(db, d).units_of(fac.id)[0]
    adj = adj_service.create_adjustments(db, fac, fac.user, d, periods, "away")[0]
    cand = next(c for c in adj.candidates if c.kind == "substitute")
    before = workload.weighted_loads(db, d, d).get(cand.candidate_id, 0.0)
    adj_service.choose(db, adj, cand.id, fac.user)
    adj_service.respond(db, cand, "accept")
    after = workload.weighted_loads(db, d, d).get(cand.candidate_id, 0.0)
    w = workload.weights(db)
    assert after - before == pytest.approx(len(periods) * w["substitution"])


def test_saving_a_log_moves_the_fairness_score(client, db):
    hod = auth(client, "hod")
    before = client.get("/analytics/fairness", headers=hod).json()
    faculty12 = auth(client, "faculty12")
    day = client.get("/logs/prefill", headers=faculty12).json()
    entries = [e for e in day["entries"]] + [{"type": "duty", "units": 6, "topic": "Exam squad (all day)"}]
    client.post("/logs", json={"date": day["date"], "entries": entries}, headers=faculty12)
    after = client.get("/analytics/fairness", headers=hod).json()
    load = lambda r, n: next(f["load"] for f in r["faculty"] if f["name"] == n)  # noqa: E731
    assert load(after, "Faculty 12") > load(before, "Faculty 12")
    assert after["score"] != before["score"]


def test_excel_totals_match_the_dashboard(client):
    hod = auth(client, "hod")
    report = client.get("/analytics/fairness", headers=hod).json()
    window = report["window"]
    res = client.get(f"/exports/logs.xlsx?start={window['start']}&end={window['end']}", headers=hod)
    assert res.status_code == 200
    wb = load_workbook(BytesIO(res.content))
    summary = wb["Summary"]
    header = [c.value for c in summary[1]]
    name_col, load_col = header.index("Faculty"), header.index("Weighted load")
    excel = {row[name_col]: row[load_col] for row in summary.iter_rows(min_row=2, values_only=True) if row[0] != "TOTAL"}
    for f in report["faculty"]:
        assert excel[f["name"]] == pytest.approx(f["load"], abs=0.05)
    logs = wb["Logs"]
    total_row = [r for r in logs.iter_rows(values_only=True) if r[0] == "TOTAL"][0]
    assert total_row[10] == pytest.approx(sum(f["load"] for f in report["faculty"]), abs=0.1)


def test_report_workbook_has_naac_sheets(client):
    res = client.get("/exports/report.xlsx", headers=auth(client, "hod"))
    wb = load_workbook(BytesIO(res.content))
    assert {"Load summary", "Adjustments", "Duties", "Fairness trend"} <= set(wb.sheetnames)
