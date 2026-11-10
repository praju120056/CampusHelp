from tests.conftest import auth


def test_login_returns_token_and_role(client):
    res = client.post("/auth/login", json={"email": "hod@educrew.local", "password": "demo1234"})
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "hod"


def test_wrong_password_is_rejected(client):
    res = client.post("/auth/login", json={"email": "hod@educrew.local", "password": "nope"})
    assert res.status_code == 401


def test_protected_route_needs_login(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/analytics/fairness").status_code == 401


def test_role_checks(client):
    faculty = auth(client, "faculty1")
    assert client.get("/analytics/fairness", headers=faculty).status_code == 403
    assert client.get("/tickets", headers=faculty).status_code == 403
    hod = auth(client, "hod")
    assert client.get("/analytics/fairness", headers=hod).status_code == 200
    assert client.patch("/tickets/XXXXXX", json={"status": "resolved"}, headers=hod).status_code == 403


def test_public_endpoints_need_no_login(client):
    res = client.get("/locations/BLK-A-F1-R101")
    assert res.status_code == 200
    assert res.json()["room_name"] == "Classroom 5A"


def test_stream_rejects_missing_or_bad_token(client):
    assert client.get("/stream/tickets").status_code == 422
    assert client.get("/stream/tickets?token=bad").status_code == 401
