"""Demo data. Run from backend/:  python -m app.seed   (this RESETS the database).

Everything is anonymised (Faculty 1…12) and synthetic. Loads are deliberately uneven so the
fairness view has something to show: Faculty 3 and 7 are overloaded, 11 and 12 underused."""
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import db as db_module
from app.config import get_settings
from app.models import (
    Adjustment,
    AdjustmentCandidate,
    Asset,
    CategoryAssignee,
    Department,
    Duty,
    Faculty,
    Leave,
    Location,
    LogDay,
    Ticket,
    TicketEvent,
    TimetableSlot,
    User,
    WorkLog,
)
from app.services import clock
from app.services.adjustments import _write_logs
from app.services.auth import hash_password
from app.services.candidates import find_candidates
from app.services.settings_store import get_setting, seed_defaults
from app.services.timetable import DAY_PERIODS, DayView

PASSWORD = "demo1234"
DOMAIN = "educrew.local"
HEAVY = {3, 7}  # overloaded on purpose
LIGHT = {11, 12}  # underused on purpose

FACULTY = [
    (1, "Professor", ["Machine Learning", "Deep Learning", "Natural Language Processing"]),
    (2, "Associate Professor", ["Computer Networks", "Cloud Computing"]),
    (3, "Associate Professor", ["Theory of Computation", "Machine Learning", "Cloud Computing"]),
    (4, "Assistant Professor", ["Software Engineering", "Cloud Computing", "Project Management"]),
    (5, "Assistant Professor", ["Research Methodology", "Software Engineering", "Theory of Computation", "Machine Learning"]),
    (6, "Assistant Professor", ["Computer Networks", "Natural Language Processing", "Machine Learning"]),
    (7, "Associate Professor", ["Theory of Computation", "Deep Learning", "Machine Learning"]),
    (8, "Assistant Professor", ["Software Engineering", "Deep Learning", "Machine Learning"]),
    (9, "Assistant Professor", ["Natural Language Processing", "Deep Learning", "Machine Learning"]),
    (10, "Assistant Professor", ["Big Data Analytics", "Cloud Computing", "Deep Learning"]),
    (11, "Assistant Professor", ["Project Management", "Software Engineering", "Research Methodology", "Cloud Computing", "Computer Networks"]),
    (12, "Assistant Professor", ["Project Management", "Big Data Analytics", "Cloud Computing", "Deep Learning", "Machine Learning"]),
]

# (section, subject, type, faculty no., count) — count is periods/week for theory, 2-period blocks/week for labs
COURSES = [
    ("5A", "Machine Learning", "theory", 1, 5), ("5A", "Computer Networks", "theory", 2, 4),
    ("5A", "Theory of Computation", "theory", 3, 4), ("5A", "Software Engineering", "theory", 4, 4),
    ("5A", "Research Methodology", "theory", 5, 3), ("5A", "Machine Learning Lab", "lab", 1, 1), ("5A", "Computer Networks Lab", "lab", 6, 1),
    ("5B", "Machine Learning", "theory", 3, 4), ("5B", "Computer Networks", "theory", 2, 4),
    ("5B", "Theory of Computation", "theory", 7, 4), ("5B", "Software Engineering", "theory", 8, 4),
    ("5B", "Research Methodology", "theory", 5, 3), ("5B", "Machine Learning Lab", "lab", 3, 1), ("5B", "Computer Networks Lab", "lab", 2, 1),
    ("7A", "Deep Learning", "theory", 7, 4), ("7A", "Natural Language Processing", "theory", 9, 4),
    ("7A", "Big Data Analytics", "theory", 10, 4), ("7A", "Cloud Computing", "theory", 3, 4),
    ("7A", "Project Management", "theory", 11, 3), ("7A", "Deep Learning Lab", "lab", 7, 1), ("7A", "Natural Language Processing Lab", "lab", 9, 1),
    ("7B", "Deep Learning", "theory", 7, 4), ("7B", "Natural Language Processing", "theory", 6, 4),
    ("7B", "Big Data Analytics", "theory", 10, 4), ("7B", "Cloud Computing", "theory", 4, 4),
    ("7B", "Project Management", "theory", 12, 3), ("7B", "Deep Learning Lab", "lab", 8, 1), ("7B", "Natural Language Processing Lab", "lab", 6, 1),
]

