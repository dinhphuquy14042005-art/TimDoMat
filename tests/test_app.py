import sqlite3

import pytest

from app import create_app
from init_db import initialize_database
from recommend import analyze_claim


@pytest.fixture
def client(tmp_path):
    database = tmp_path / "test.sqlite3"
    initialize_database(database, "admin@gmail.com", "admin-pass-123")
    application = create_app(database, secret_key="test-session-secret")
    application.config.update(TESTING=True)
    with application.test_client() as test_client:
        yield test_client


def api(client, method, path, data=None, csrf=True):
    token = client.get("/api/csrf").get_json()["csrf_token"]
    headers = {"X-CSRF-Token": token} if csrf else {}
    return client.open(path, method=method, json=data, headers=headers)


def test_frontend_is_served_from_organized_folders(client):
    page = client.get("/")
    script = client.get("/static/client.js")
    stylesheet = client.get("/static/style.css")

    assert page.status_code == 200
    assert b"<title>" in page.data
    assert b'/static/style.css' in page.data
    assert script.status_code == 200
    assert b'"use strict"' in script.data
    assert stylesheet.status_code == 200
    assert b"--green:" in stylesheet.data


def register(client, email, name):
    response = api(
        client,
        "POST",
        "/api/register",
        {
            "display_name": name,
            "email": email,
            "password": "valid-password",
            "phone": "0912345678",
        },
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["user"]


def create_post(client, post_type, title, district="Hải Châu", location="Chợ Hàn"):
    return api(
        client,
        "POST",
        "/api/posts",
        {
            "type": post_type,
            "category": "Ví & túi",
            "title": title,
            "description": "Mô tả món đồ kiểm thử có đủ độ dài.",
            "district": district,
            "location": location,
            "date": "2026-11-14",
            "phone": "0912345678",
            "private_clue": "Vật nhỏ màu xanh nằm trong ngăn phụ của ví.",
        },
    )


def test_one_user_can_post_both_types_and_owner_can_verify(client):
    user = register(client, "finder@example.test", "Người dùng")
    assert user["roles"] == ["user"]
    found = create_post(client, "found", "Ví tìm thấy")
    assert found.status_code == 201
    post_id = found.get_json()["post"]["id"]
    lost = create_post(client, "lost", "Mất ví thử nghiệm")
    assert lost.status_code == 201
    lost_id = lost.get_json()["post"]["id"]

    register(client, "owner@example.test", "Người dùng khác")
    public = client.get("/api/posts").get_json()["posts"]
    assert len(public) == 2
    found_public = next(post for post in public if post["id"] == post_id)
    assert "claimant_user_id" not in found_public
    assert "private_clue" not in found_public
    assert "phone" not in found_public
    request_data = {"details": "Có thẻ nhỏ màu xanh ở ngăn phụ.", "phone": "0987654321"}
    claim = api(client, "POST", f"/api/posts/{post_id}/verifications", request_data)
    assert claim.status_code == 201
    assert set(claim.get_json()["request"]) == {"id", "status"}
    request_id = claim.get_json()["request"]["id"]
    assert api(client, "POST", f"/api/posts/{post_id}/verifications", request_data).status_code == 409
    own_requests = client.get("/api/my/verifications").get_json()["requests"]
    assert own_requests[0]["contact_phone"] is None

    assert client.get(f"/api/posts/{post_id}/verifications").status_code == 404
    api(client, "POST", "/api/logout")
    login = api(
        client,
        "POST",
        "/api/login",
        {"email": "finder@example.test", "password": "valid-password"},
    )
    assert login.status_code == 200
    inbox = client.get(f"/api/posts/{post_id}/verifications").get_json()["requests"]
    assert inbox[0]["details"] == request_data["details"]
    assert inbox[0]["risk_level"] == "low"
    assert inbox[0]["contact_phone"] is None
    assert "risk_reasons" in inbox[0]
    reviewed = api(client, "PATCH", f"/api/verifications/{request_id}", {"status": "accepted"})
    assert reviewed.status_code == 200
    remaining = client.get("/api/posts").get_json()["posts"]
    assert [post["id"] for post in remaining] == [lost_id]
    api(client, "POST", "/api/logout")
    api(
        client,
        "POST",
        "/api/login",
        {"email": "owner@example.test", "password": "valid-password"},
    )
    own_requests = client.get("/api/my/verifications").get_json()["requests"]
    assert own_requests[0]["status"] == "accepted"
    assert own_requests[0]["contact_phone"] == "0912345678"


def test_any_user_can_respond_to_lost_post_and_contact_is_released_after_acceptance(client):
    register(client, "owner@example.test", "Người dùng")
    lost = create_post(client, "lost", "Mất ví thử nghiệm")
    assert lost.status_code == 201
    post_id = lost.get_json()["post"]["id"]

    register(client, "finder@example.test", "Người dùng khác")
    response = api(
        client,
        "POST",
        f"/api/posts/{post_id}/verifications",
        {
            "details": "Tìm thấy ví có vật nhỏ màu xanh nằm trong ngăn phụ.",
            "phone": "0987654321",
            "meeting_location": "Sảnh trung tâm thương mại",
            "meeting_at": "2026-11-17T23:00",
            "meeting_is_public": False,
        },
    )
    assert response.status_code == 201
    request_id = response.get_json()["request"]["id"]
    assert client.get("/api/my/verifications").get_json()["requests"][0]["contact_phone"] is None

    api(client, "POST", "/api/logout")
    api(
        client,
        "POST",
        "/api/login",
        {"email": "owner@example.test", "password": "valid-password"},
    )
    inbox = client.get(f"/api/posts/{post_id}/verifications").get_json()["requests"]
    assert inbox[0]["contact_phone"] is None
    assert inbox[0]["risk_level"] == "low"
    assert inbox[0]["meeting_location"] == "Sảnh trung tâm thương mại"
    assert inbox[0]["meeting_at"] == "2026-11-17T23:00"
    assert inbox[0]["meeting_safety_warning"] == 1
    accepted = api(client, "PATCH", f"/api/verifications/{request_id}", {"status": "accepted"})
    assert accepted.status_code == 200
    assert client.get("/api/posts").get_json()["posts"] == []


def test_meeting_safety_warning_requires_both_late_time_and_unconfirmed_public_place(client):
    register(client, "owner@example.test", "Người dùng")
    post_ids = [
        create_post(client, "lost", "Mất ví thử nghiệm").get_json()["post"]["id"]
        for _ in range(5)
    ]
    register(client, "finder@example.test", "Người nhặt")
    cases = [
        ("2026-11-17T23:00", False, True),
        ("2026-11-17T23:00", True, False),
        ("2026-11-17T18:00", False, False),
        ("2026-11-17T06:00", False, False),
        ("2026-11-17T22:00", False, False),
    ]
    for post_id, (meeting_at, meeting_is_public, expected_warning) in zip(post_ids, cases):
        response = api(
            client,
            "POST",
            f"/api/posts/{post_id}/verifications",
            {
                "details": "Tìm thấy ví có vật nhỏ màu xanh nằm trong ngăn phụ.",
                "phone": "0987654321",
                "meeting_location": "Quán cà phê trung tâm",
                "meeting_at": meeting_at,
                "meeting_is_public": meeting_is_public,
            },
        )
        assert response.status_code == 201

    api(client, "POST", "/api/logout")
    api(
        client,
        "POST",
        "/api/login",
        {"email": "owner@example.test", "password": "valid-password"},
    )
    for post_id, (_, _, expected_warning) in zip(post_ids, cases):
        inbox = client.get(f"/api/posts/{post_id}/verifications").get_json()["requests"]
        assert inbox[0]["meeting_safety_warning"] == int(expected_warning)


def test_admin_login_moderation_and_audit(client):
    api(
        client,
        "POST",
        "/api/login",
        {"email": "admin@gmail.com", "password": "admin-pass-123"},
    )
    assert client.get("/api/admin/overview").get_json()["overview"]["users"] == 1

    register(client, "finder@example.test", "Người dùng")
    post = create_post(client, "found", "Tin cần ẩn").get_json()["post"]
    api(client, "POST", "/api/logout")
    api(
        client,
        "POST",
        "/api/login",
        {"email": "admin@gmail.com", "password": "admin-pass-123"},
    )
    users = client.get("/api/admin/users").get_json()["users"]
    regular_user = next(user for user in users if user["email"] == "finder@example.test")
    assert regular_user["roles"] == ["user"]
    response = api(client, "PATCH", f"/api/admin/posts/{post['id']}", {"status": "hidden"})
    assert response.status_code == 200
    assert client.get("/api/posts").get_json()["posts"] == []
    with sqlite3.connect(client.application.config["DATABASE"]) as connection:
        assert connection.execute("SELECT action FROM admin_audit_log").fetchall() == [
            ("set_post_status",)
        ]


def test_csrf_required_for_mutations(client):
    response = client.post(
        "/api/register",
        json={
            "display_name": "Người dùng",
            "email": "user@example.test",
            "password": "valid-password",
            "phone": "0912345678",
        },
    )
    assert response.status_code == 403


def test_invalid_post_type_is_rejected(client):
    register(client, "finder@example.test", "Người dùng")
    response = api(
        client,
        "POST",
        "/api/posts",
        {
            "type": ["found"],
            "category": "Khác",
            "title": "Tin không hợp lệ",
            "description": "Mô tả tin không hợp lệ.",
            "district": "Hải Châu",
            "location": "Đà Nẵng",
            "date": "2026-11-14",
            "phone": "0912345678",
        },
    )
    assert response.status_code == 400


def test_lost_post_accepts_either_district_or_street_location(client):
    register(client, "finder@example.test", "Người dùng")

    district_only = create_post(client, "lost", "Mất ví ở quận", location="")
    assert district_only.status_code == 201
    assert district_only.get_json()["post"]["district"] == "Hải Châu"
    assert district_only.get_json()["post"]["location"] == ""

    street_only = create_post(
        client,
        "lost",
        "Mất ví trên đường",
        district="",
        location="Đường Nguyễn Văn Linh",
    )
    assert street_only.status_code == 201
    assert street_only.get_json()["post"]["district"] == "Chưa rõ"
    assert street_only.get_json()["post"]["location"] == "Đường Nguyễn Văn Linh"

    no_location = create_post(client, "lost", "Mất ví chưa rõ nơi", district="", location="")
    assert no_location.status_code == 400


def test_local_fraud_score_flags_generic_and_unmatched_claims():
    clue = "Móc khóa hình cá màu đỏ nằm trong ngăn khóa kéo."
    matching = analyze_claim(clue, "Móc khóa hình cá màu đỏ ở trong ngăn khóa kéo.")
    suspicious = analyze_claim(clue, "Đồ của tôi, đúng mô tả.")

    assert matching["risk_level"] == "low"
    assert suspicious["risk_level"] == "high"
    assert any("đặc điểm riêng" in reason for reason in suspicious["risk_reasons"])
