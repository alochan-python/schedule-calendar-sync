"""SQLiteによる同期履歴の管理。

data/schedule_sync.db に、source_key <-> google_event_id の対応を保存し、
再同期時の重複登録防止・内容変更検出(content_hash)に利用する。
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATABASE_PATH, ensure_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    google_event_id TEXT,
    calendar_id TEXT,
    last_synced_at TEXT,
    content_hash TEXT,
    sync_status TEXT,
    title TEXT,
    start_datetime TEXT,
    end_datetime TEXT
);
"""


@dataclass
class SyncRecord:
    source_key: str
    google_event_id: Optional[str]
    calendar_id: Optional[str]
    last_synced_at: Optional[str]
    content_hash: Optional[str]
    sync_status: Optional[str]
    title: Optional[str] = None
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DATABASE_PATH
    ensure_data_dir()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def compute_content_hash(title: str, start_datetime: str, end_datetime: str, location: str, description: str) -> str:
    raw = "|".join([title or "", start_datetime or "", end_datetime or "", location or "", description or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_record(conn: sqlite3.Connection, source_key: str) -> Optional[SyncRecord]:
    row = conn.execute(
        "SELECT * FROM sync_history WHERE source_key = ?", (source_key,)
    ).fetchone()
    if row is None:
        return None
    return SyncRecord(
        source_key=row["source_key"],
        google_event_id=row["google_event_id"],
        calendar_id=row["calendar_id"],
        last_synced_at=row["last_synced_at"],
        content_hash=row["content_hash"],
        sync_status=row["sync_status"],
        title=row["title"],
        start_datetime=row["start_datetime"],
        end_datetime=row["end_datetime"],
    )


def get_all_records(conn: sqlite3.Connection) -> list[SyncRecord]:
    rows = conn.execute("SELECT * FROM sync_history").fetchall()
    return [
        SyncRecord(
            source_key=r["source_key"],
            google_event_id=r["google_event_id"],
            calendar_id=r["calendar_id"],
            last_synced_at=r["last_synced_at"],
            content_hash=r["content_hash"],
            sync_status=r["sync_status"],
            title=r["title"],
            start_datetime=r["start_datetime"],
            end_datetime=r["end_datetime"],
        )
        for r in rows
    ]


def upsert_record(conn: sqlite3.Connection, record: SyncRecord) -> None:
    conn.execute(
        """
        INSERT INTO sync_history
            (source_key, google_event_id, calendar_id, last_synced_at, content_hash, sync_status,
             title, start_datetime, end_datetime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
            google_event_id=excluded.google_event_id,
            calendar_id=excluded.calendar_id,
            last_synced_at=excluded.last_synced_at,
            content_hash=excluded.content_hash,
            sync_status=excluded.sync_status,
            title=excluded.title,
            start_datetime=excluded.start_datetime,
            end_datetime=excluded.end_datetime
        """,
        (
            record.source_key,
            record.google_event_id,
            record.calendar_id,
            record.last_synced_at or datetime.now().isoformat(),
            record.content_hash,
            record.sync_status,
            record.title,
            record.start_datetime,
            record.end_datetime,
        ),
    )
    conn.commit()


def delete_record(conn: sqlite3.Connection, source_key: str) -> None:
    conn.execute("DELETE FROM sync_history WHERE source_key = ?", (source_key,))
    conn.commit()