SECTION_ROOMS = {"5A": "BLK-A-F1-R101", "5B": "BLK-A-F1-R102", "7A": "BLK-A-F2-R201", "7B": "BLK-A-F2-R202"}
LAB_ROOMS = {"Machine Learning Lab": "BLK-A-F1-LAB105", "Deep Learning Lab": "BLK-A-F1-LAB105", "Computer Networks Lab": "BLK-A-F2-LAB205", "Natural Language Processing Lab": "BLK-A-F2-LAB205"}

# (code, floor, room name, kind, corridor side, order, assets)
LOCATIONS = [
    ("BLK-A-F1-R101", 1, "Classroom 5A", "classroom", "N", 1, ["Projector", "6 ceiling fans", "Tube lights", "Benches"]),
    ("BLK-A-F1-R102", 1, "Classroom 5B", "classroom", "N", 2, ["Projector", "6 ceiling fans", "Tube lights", "Benches"]),
    ("BLK-A-F1-R103", 1, "Seminar Hall", "classroom", "N", 3, ["Sound system", "Projector", "Air conditioner"]),
    ("BLK-A-F1-R104", 1, "Staff Room", "office", "N", 4, ["Ceiling fans", "Water dispenser"]),
    ("BLK-A-F1-LAB105", 1, "AI Lab", "lab", "N", 5, ["40 PCs", "Projector", "Air conditioner", "Wi-Fi access point"]),
    ("BLK-A-F1-R106", 1, "HOD Office", "office", "S", 1, ["Air conditioner", "Printer"]),
    ("BLK-A-F1-R107", 1, "Faculty Cabins", "office", "S", 2, ["Ceiling fans", "Network points"]),
    ("BLK-A-F1-LIFT", 1, "Lift landing", "lift", "S", 3, ["Lift car", "Call buttons"]),
    ("BLK-A-F1-WRM", 1, "Washroom (Men)", "washroom", "S", 4, ["Taps", "Flush tanks", "Exhaust fan"]),
    ("BLK-A-F1-WRW", 1, "Washroom (Women)", "washroom", "S", 5, ["Taps", "Flush tanks", "Exhaust fan"]),
    ("BLK-A-F2-R201", 2, "Classroom 7A", "classroom", "N", 1, ["Projector", "6 ceiling fans", "Tube lights", "Benches"]),
    ("BLK-A-F2-R202", 2, "Classroom 7B", "classroom", "N", 2, ["Projector", "6 ceiling fans", "Tube lights", "Benches"]),
    ("BLK-A-F2-R203", 2, "Tutorial Room", "classroom", "N", 3, ["Smart board", "Ceiling fans"]),
    ("BLK-A-F2-R204", 2, "Classroom (spare)", "classroom", "N", 4, ["Projector", "Ceiling fans"]),
    ("BLK-A-F2-LAB205", 2, "Networks Lab", "lab", "N", 5, ["36 PCs", "Network rack", "Air conditioner"]),
    ("BLK-A-F2-R206", 2, "Project Lab", "lab", "S", 1, ["12 PCs", "GPU server"]),
    ("BLK-A-F2-R207", 2, "Store Room", "office", "S", 2, ["Shelves"]),
    ("BLK-A-F2-LIFT", 2, "Lift landing", "lift", "S", 3, ["Call buttons"]),
    ("BLK-A-F2-WRM", 2, "Washroom (Men)", "washroom", "S", 4, ["Taps", "Flush tanks"]),
    ("BLK-A-F2-WRW", 2, "Washroom (Women)", "washroom", "S", 5, ["Taps", "Flush tanks"]),
]

INCHARGES = [
    ("electrical", "Electrical In-charge"),
    ("plumbing", "Plumbing In-charge"),
    ("housekeeping", "Housekeeping Supervisor"),
    ("it", "IT In-charge"),
    ("civil", "Civil In-charge"),
]

