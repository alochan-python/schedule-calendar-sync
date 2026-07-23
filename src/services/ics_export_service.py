"""ScheduleEventのリストをICSファイルへ出力するサービス。

Google Calendar APIを設定していなくても利用できる機能。
UIDはsource_keyから生成した安定した値を使用する(再出力しても同じUIDになる)。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from src.models import ScheduleEvent


def _uid_from_source_key(source_key: str) -> str:
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:32]
    return f"{digest}@schedule-calendar-sync"


def build_ics(events: list[ScheduleEvent]) -> bytes:
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
        cal.add_component(ical_event)

    return cal.to_ical()
