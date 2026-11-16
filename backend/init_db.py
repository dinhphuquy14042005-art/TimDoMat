import argparse
import base64
import getpass
import hashlib
import os
import secrets
import sqlite3
from pathlib import Path

from .database import DEFAULT_DATABASE, SCHEMA_PATH

PASSWORD_ITERATIONS = 600_000
DEFAULT_ADMIN_EMAIL = "admin@gmail.com"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt_text}${digest_text}"


def initialize_database(database_path: Path, admin_email: str, admin_password: str) -> bool:
    if not admin_email or "@" not in admin_email:
        raise ValueError("Admin email không hợp lệ.")
    if len(admin_password) < 8:
        raise ValueError("Mật khẩu admin phải có ít nhất 8 ký tự.")

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema)

        existing = connection.execute(
            "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
            (admin_email,),
        ).fetchone()
        admin_role_id = connection.execute(
            "SELECT id FROM roles WHERE name = 'admin'"
        ).fetchone()[0]

        if existing:
            has_admin_role = connection.execute(
                "SELECT 1 FROM user_roles WHERE user_id = ? AND role_id = ?",
                (existing[0], admin_role_id),
            ).fetchone()
            if not has_admin_role:
                raise ValueError(
                    "Email admin đã thuộc về tài khoản không phải admin; "
                    "không tự ý nâng quyền tài khoản hiện có."
                )
            return False

        cursor = connection.execute(
            "INSERT INTO users(email, password_hash, display_name) VALUES (?, ?, ?)",
            (admin_email, hash_password(admin_password), "Quản trị viên"),
        )
        connection.execute(
            "INSERT INTO user_roles(user_id, role_id) VALUES (?, ?)",
            (cursor.lastrowid, admin_role_id),
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Khởi tạo CSDL Nhặt Được Đà Nẵng.")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Đường dẫn tệp SQLite (mặc định: danang_lost_found.db)",
    )
    args = parser.parse_args()

    admin_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_password is None:
        admin_password = getpass.getpass("Nhập mật khẩu khởi tạo cho admin: ")
        confirmation = getpass.getpass("Nhập lại mật khẩu admin: ")
        if admin_password != confirmation:
            raise SystemExit("Hai mật khẩu không khớp; chưa tạo tài khoản admin.")

    created = initialize_database(args.db, admin_email, admin_password)
    if created:
        print(f"Database initialized at: {args.db.resolve()}")
        print(f"Admin account created: {admin_email}")
    else:
        print(f"Database already exists; admin account unchanged: {admin_email}")


if __name__ == "__main__":
    main()