# (location, category, priority, status, hours ago, description, reporter, resolved hours ago, overdue)
TICKETS = [
    ("BLK-A-F1-R101", "electrical", "normal", "in_progress", 30, "Two tube lights near the back benches are not working.", "Student, 5A", None),
    ("BLK-A-F1-WRM", "plumbing", "high", "assigned", 5, "Flush not working in the second cubicle.", None, None),
    ("BLK-A-F1-LAB105", "it", "high", "new", 2, "Three systems in row 2 are not booting. Lab exam on Friday.", "Lab assistant", None),
    ("BLK-A-F2-R202", "civil", "normal", "assigned", 20, "Door handle is broken, the door does not latch.", None, None),
    ("BLK-A-F2-WRW", "housekeeping", "high", "in_progress", 3, "Washroom not cleaned since morning, bins overflowing.", None, None),
    ("BLK-A-F1-LIFT", "electrical", "critical", "assigned", 6, "Lift stops between floors and jerks before opening.", "Faculty 4", None),
    ("BLK-A-F2-R203", "it", "high", "resolved", 50, "Projector is not detecting the HDMI input.", None, 40),
    ("BLK-A-F1-R104", "electrical", "critical", "resolved", 26, "Fan regulator sparking when switched on.", "Faculty 9", 24),
    ("BLK-A-F2-R204", "civil", "high", "assigned", 30, "Ceiling plaster cracking above the front row.", None, None),
    ("BLK-A-F1-WRW", "plumbing", "normal", "resolved", 80, "Tap leaking continuously in the first washbasin.", None, 70),
    ("BLK-A-F2-LAB205", "it", "normal", "new", 1, "Wi-Fi drops every few minutes in the lab.", "Student, 7B", None),
    ("BLK-A-F1-R102", "housekeeping", "normal", "rejected", 60, "Paint spilled near the entrance.", None, None),
    ("BLK-A-F2-R201", "electrical", "normal", "in_progress", 10, "Socket near the podium has no power.", None, None),
    ("BLK-A-F1-R106", "civil", "normal", "resolved", 100, "Window glass cracked in the HOD office.", None, 90),
    ("BLK-A-F2-R207", "housekeeping", "normal", "assigned", 15, "Cobwebs and dust on the store room shelves.", None, None),
]

TOPICS = {
    "Machine Learning": ["Linear regression", "Logistic regression", "Decision trees", "Bias–variance trade-off", "SVM", "k-means clustering"],
    "Computer Networks": ["OSI model", "TCP flow control", "IP addressing", "Routing algorithms", "Congestion control"],
    "Theory of Computation": ["DFA minimisation", "Regular expressions", "Pumping lemma", "Context-free grammars", "Turing machines"],
    "Software Engineering": ["Requirements elicitation", "UML diagrams", "Agile and Scrum", "Testing strategies", "Design patterns"],
    "Research Methodology": ["Literature review", "Research design", "Sampling", "Writing a paper"],
    "Deep Learning": ["Backpropagation", "CNNs", "RNNs and LSTMs", "Regularisation", "Transformers"],
    "Natural Language Processing": ["Tokenisation", "Word embeddings", "Language models", "Named entity recognition", "Attention"],
    "Big Data Analytics": ["Hadoop and HDFS", "MapReduce", "Spark RDDs", "NoSQL stores"],
    "Cloud Computing": ["Virtualisation", "Service models", "Containers", "Cloud security"],
    "Project Management": ["Project charter", "Gantt charts", "Risk management", "Review 1 preparation"],
}
REASONS = ["Attending an FDP at VTU", "Medical appointment", "External examiner duty", "NBA committee meeting"]


