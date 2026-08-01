"""Google Calendar API連携サービス。

credentials.json が無い場合でもアプリ自体はエラー終了せず、
呼び出し側(Streamlit画面)が google_credentials_available() を見て
設定手順を案内できるようにする。

OAuthは「デスクトップアプリ」方式を使用し、初回のみブラウザでログイン・
権限許可を行う。token.json にトークンが保存され、以後はそれを再利用する。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config import (
    DEFAULT_REMINDER_MINUTES,
    GOOGLE_CALENDAR_SCOPES,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
    google_credentials_available,
)
from src.models import ScheduleEvent

PRIVATE_KEY_SCHEDULE_SYNC = "schedule_sync_key"
PRIVATE_KEY_SOURCE_TYPE = "source_type"
PRIVATE_KEY_RESERVATION_CODE = "reservation_code"


class GoogleCalendarNotConfiguredError(Exception):
    """credentials.json が存在しない場合に送出する。"""


@dataclass
class CalendarInfo:
    id: str
    summary: str


def build_event_body(event: ScheduleEvent, reminder_minutes: Optional[list[int]] = None) -> dict:
    """ScheduleEventからGoogle Calendar APIのevents().insert用bodyを構築する。

    reminder_minutes: 通知タイミング(分前)のリスト。複数指定可(例: [120, 1440] で
    2時間前・1日前の2つの通知)。空リストを渡すと通知なしになる。Noneの場合は既定値を使う。
    """
    tz = event.timezone or "Asia/Tokyo"
    if reminder_minutes is None:
        reminder_minutes = DEFAULT_REMINDER_MINUTES
    return {
        "summary": event.title,
        "location": event.location,
        "description": event.description,
        "start": {"dateTime": event.start_datetime.isoformat(), "timeZone": tz},
        "end": {"dateTime": event.end_datetime.isoformat(), "timeZone": tz},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": m} for m in reminder_minutes],
        },
        "extendedProperties": {
            "private": {
                PRIVATE_KEY_SCHEDULE_SYNC: event.source_key,
                PRIVATE_KEY_SOURCE_TYPE: event.source_type,
                PRIVATE_KEY_RESERVATION_CODE: event.reservation_code or "",
            }
        },
    }


class GoogleCalendarService:
    """Google Calendar APIへのアクセスをラップするサービス。

    credentials.json が無い環境でもインポート・インスタンス化自体は可能。
    実際にAPIへアクセスするメソッド呼び出し時にのみ例外を送出する。
    """

    def __init__(self) -> None:
        self._service = None

    @staticmethod
    def is_configured() -> bool:
        return google_credentials_available()

    def _get_service(self):
        if self._service is not None:
            return self._service
        if not google_credentials_available():
            raise GoogleCalendarNotConfiguredError(
                f"{GOOGLE_CREDENTIALS_PATH} が見つかりません。"
                "READMEの『Google Calendar API設定手順』を参照してください。"
            )
        # 遅延importにして、未設定環境でも本モジュール自体はimportできるようにする
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if GOOGLE_TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), GOOGLE_CALENDAR_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(GOOGLE_CREDENTIALS_PATH), GOOGLE_CALENDAR_SCOPES
                )
                creds = flow.run_local_server(port=0)
            GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def connect(self) -> None:
        """OAuth認証を実行する(初回はブラウザが開く)。"""
        self._get_service()

    def is_connected(self) -> bool:
        return GOOGLE_TOKEN_PATH.exists()

    def list_calendars(self) -> list[CalendarInfo]:
        service = self._get_service()
        result = service.calendarList().list().execute()
        return [CalendarInfo(id=item["id"], summary=item.get("summary", item["id"]))
                for item in result.get("items", [])]

    def ensure_calendar(self, name: str) -> str:
        """名前でカレンダーを探し、無ければ作成してcalendar_idを返す。"""
        if name == "primary":
            return "primary"
        service = self._get_service()
        for cal in self.list_calendars():
            if cal.summary == name:
                return cal.id
        created = service.calendars().insert(body={"summary": name, "timeZone": "Asia/Tokyo"}).execute()
        return created["id"]

    def insert_event(self, calendar_id: str, event: ScheduleEvent,
                      reminder_minutes: Optional[list[int]] = None) -> str:
        service = self._get_service()
        body = build_event_body(event, reminder_minutes)
        created = service.events().insert(calendarId=calendar_id, body=body).execute()
        return created["id"]

    def update_event(self, calendar_id: str, google_event_id: str, event: ScheduleEvent,
                      reminder_minutes: Optional[list[int]] = None) -> str:
        service = self._get_service()
        body = build_event_body(event, reminder_minutes)
        updated = service.events().update(
            calendarId=calendar_id, eventId=google_event_id, body=body
        ).execute()
        return updated["id"]

    def delete_event(self, calendar_id: str, google_event_id: str) -> None:
        service = self._get_service()
        from googleapiclient.errors import HttpError
        try:
            service.events().delete(calendarId=calendar_id, eventId=google_event_id).execute()
        except HttpError as exc:
            if exc.resp.status != 404:
                raise
