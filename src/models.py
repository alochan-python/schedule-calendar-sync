"""共通データモデル定義。

Excel取込・Web取込のどちらから来た予定も、最終的にこの ScheduleEvent 形式へ
変換してから確認画面・Googleカレンダー登録・CSV/ICS出力を行う。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

DEFAULT_TIMEZONE = "Asia/Tokyo"

SOURCE_TYPE_EXCEL = "excel"
SOURCE_TYPE_WEB = "web"

COURSE_AI_IMPLEMENTATION = "AI実装コース"
COURSE_AI_ANALYSIS = "AI分析コース"

STATUS_CANDIDATE = "候補"
STATUS_CONFIRMED = "確定"
STATUS_TENTATIVE = "仮予定"
STATUS_CANCELLED = "キャンセル"

SYNC_STATUS_NOT_SYNCED = "未登録"
SYNC_STATUS_SYNCED = "登録済み"
SYNC_STATUS_UPDATED = "更新済み"
SYNC_STATUS_ERROR = "エラー"
SYNC_STATUS_DELETE_CANDIDATE = "削除候補"


@dataclass
class ScheduleEvent:
    """予定1件を表す共通データモデル。"""

    # --- 由来情報 ---
    source_type: str  # "excel" または "web"
    source_file: str  # 取込元のファイル名・入力名
    source_key: str  # 重複防止のための一意キー

    # --- 分類 ---
    course: str = ""  # 例: "AI実装コース" / "AI分析コース" / ""
    session_name: str = ""  # 例: "第2回" / レッスン名など

    # --- 予定本体 ---
    title: str = ""
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    timezone: str = DEFAULT_TIMEZONE
    location: str = ""
    instructor: str = ""
    reservation_code: str = ""
    description: str = ""
    status: str = STATUS_CANDIDATE

    # --- UI・同期用の状態 ---
    selected: bool = False
    google_event_id: Optional[str] = None
    sync_status: str = SYNC_STATUS_NOT_SYNCED

    # --- 追加のWeb項目(表示・説明文生成用に保持) ---
    weekday: str = ""
    reservation_type: str = ""
    raw_text: str = ""
    original_location: str = ""

    # --- 管理用 ---
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def is_valid_time_range(self) -> bool:
        if self.start_datetime is None or self.end_datetime is None:
            return False
        return self.start_datetime < self.end_datetime

    def is_past(self, now: Optional[datetime] = None) -> bool:
        if self.end_datetime is None:
            return False
        now = now or datetime.now(self.end_datetime.tzinfo)
        return self.end_datetime < now

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "source_key": self.source_key,
            "course": self.course,
            "session_name": self.session_name,
            "title": self.title,
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
            "timezone": self.timezone,
            "location": self.location,
            "instructor": self.instructor,
            "reservation_code": self.reservation_code,
            "description": self.description,
            "status": self.status,
            "selected": self.selected,
            "google_event_id": self.google_event_id,
            "sync_status": self.sync_status,
            "weekday": self.weekday,
            "reservation_type": self.reservation_type,
            "raw_text": self.raw_text,
            "original_location": self.original_location,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def make_excel_source_key(course: str, session_name: str, start_datetime: datetime) -> str:
    """excel|コース名|第○回|開始日時 形式のキーを生成する。"""
    dt_str = start_datetime.strftime("%Y-%m-%dT%H:%M") if start_datetime else "unknown"
    return f"excel|{course}|{session_name}|{dt_str}"


def make_web_source_key(reservation_code: str) -> str:
    """web|予約番号 形式のキーを生成する。予約番号が無い場合はraw_textから代替キーを作る。"""
    if reservation_code:
        return f"web|{reservation_code}"
    return f"web|{uuid.uuid4()}"