def _build_timetable(rng: random.Random) -> Optional[list[tuple]]:
    fac_busy, sec_busy, room_busy = set(), set(), set()
    out: list[tuple] = []

    def free(fn, sec, room, d, p):
        return (fn, d, p) not in fac_busy and (sec, d, p) not in sec_busy and (room, d, p) not in room_busy

    def place(sec, subj, typ, fn, room, d, p):
        fac_busy.add((fn, d, p))
        sec_busy.add((sec, d, p))
        room_busy.add((room, d, p))
        out.append((sec, subj, typ, fn, room, d, p))

    labs = [c for c in COURSES if c[2] == "lab"]
    rng.shuffle(labs)
    lab_days: dict[str, set] = defaultdict(set)
    for sec, subj, typ, fn, count in labs:
        room = LAB_ROOMS[subj]
        options = [(d, b) for d in range(6) for b in ((1, 2), (3, 4), (5, 6)) if b[1] <= DAY_PERIODS[d]]
        rng.shuffle(options)
        for _ in range(count):
            for d, block in options:
                if d in lab_days[sec] or not all(free(fn, sec, room, d, p) for p in block):
                    continue
                for p in block:
                    place(sec, subj, typ, fn, room, d, p)
                lab_days[sec].add(d)
                break
            else:
                return None

    theory = [c for c in COURSES if c[2] == "theory"]
    rng.shuffle(theory)
    theory.sort(key=lambda c: -c[4])
    for sec, subj, typ, fn, count in theory:
        room = SECTION_ROOMS[sec]
        days = list(range(6))
        rng.shuffle(days)
        days.sort(key=lambda d: sum(1 for p in range(1, DAY_PERIODS[d] + 1) if (sec, d, p) in sec_busy))
        placed = 0
        for d in days:
            if placed == count:
                break
            periods = list(range(1, DAY_PERIODS[d] + 1))
            rng.shuffle(periods)
            for p in periods:
                if free(fn, sec, room, d, p):
                    place(sec, subj, typ, fn, room, d, p)
                    placed += 1
                    break
        if placed < count:
            return None
    # Faculty 1 is the demo faculty: make sure they teach every working day.
    if {d for (_, _, _, fn, _, d, _) in out if fn == 1} != set(range(6)):
        return None
    return out


def _at(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm))


