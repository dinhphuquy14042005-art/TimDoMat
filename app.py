import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import date, datetime, time
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request, session

from database import DEFAULT_DATABASE, PROJECT_ROOT, connect_database, initialize_schema
from recommend import analyze_claim, is_useful_clue


PASSWORD_ITERATIONS = 600_000
PHONE_PATTERN = re.compile(r"^[0-9]{8,15}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DISTRICTS = {
    "Hải Châu", "Thanh Khê", "Sơn Trà", "Ngũ Hành Sơn",
    "Liên Chiểu", "Cẩm Lệ", "Hòa Vang",
}
UNKNOWN_DISTRICT = "Chưa rõ"
CATEGORIES = {"Giấy tờ", "Ví & túi", "Điện tử", "Chìa khóa", "Thú cưng", "Khác"}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt_text, expected = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        actual = base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        ).decode("ascii")
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def create_app(database_path: str | Path | None = None, secret_key: str | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.update(
        DATABASE=str(database_path or os.environ.get("DATABASE_PATH", DEFAULT_DATABASE)),
        SECRET_KEY=secret_key or os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "").lower() == "true",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
        MAX_CONTENT_LENGTH=32 * 1024,
    )

    def connect_db() -> sqlite3.Connection:
        return connect_database(app.config["DATABASE"])

    def account_roles(role_names: list[str]) -> list[str]:
        return ["admin"] if "admin" in role_names else ["user"]

    app.teardown_appcontext(lambda error: getattr(g, "db", None) and g.db.close())

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = connect_db()
        return g.db

    with app.app_context():
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        connection = get_db()
        initialize_schema(connection)

    def error(message: str, status: int = 400):
        return jsonify({"error": message}), status

    def body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Nội dung gửi lên không hợp lệ.")
        return data

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        user = get_db().execute(
            "SELECT id, email, display_name, phone, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user or not user["is_active"]:
            session.clear()
            return None
        roles = get_db().execute(
            "SELECT r.name FROM roles r JOIN user_roles ur ON ur.role_id = r.id "
            "WHERE ur.user_id = ? ORDER BY r.name",
            (user_id,),
        ).fetchall()
        result = dict(user)
        result["roles"] = account_roles([row["name"] for row in roles])
        return result

    def user_required(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return error("Vui lòng đăng nhập để tiếp tục.", 401)
            g.current_user = user
            return handler(*args, **kwargs)
        return wrapped

    def admin_required(handler):
        @wraps(handler)
        @user_required
        def wrapped(*args, **kwargs):
            if "admin" not in g.current_user["roles"]:
                return error("Bạn không có quyền quản trị.", 403)
            return handler(*args, **kwargs)
        return wrapped

    def csrf_required(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                return error("Phiên thao tác không hợp lệ. Tải lại trang và thử lại.", 403)
            return handler(*args, **kwargs)
        return wrapped

    def audit(action: str, entity_type: str, entity_id: str, details: str = "") -> None:
        get_db().execute(
            "INSERT INTO admin_audit_log(admin_user_id, action, entity_type, entity_id, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.current_user["id"], action, entity_type, str(entity_id), details[:500]),
        )

    def public_user(user_id: int) -> dict:
        user = get_db().execute(
            "SELECT id, email, display_name, phone, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        roles = get_db().execute(
            "SELECT r.name FROM roles r JOIN user_roles ur ON ur.role_id = r.id "
            "WHERE ur.user_id = ? ORDER BY r.name",
            (user_id,),
        ).fetchall()
        result = dict(user)
        result["roles"] = account_roles([row["name"] for row in roles])
        return result

    def validate_password(password, minimum=8):
        if not isinstance(password, str) or not minimum <= len(password) <= 128:
            raise ValueError(f"Mật khẩu phải có từ {minimum} đến 128 ký tự.")
        return password

    def validate_phone(phone):
        if not isinstance(phone, str) or not PHONE_PATTERN.fullmatch(phone.strip()):
            raise ValueError("Số điện thoại cần có từ 8 đến 15 chữ số.")
        return phone.strip()

    def get_post(post_id):
        return get_db().execute(
            "SELECT p.*, u.display_name AS poster_name FROM posts p "
            "JOIN users u ON u.id = p.user_id WHERE p.id = ?",
            (post_id,),
        ).fetchone()

    def can_manage_post(user, post) -> bool:
        return bool(post) and (post["user_id"] == user["id"] or "admin" in user["roles"])

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.errorhandler(413)
    def too_large(_exception):
        return error("Yêu cầu quá lớn.", 413)

    @app.get("/api/csrf")
    def get_csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify({"csrf_token": session["csrf_token"]})

    @app.get("/api/me")
    def get_me():
        return jsonify({"user": current_user()})

    @app.post("/api/register")
    @csrf_required
    def register():
        try:
            data = body()
            display_name = str(data.get("display_name", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            password = validate_password(data.get("password"))
            phone = validate_phone(data.get("phone", ""))
            if not display_name or len(display_name) > 80:
                raise ValueError("Vui lòng nhập tên hiển thị (tối đa 80 ký tự).")
            if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
                raise ValueError("Địa chỉ email không hợp lệ.")

            connection = get_db()
            cursor = connection.execute(
                "INSERT INTO users(email, password_hash, display_name, phone) VALUES (?, ?, ?, ?)",
                (email, hash_password(password), display_name, phone),
            )
            user_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO user_roles(user_id, role_id) SELECT ?, id FROM roles "
                "WHERE name IN ('finder', 'owner')",
                (user_id,),
            )
            connection.commit()
            session.clear()
            session["user_id"] = user_id
            session["csrf_token"] = secrets.token_urlsafe(32)
            session.permanent = True
            return jsonify({"user": public_user(user_id), "csrf_token": session["csrf_token"]}), 201
        except ValueError as exc:
            return error(str(exc))
        except sqlite3.IntegrityError:
            get_db().rollback()
            return error("Email này đã được đăng ký.", 409)

    @app.post("/api/login")
    @csrf_required
    def login():
        try:
            data = body()
        except ValueError as exc:
            return error(str(exc))
        email = str(data.get("email", "")).strip().lower()
        password = data.get("password")
        if not isinstance(password, str) or not email:
            return error("Vui lòng nhập email và mật khẩu.")
        row = get_db().execute(
            "SELECT id, password_hash, is_active FROM users WHERE email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()
        if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
            return error("Email hoặc mật khẩu không chính xác.", 401)
        session.clear()
        session["user_id"] = row["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True
        return jsonify({"user": public_user(row["id"]), "csrf_token": session["csrf_token"]})

    @app.post("/api/logout")
    @csrf_required
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/posts")
    def list_posts():
        filters = ["p.status = 'open'"]
        values = []
        post_type = request.args.get("type")
        category = request.args.get("category")
        district = request.args.get("district")
        search = request.args.get("q", "").strip()
        if post_type in {"lost", "found"}:
            filters.append("p.type = ?")
            values.append(post_type)
        if category and category in CATEGORIES:
            filters.append("p.category = ?")
            values.append(category)
        if district and (district in DISTRICTS or district == UNKNOWN_DISTRICT):
            filters.append("p.district = ?")
            values.append(district)
        if search:
            filters.append(
                "(p.title LIKE ? OR p.description LIKE ? OR p.location LIKE ? OR p.district LIKE ?)"
            )
            values.extend([f"%{search[:100]}%"] * 4)
        rows = get_db().execute(
            "SELECT p.id, p.user_id, p.type, p.category, p.title, p.description, p.district, "
            "p.location, p.incident_date AS date, p.status, "
            "p.created_at, u.display_name AS poster_name, "
            "(SELECT count(*) FROM verification_requests v WHERE v.post_id = p.id AND v.status = 'pending') "
            "AS pending_verifications FROM posts p JOIN users u ON u.id = p.user_id WHERE "
            + " AND ".join(filters)
            + " ORDER BY p.created_at DESC LIMIT 200",
            values,
        ).fetchall()
        user = current_user()
        results = []
        for row in rows:
            item = dict(row)
            item["is_mine"] = bool(user and item["user_id"] == user["id"])
            if not item["is_mine"]:
                item.pop("user_id")
            results.append(item)
        return jsonify({"posts": results})

    @app.get("/api/my/posts")
    @user_required
    def list_my_posts():
        rows = get_db().execute(
            "SELECT p.*, (SELECT count(*) FROM verification_requests v WHERE v.post_id = p.id) "
            "AS verification_count FROM posts p WHERE p.user_id = ? ORDER BY p.created_at DESC",
            (g.current_user["id"],),
        ).fetchall()
        return jsonify({"posts": [dict(row) for row in rows]})

    @app.get("/api/my/verifications")
    @user_required
    def list_my_verifications():
        rows = get_db().execute(
            "SELECT v.id, v.post_id, v.status, v.created_at, p.title AS post_title, "
            "p.type AS post_type, p.district, p.location, "
            "v.meeting_location, v.meeting_at, v.meeting_is_public, v.meeting_safety_warning, "
            "CASE WHEN v.status = 'accepted' THEN p.contact_phone ELSE NULL END AS contact_phone "
            "FROM verification_requests v JOIN posts p ON p.id = v.post_id "
            "WHERE v.claimant_user_id = ? ORDER BY v.created_at DESC LIMIT 200",
            (g.current_user["id"],),
        ).fetchall()
        return jsonify({"requests": [dict(row) for row in rows]})

    @app.post("/api/posts")
    @user_required
    @csrf_required
    def create_post():
        try:
            data = body()
            post_type = data.get("type")
            if not isinstance(post_type, str) or post_type not in {"lost", "found"}:
                raise ValueError("Loại tin đăng không hợp lệ.")
            category = data.get("category")
            district = data.get("district")
            title = str(data.get("title", "")).strip()
            description = str(data.get("description", "")).strip()
            location = data.get("location", "")
            if location is None and post_type == "lost":
                location = ""
            if not isinstance(location, str):
                raise ValueError("Địa điểm không hợp lệ.")
            location = location.strip()
            incident_date = data.get("date")
            phone = validate_phone(data.get("phone", ""))
            private_clue = str(data.get("private_clue", "")).strip()
            if not isinstance(category, str) or category not in CATEGORIES:
                raise ValueError("Vui lòng chọn danh mục hợp lệ.")
            if post_type == "lost":
                if district is None:
                    district = ""
                if not isinstance(district, str):
                    raise ValueError("Quận/khu vực không hợp lệ.")
                district = district.strip()
                if district and district not in DISTRICTS:
                    raise ValueError("Vui lòng chọn quận/khu vực hợp lệ.")
                if not district and location in DISTRICTS:
                    district = location
                    location = ""
                if not district and not location:
                    raise ValueError("Hãy nhập đường/khu vực mất đồ hoặc chọn quận.")
                if not district:
                    district = UNKNOWN_DISTRICT
            elif not isinstance(district, str) or district not in DISTRICTS:
                raise ValueError("Vui lòng chọn quận/khu vực hợp lệ.")
            if not title or len(title) > 70 or not description or len(description) > 1000:
                raise ValueError("Tên món đồ hoặc mô tả không hợp lệ.")
            if (post_type == "found" and not location) or len(location) > 120:
                raise ValueError("Vui lòng nhập địa điểm hợp lệ.")
            if not 15 <= len(private_clue) <= 300:
                raise ValueError("Tin đăng cần có đặc điểm bí mật từ 15 đến 300 ký tự để AI đối chiếu.")
            if not is_useful_clue(private_clue):
                raise ValueError("Đặc điểm bí mật cần có ít nhất 3 từ khóa nhận dạng cụ thể.")
            try:
                parsed_date = date.fromisoformat(incident_date)
                if parsed_date.isoformat() != incident_date:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError("Ngày xảy ra không hợp lệ.") from None
            post_id = str(uuid.uuid4())
            connection = get_db()
            connection.execute(
                "INSERT INTO posts(id, user_id, type, category, title, description, district, "
                "location, incident_date, contact_phone) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (post_id, g.current_user["id"], post_type, category, title, description,
                 district, location, incident_date, phone),
            )
            connection.execute(
                "INSERT INTO post_private_clues(post_id, clue_text) VALUES (?, ?)",
                (post_id, private_clue),
            )
            connection.commit()
            return jsonify({"post": dict(get_post(post_id))}), 201
        except ValueError as exc:
            return error(str(exc))

    @app.patch("/api/posts/<post_id>")
    @user_required
    @csrf_required
    def update_post(post_id):
        try:
            data = body()
        except ValueError as exc:
            return error(str(exc))
        post = get_post(post_id)
        if not can_manage_post(g.current_user, post):
            return error("Không tìm thấy tin hoặc bạn không có quyền sửa.", 404)
        status = data.get("status")
        allowed = {"open", "resolved"} if "admin" not in g.current_user["roles"] else {
            "open", "resolved", "hidden"
        }
        if not isinstance(status, str) or status not in allowed:
            return error("Trạng thái tin đăng không hợp lệ.")
        get_db().execute(
            "UPDATE posts SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, post_id),
        )
        if "admin" in g.current_user["roles"]:
            audit("update_status", "post", post_id, status)
        get_db().commit()
        return jsonify({"post": dict(get_post(post_id))})

    @app.post("/api/posts/<post_id>/verifications")
    @user_required
    @csrf_required
    def create_verification(post_id):
        post = get_post(post_id)
        if not post or post["status"] != "open":
            return error("Tin đăng không còn nhận yêu cầu xác minh.", 404)
        if post["user_id"] == g.current_user["id"]:
            return error("Bạn không thể tự xác minh tin của mình.", 403)
        try:
            data = body()
            details = str(data.get("details", "")).strip()
            phone = validate_phone(data.get("phone", ""))
            if not 10 <= len(details) <= 500:
                raise ValueError("Thông tin xác minh cần từ 10 đến 500 ký tự.")
            meeting_location = None
            meeting_at = None
            meeting_is_public = False
            meeting_safety_warning = False
            meeting_fields = ("meeting_location", "meeting_at", "meeting_is_public")
            has_meeting_fields = any(field in data for field in meeting_fields)
            if post["type"] == "lost" and has_meeting_fields:
                meeting_location = data.get("meeting_location")
                meeting_at = data.get("meeting_at")
                meeting_is_public = data.get("meeting_is_public")
                if not isinstance(meeting_location, str):
                    raise ValueError("Vui lòng nhập địa điểm hẹn.")
                meeting_location = meeting_location.strip()
                if not 3 <= len(meeting_location) <= 200:
                    raise ValueError("Địa điểm hẹn cần từ 3 đến 200 ký tự.")
                if not isinstance(meeting_at, str):
                    raise ValueError("Vui lòng chọn ngày và giờ hẹn.")
                try:
                    parsed_meeting_at = datetime.strptime(meeting_at, "%Y-%m-%dT%H:%M")
                except ValueError as exc:
                    raise ValueError("Ngày giờ hẹn không hợp lệ.") from exc
                if parsed_meeting_at.strftime("%Y-%m-%dT%H:%M") != meeting_at:
                    raise ValueError("Ngày giờ hẹn không hợp lệ.")
                if not isinstance(meeting_is_public, bool):
                    raise ValueError("Thông tin xác nhận địa điểm không hợp lệ.")
                outside_recommended_hours = (
                    parsed_meeting_at.time() < time(6) or parsed_meeting_at.time() > time(22)
                )
                meeting_safety_warning = outside_recommended_hours and not meeting_is_public
            elif has_meeting_fields:
                raise ValueError("Chỉ có thể đề xuất cuộc hẹn cho tin đang tìm mất đồ.")
            private_clue_row = get_db().execute(
                "SELECT clue_text FROM post_private_clues WHERE post_id = ?", (post_id,)
            ).fetchone()
            previous_rejections = get_db().execute(
                "SELECT count(*) FROM verification_requests WHERE claimant_user_id = ? AND status = 'rejected'",
                (g.current_user["id"],),
            ).fetchone()[0]
            recent_claims = get_db().execute(
                "SELECT count(*) FROM verification_requests WHERE claimant_user_id = ? "
                "AND created_at >= datetime('now', '-1 hour')",
                (g.current_user["id"],),
            ).fetchone()[0]
            analysis = analyze_claim(
                private_clue_row["clue_text"] if private_clue_row else "",
                details,
                previous_rejections=previous_rejections,
                recent_claims=recent_claims,
            )
            request_id = str(uuid.uuid4())
            get_db().execute(
                "INSERT INTO verification_requests(id, post_id, claimant_user_id, details, contact_phone, "
                "risk_score, risk_level, risk_reasons, meeting_location, meeting_at, meeting_is_public, "
                "meeting_safety_warning) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request_id, post_id, g.current_user["id"], details, phone,
                 analysis["risk_score"], analysis["risk_level"],
                 json.dumps(analysis["risk_reasons"], ensure_ascii=False),
                 meeting_location, meeting_at, meeting_is_public, meeting_safety_warning),
            )
            get_db().commit()
            return jsonify({"request": {"id": request_id, "status": "pending"}}), 201
        except ValueError as exc:
            return error(str(exc))
        except sqlite3.IntegrityError:
            get_db().rollback()
            return error("Bạn đã gửi yêu cầu đang chờ cho tin này.", 409)

    @app.get("/api/posts/<post_id>/verifications")
    @user_required
    def list_verifications(post_id):
        post = get_post(post_id)
        if not post or not can_manage_post(g.current_user, post):
            return error("Không tìm thấy tin hoặc bạn không có quyền xem yêu cầu.", 404)
        rows = get_db().execute(
            "SELECT v.id, v.post_id, v.claimant_user_id, v.details, "
            "CASE WHEN v.status = 'accepted' THEN v.contact_phone ELSE NULL END AS contact_phone, v.status, "
            "v.risk_score, v.risk_level, v.risk_reasons, v.meeting_location, v.meeting_at, "
            "v.meeting_is_public, v.meeting_safety_warning, v.created_at, "
            "u.display_name AS claimant_name FROM verification_requests v "
            "JOIN users u ON u.id = v.claimant_user_id WHERE v.post_id = ? "
            "ORDER BY v.created_at DESC",
            (post_id,),
        ).fetchall()
        requests = [dict(row) for row in rows]
        for item in requests:
            item["risk_reasons"] = json.loads(item["risk_reasons"])
        return jsonify({"requests": requests})

    def review_verification(request_id, status, admin=False):
        verification = get_db().execute(
            "SELECT v.*, p.user_id AS poster_id, p.status AS post_status FROM verification_requests v "
            "JOIN posts p ON p.id = v.post_id WHERE v.id = ?",
            (request_id,),
        ).fetchone()
        if not verification:
            return error("Không tìm thấy yêu cầu xác minh.", 404)
        if not admin and verification["poster_id"] != g.current_user["id"]:
            return error("Bạn không có quyền duyệt yêu cầu này.", 403)
        if verification["status"] != "pending":
            return error("Yêu cầu này đã được xử lý.", 409)
        connection = get_db()
        connection.execute(
            "UPDATE verification_requests SET status = ?, reviewed_at = datetime('now'), "
            "reviewed_by_user_id = ? WHERE id = ?",
            (status, g.current_user["id"], request_id),
        )
        if status == "accepted":
            connection.execute(
                "UPDATE posts SET status = 'resolved', updated_at = datetime('now') WHERE id = ?",
                (verification["post_id"],),
            )
            connection.execute(
                "UPDATE verification_requests SET status = 'rejected', reviewed_at = datetime('now'), "
                "reviewed_by_user_id = ? WHERE post_id = ? AND id != ? AND status = 'pending'",
                (g.current_user["id"], verification["post_id"], request_id),
            )
        if admin:
            audit("review_verification", "verification", request_id, status)
        connection.commit()
        return jsonify({"ok": True, "status": status})

    @app.patch("/api/verifications/<request_id>")
    @user_required
    @csrf_required
    def update_verification(request_id):
        try:
            status = body().get("status")
        except ValueError as exc:
            return error(str(exc))
        if not isinstance(status, str) or status not in {"accepted", "rejected"}:
            return error("Trạng thái duyệt không hợp lệ.")
        return review_verification(request_id, status)

    @app.get("/api/admin/overview")
    @admin_required
    def admin_overview():
        connection = get_db()
        overview = {
            "users": connection.execute("SELECT count(*) FROM users").fetchone()[0],
            "posts": connection.execute("SELECT count(*) FROM posts").fetchone()[0],
            "open_posts": connection.execute("SELECT count(*) FROM posts WHERE status = 'open'").fetchone()[0],
            "pending_verifications": connection.execute(
                "SELECT count(*) FROM verification_requests WHERE status = 'pending'"
            ).fetchone()[0],
        }
        return jsonify({"overview": overview})

    @app.get("/api/admin/users")
    @admin_required
    def admin_users():
        rows = get_db().execute(
            "SELECT u.id, u.email, u.display_name, u.phone, u.is_active, u.created_at, "
            "group_concat(r.name, ',') AS roles FROM users u "
            "LEFT JOIN user_roles ur ON ur.user_id = u.id LEFT JOIN roles r ON r.id = ur.role_id "
            "GROUP BY u.id ORDER BY u.created_at DESC LIMIT 500"
        ).fetchall()
        users = []
        for row in rows:
            item = dict(row)
            role_names = (item["roles"] or "").split(",") if item["roles"] else []
            item["roles"] = account_roles(role_names)
            users.append(item)
        return jsonify({"users": users})

    @app.patch("/api/admin/users/<int:user_id>")
    @admin_required
    @csrf_required
    def admin_update_user(user_id):
        try:
            data = body()
        except ValueError as exc:
            return error(str(exc))
        active = data.get("is_active")
        if not isinstance(active, bool):
            return error("Trạng thái tài khoản không hợp lệ.")
        target = get_db().execute(
            "SELECT id, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not target:
            return error("Không tìm thấy tài khoản.", 404)
        if user_id == g.current_user["id"] and not active:
            return error("Không thể khóa tài khoản admin đang sử dụng.", 409)
        if not active:
            active_admins = get_db().execute(
                "SELECT count(*) FROM users u JOIN user_roles ur ON ur.user_id = u.id "
                "JOIN roles r ON r.id = ur.role_id WHERE r.name = 'admin' AND u.is_active = 1"
            ).fetchone()[0]
            is_admin = get_db().execute(
                "SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                "WHERE ur.user_id = ? AND r.name = 'admin'",
                (user_id,),
            ).fetchone()
            if is_admin and active_admins <= 1:
                return error("Không thể khóa admin cuối cùng.", 409)
        get_db().execute("UPDATE users SET is_active = ? WHERE id = ?", (int(active), user_id))
        audit("set_user_active", "user", user_id, str(active).lower())
        get_db().commit()
        return jsonify({"ok": True})

    @app.get("/api/admin/posts")
    @admin_required
    def admin_posts():
        rows = get_db().execute(
            "SELECT p.*, u.email AS poster_email, u.display_name AS poster_name "
            "FROM posts p JOIN users u ON u.id = p.user_id ORDER BY p.created_at DESC LIMIT 500"
        ).fetchall()
        return jsonify({"posts": [dict(row) for row in rows]})

    @app.get("/api/admin/verifications")
    @admin_required
    def admin_verifications():
        rows = get_db().execute(
            "SELECT v.id, v.post_id, v.claimant_user_id, v.details, v.contact_phone, v.status, "
            "v.risk_score, v.risk_level, v.risk_reasons, v.created_at, v.reviewed_at, "
            "p.title AS post_title, poster.email AS poster_email, "
            "claimant.email AS claimant_email FROM verification_requests v "
            "JOIN posts p ON p.id = v.post_id JOIN users poster ON poster.id = p.user_id "
            "JOIN users claimant ON claimant.id = v.claimant_user_id "
            "ORDER BY v.created_at DESC LIMIT 500"
        ).fetchall()
        requests = [dict(row) for row in rows]
        for item in requests:
            item["risk_reasons"] = json.loads(item["risk_reasons"])
        return jsonify({"requests": requests})

    @app.patch("/api/admin/verifications/<request_id>")
    @admin_required
    @csrf_required
    def admin_review_verification(request_id):
        try:
            status = body().get("status")
        except ValueError as exc:
            return error(str(exc))
        if not isinstance(status, str) or status not in {"accepted", "rejected"}:
            return error("Trạng thái duyệt không hợp lệ.")
        return review_verification(request_id, status, admin=True)

    @app.patch("/api/admin/posts/<post_id>")
    @admin_required
    @csrf_required
    def admin_update_post(post_id):
        try:
            status = body().get("status")
        except ValueError as exc:
            return error(str(exc))
        if not isinstance(status, str) or status not in {"open", "resolved", "hidden"}:
            return error("Trạng thái tin đăng không hợp lệ.")
        if not get_post(post_id):
            return error("Không tìm thấy tin đăng.", 404)
        get_db().execute(
            "UPDATE posts SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, post_id),
        )
        audit("set_post_status", "post", post_id, status)
        get_db().commit()
        return jsonify({"ok": True})

    @app.get("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
