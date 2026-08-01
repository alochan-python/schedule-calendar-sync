"""ScheduleEventのリストをICSファイルへ出力するサービス。

Google Calendar APIを設定していなくても利用できる機能。
UIDはsource_keyから生成した安定した値を使用する(再出力しても同じUIDになる)。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar, Event

from src.config import DEFAULT_REMINDER_MINUTES
from src.models import ScheduleEvent


def _uid_from_source_key(source_key: str) -> str:
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:32]
    return f"{digest}@schedule-calendar-sync"


def build_ics(events: list[ScheduleEvent], reminder_minutes: Optional[list[int]] = None) -> bytes:
    """ScheduleEventのリストからICSファイルを生成する。

    reminder_minutes: 通知タイミング(分前)のリスト。Noneなら既定値、空リストなら通知なし。
    """
    if reminder_minutes is None:
        reminder_minutes = DEFAULT_REMINDER_MINUTES
    cal = Calendar()
    cal.add("prodid", "-//schedule-calendar-sync//JP")
    cal.add("version", "2.0")

    now_utc = datetime.now(ZoneInfo("UTC"))

    for e in events:
        if e.start_datetime is None or e.end_datetime is None:
            continue
        tzinfo = ZoneInfo(e.timezone or "Asia/Tokyo")
        start = e.start_datetime
        end = e.end_datetime
        if start.tzinfo is None:
            start = start.replace(tzinfo=tzinfo)
        if end.tzinfo is None:
            end = end.replace(tzinfo=tzinfo)

        ical_event = Event()
        ical_event.add("uid", _uid_from_source_key(e.source_key))
        ical_event.add("summary", e.title)
        ical_event.add("dtstart", start)
        ical_event.add("dtend", end)
        ical_event.add("dtstamp", now_utc)
        if e.location:
            ical_event.add("location", e.location)
        if e.description:
            ical_event.add("description", e.description)

        for minutes in reminder_minutes:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", e.title)
            alarm.add("trigger", timedelta(minutes=-minutes))
            ical_event.add_component(alarm)

        cal.add_component(ical_event)

    return cal.to_ical()