def seed(db: Session, today: Optional[date] = None) -> dict:
    rng = random.Random(2026)
    now = clock.now()
    today = today or now.date()
    pw = hash_password(PASSWORD)
    seed_defaults(db)

    dept = Department(name="CSE (AI & ML)")
    db.add(dept)
    db.flush()

    def user(name, email, role):
        u = User(name=name, email=f"{email}@{DOMAIN}", password_hash=pw, role=role, dept_id=dept.id)
        db.add(u)
        return u

    hod = user("HOD, CSE (AI & ML)", "hod", "hod")
    estate = user("Estate Officer", "estate", "estate")
    incharges = {cat: user(name, cat, "incharge") for cat, name in INCHARGES}
    faculty: dict[int, Faculty] = {}
    for n, designation, qualified in FACULTY:
        u = user(f"Faculty {n}", f"faculty{n}", "faculty")
        db.flush()
        faculty[n] = Faculty(user_id=u.id, designation=designation, qualified_subjects=qualified)
        db.add(faculty[n])
    db.flush()
    for cat, u in incharges.items():
        db.add(CategoryAssignee(category=cat, user_id=u.id))

    locations: dict[str, Location] = {}
    for code, floor, name, kind, side, order, assets in LOCATIONS:
        loc = Location(code=code, block="A", floor=floor, room_name=name, kind=kind, side=side, sort_order=order)
        db.add(loc)
        db.flush()
        locations[code] = loc
        for asset in assets:
            db.add(Asset(location_id=loc.id, name=asset))

    # ---- timetable
    layout = None
    attempt = 0
    while layout is None:
        layout = _build_timetable(random.Random(1000 + attempt))
        attempt += 1
    for sec, subj, typ, fn, room, d, p in layout:
        db.add(TimetableSlot(faculty_id=faculty[fn].id, section=sec, subject=subj, day=d, period=p,
                             room_id=locations[room].id, type=typ))
    db.flush()

    # ---- duties (past 4 weeks and next week): heavy faculty get many, light faculty none
    duty_kinds = ["Invigilation", "Invigilation", "Exam squad", "Admission desk"]
    for offset in range(-28, 8):
        d = today + timedelta(days=offset)
        if d.weekday() == 6:
            continue
        view = DayView(db, d)
        for n, fac in faculty.items():
            if n in LIGHT:
                continue
            chance = 0.55 if n in HEAVY else 0.08
            if rng.random() < chance:
                free_periods = [p for p in range(1, DAY_PERIODS[d.weekday()] + 1) if p not in view.busy(fac.id)]
                if free_periods:
                    db.add(Duty(faculty_id=fac.id, date=d, period=rng.choice(free_periods), kind=rng.choice(duty_kinds)))
        db.flush()

    # ---- a half-day leave today, so the "not on leave" check is visible
    if today.weekday() != 6:
        view = DayView(db, today)
        for p in (5, 6, 7):
            if p <= DAY_PERIODS[today.weekday()] and p not in view.busy(faculty[11].id):
                db.add(Leave(faculty_id=faculty[11].id, date=today, period=p, reason="Half-day leave"))
    db.flush()

    # ---- past adjustments (accepted), so substitution counts feed the fairness view
    past_adjustments = []
    for k, offset in enumerate((-20, -13, -9, -4)):
        d = today + timedelta(days=offset)
        if d.weekday() == 6:
            d -= timedelta(days=1)
        requester = faculty[3] if k % 2 == 0 else faculty[7]
        units = DayView(db, d).units_of(requester.id)
        if not units:
            continue
        periods, first = units[0]
        adj = Adjustment(requester_id=requester.id, date=d, periods=periods, section=first.section,
                         subject=first.subject, slot_type=first.type, reason=REASONS[k % len(REASONS)],
                         status="open", created_at=_at(d - timedelta(days=1), 15))
        db.add(adj)
        db.flush()
        suggestions = [s for s in find_candidates(db, adj) if s.kind == "substitute" and s.tier == 1]
        if not suggestions:
            db.delete(adj)
            continue
        best = suggestions[0]
        cand = AdjustmentCandidate(adjustment_id=adj.id, candidate_id=best.faculty.id, kind="substitute", rank=1,
                                   score=best.fit, score_breakdown=best.breakdown | {"tier": best.tier},
                                   state="accepted", requested_at=_at(d - timedelta(days=1), 15, 5),
                                   responded_at=_at(d - timedelta(days=1), 15, 40))
        db.add(cand)
        db.flush()
        adj.status = "accepted"
        adj.chosen_candidate_id = cand.id
        past_adjustments.append(adj)
    db.flush()

    # ---- work logs for the past 4 weeks
    weights = get_setting(db, "workload_weights")
    topic_index: dict[tuple, int] = defaultdict(int)

    def topic_for(subject: str, section: str) -> str:
        base = subject.removesuffix(" Lab")
        options = TOPICS.get(base, ["Lecture"])
        i = topic_index[(base, section)]
        topic_index[(base, section)] += 1
        prefix = "Experiment: " if subject.endswith("Lab") else ""
        return prefix + options[i % len(options)]

    def log_day(fac: Faculty, d: date, until_period: int = 7):
        view = DayView(db, d)
        for periods, a in view.units_of(fac.id):
            if a.adjustment_id or periods[0] > until_period:
                continue  # adjustment entries are written by _write_logs below
            db.add(WorkLog(faculty_id=fac.id, date=d, type=a.type, topic=topic_for(a.subject, a.section),
                           units=len(periods), weight=len(periods) * weights[a.type], period=periods[0],
                           section=a.section, subject=a.subject, source_slot_id=a.slot_id,
                           created_by=fac.user_id, created_at=_at(d, 16, 30)))
        for duty in db.query(Duty).filter(Duty.faculty_id == fac.id, Duty.date == d):
            if duty.period <= until_period:
                db.add(WorkLog(faculty_id=fac.id, date=d, type="duty", topic=duty.kind, units=1,
                               weight=weights["duty"], period=duty.period, created_by=fac.user_id,
                               created_at=_at(d, 16, 30)))

    for offset in range(-28, 0):
        d = today + timedelta(days=offset)
        if d.weekday() == 6:
            continue
        for n, fac in faculty.items():
            miss = 0.0 if n in HEAVY else (0.12 if n in LIGHT else 0.04)
            if rng.random() < miss:
                continue
            log_day(fac, d)
            if n in HEAVY and d.weekday() in (1, 3):
                db.add(WorkLog(faculty_id=fac.id, date=d, type="meeting", topic="NBA documentation committee",
                               units=2, weight=2 * weights["meeting"], created_by=fac.user_id,
                               created_at=_at(d, 17)))
            if d.weekday() == 4:
                db.add(WorkLog(faculty_id=fac.id, date=d, type="meeting", topic="Department meeting", units=1,
                               weight=weights["meeting"], created_by=fac.user_id, created_at=_at(d, 17)))
            db.add(LogDay(faculty_id=fac.id, date=d, submitted_at=_at(d, 16, 30 + rng.randint(0, 25))))
        db.flush()
    for adj in past_adjustments:
        cand = next(c for c in adj.candidates if c.state == "accepted")
        _write_logs(db, adj, cand)

    # ---- today: half the department has already logged; Faculty 1 (the demo login) has not
    if today.weekday() != 6:
        for n in (2, 4, 6, 8, 10, 12):
            log_day(faculty[n], today, until_period=4)
            db.add(LogDay(faculty_id=faculty[n].id, date=today, submitted_at=now - timedelta(minutes=7 * n)))
    db.flush()

    # ---- tickets
    hours = get_setting(db, "deadline_hours")
    for i, (code, cat, priority, status, ago, text, reporter, resolved_ago) in enumerate(TICKETS):
        loc = locations[code]
        owner = incharges[cat]
        created = now - timedelta(hours=ago)
        deadline = created + timedelta(hours=hours[priority])
        t = Ticket(
            ref="".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6)),
            location_id=loc.id, category=cat, priority=priority, status=status, description=text,
            summary=text.split(".")[0][:90], ai_category=cat, ai_priority=priority,
            ai_confidence=round(rng.uniform(0.62, 0.93), 2), ai_source="rules", reporter_name=reporter,
            assigned_to=owner.id, deadline_at=deadline, created_at=created, updated_at=created,
        )
        db.add(t)
        db.flush()
        events = [
            TicketEvent(ticket_id=t.id, actor=reporter or "Reporter (QR)", action="created",
                        note=f"Triage by keyword rules: {cat} / {priority}", created_at=created),
            TicketEvent(ticket_id=t.id, actor="System", action="routed", note=f"Routed to {owner.name}",
                        created_at=created),
        ]
        step = created + timedelta(minutes=25)
        if status in ("assigned", "in_progress", "resolved"):
            t.worker = rng.choice(["Ravi (technician)", "Manjunath", "Suresh", "Outsourced team"])
            events.append(TicketEvent(ticket_id=t.id, actor=owner.name, action="worker",
                                      note=f"Work given to {t.worker}", created_at=step))
            events.append(TicketEvent(ticket_id=t.id, actor=owner.name, action="status_changed",
                                      note="New → Assigned", created_at=step))
        if status in ("in_progress", "resolved"):
            step += timedelta(minutes=50)
            events.append(TicketEvent(ticket_id=t.id, actor=owner.name, action="status_changed",
                                      note="Assigned → In progress", created_at=step))
        if status == "resolved":
            t.resolved_at = now - timedelta(hours=resolved_ago)
            events.append(TicketEvent(ticket_id=t.id, actor=owner.name, action="status_changed",
                                      note="In progress → Resolved", created_at=t.resolved_at))
        if status == "rejected":
            t.rejection_reason = "Already cleaned during the morning round"
            events.append(TicketEvent(ticket_id=t.id, actor=owner.name, action="status_changed",
                                      note=f"New → Rejected: {t.rejection_reason}", created_at=step))
        if t.is_open and deadline <= now:
            t.reminded_at = created + (deadline - created) * 0.75
            t.escalated_at = deadline + timedelta(minutes=1)
            events.append(TicketEvent(ticket_id=t.id, actor="System", action="reminder",
                                      note=f"Reminder sent: due {deadline:%d %b %H:%M}", created_at=t.reminded_at))
            events.append(TicketEvent(ticket_id=t.id, actor="System", action="escalated",
                                      note="Deadline passed; escalated to the Estate Officer", created_at=t.escalated_at))
        t.updated_at = max(e.created_at for e in events)
        db.add_all(events)
    db.commit()
    return {
        "users": db.query(User).count(),
        "faculty": len(faculty),
        "slots": len(layout),
        "locations": len(locations),
        "tickets": len(TICKETS),
        "work_logs": db.query(WorkLog).count(),
        "duties": db.query(Duty).count(),
        "adjustments": len(past_adjustments),
    }


def run_seed(today: Optional[date] = None) -> dict:
    if db_module.engine is None:
        db_module.init_engine(get_settings().database_url)
    db_module.drop_all()
    db_module.create_all()
    session = db_module.SessionLocal()
    try:
        return seed(session, today)
    finally:
        session.close()


if __name__ == "__main__":
    counts = run_seed()
    print("Demo data loaded:", ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"\nLogins (password for all: {PASSWORD})")
    for role, email in [("HOD", "hod"), ("Faculty (demo)", "faculty1"), ("Faculty", "faculty2 … faculty12"),
                        ("In-charges", "electrical, plumbing, housekeeping, it, civil"), ("Estate Officer", "estate")]:
        print(f"  {role:15} {email}@{DOMAIN}")
