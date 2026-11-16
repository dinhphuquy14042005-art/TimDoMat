import sqlite3
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_DIR = BACKEND_ROOT / "data"
SCHEMA_PATH = DATA_DIR / "schema.sql"
DEFAULT_DATABASE = DATA_DIR / "danang_lost_found.db"
WEB_DIR = PROJECT_ROOT / "web"


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    verification_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(verification_requests)")
    }
    for name, declaration in (
        ("risk_score", "INTEGER NOT NULL DEFAULT 50"),
        ("risk_level", "TEXT NOT NULL DEFAULT 'medium'"),
        ("risk_reasons", "TEXT NOT NULL DEFAULT '[]'"),
        ("meeting_location", "TEXT"),
        ("meeting_at", "TEXT"),
        ("meeting_is_public", "INTEGER NOT NULL DEFAULT 0 CHECK (meeting_is_public IN (0, 1))"),
        ("meeting_safety_warning", "INTEGER NOT NULL DEFAULT 0 CHECK (meeting_safety_warning IN (0, 1))"),
    ):
        if name not in verification_columns:
            connection.execute(f"ALTER TABLE verification_requests ADD COLUMN {name} {declaration}")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_verification_claimant "
        "ON verification_requests(post_id, claimant_user_id) WHERE status = 'pending'"
    )
    connection.commit()
