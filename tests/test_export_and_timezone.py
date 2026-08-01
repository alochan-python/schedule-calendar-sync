from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar

from src.models import ScheduleEvent
from src.services.csv_export_service import to_google_calendar_csv, to_normalized_csv
from src.services.google_calendar_service import build_event_body
from src.services.ics_export_service import build_ics


def make_event():
    return ScheduleEvent(
        source_type="web",
        source_file="test",
        source_key="web|G00001",
        title="英会話｜テストレッスン",
        start_datetime=datetime(2026, 8, 1, 10, 0),
        end_datetime=datetime(2026, 8, 1, 10, 30),
        location="オンライン",
        instructor="田中",
        description="講師: 田中",
        selected=True,
    )


def test_ics_contains_required_fields():
    ics_bytes = build_ics([make_event()])
    cal = Calendar.from_ical(ics_bytes)
    events = list(cal.walk("VEVENT"))
    assert len(events) == 1
    ev = events[0]
    assert ev["SUMMARY"] == "英会話｜テストレッスン"
    assert ev["UID"]
    assert ev["DTSTART"] is not None
    assert ev["DTEND"] is not None
    assert ev["DTSTAMP"] is not None
    assert str(ev["LOCATION"]) == "オンライン"


def test_ics_uses_asia_tokyo_timezone():
    ics_bytes = build_ics([make_event()])
    cal = Calendar.from_ical(ics_bytes)
    ev = list(cal.walk("VEVENT"))[0]
    dtstart = ev["DTSTART"].dt
    assert dtstart.tzinfo is not None
    assert dtstart.utcoffset() == ZoneInfo("Asia/Tokyo").utcoffset(datetime(2026, 8, 1))


def test_ics_uid_is_stable_across_calls():
    event = make_event()
    uid1 = list(Calendar.from_ical(build_ics([event])).walk("VEVENT"))[0]["UID"]
    uid2 = list(Calendar.from_ical(build_ics([event])).walk("VEVENT"))[0]["UID"]
    assert str(uid1) == str(uid2)


def test_normalized_csv_contains_event():
    csv_text = to_normalized_csv([make_event()])
    assert "英会話｜テストレッスン" in csv_text
    assert "web|G00001" in csv_text


def test_google_calendar_csv_format():
    csv_text = to_google_calendar_csv([make_event()])
    assert "Subject" in csv_text.splitlines()[0]
    assert "英会話｜テストレッスン" in csv_text


def test_build_event_body_uses_asia_tokyo():
    body = build_event_body(make_event())
    assert body["start"]["timeZone"] == "Asia/Tokyo"
    assert body["end"]["timeZone"] == "Asia/Tokyo"
    assert body["extendedProperties"]["private"]["schedule_sync_key"] == "web|G00001"


def test_build_event_body_default_reminders_are_2h_and_1day():
    body = build_event_body(make_event())
    minutes = sorted(o["minutes"] for o in body["reminders"]["overrides"])
    assert minutes == [120, 1440]
    assert body["reminders"]["useDefault"] is False


def test_build_event_body_custom_reminder_list():
    body = build_event_body(make_event(), reminder_minutes=[10, 60, 10080])
    minutes = sorted(o["minutes"] for o in body["reminders"]["overrides"])
    assert minutes == [10, 60, 10080]


def test_build_event_body_empty_list_means_no_notification():
    body = build_event_body(make_event(), reminder_minutes=[])
    assert body["reminders"]["overrides"] == []
    assert body["reminders"]["useDefault"] is False


def test_ics_default_reminders_add_two_valarms():
    ics_bytes = build_ics([make_event()])
    ev = list(Calendar.from_ical(ics_bytes).walk("VEVENT"))[0]
    alarms = list(ev.walk("VALARM"))
    assert len(alarms) == 2
    triggers = sorted(a["TRIGGER"].dt for a in alarms)
    from datetime import timedelta
    assert triggers == sorted([timedelta(minutes=-120), timedelta(minutes=-1440)])


def test_ics_empty_reminder_list_has_no_valarm():
    ics_bytes = build_ics([make_event()], reminder_minutes=[])
    ev = list(Calendar.from_ical(ics_bytes).walk("VEVENT"))[0]
    assert list(ev.walk("VALARM")) == []


def test_ics_custom_reminder_list():
    ics_bytes = build_ics([make_event()], reminder_minutes=[30])
    ev = list(Calendar.from_ical(ics_bytes).walk("VEVENT"))[0]
    alarms = list(ev.walk("VALARM"))
    assert len(alarms) == 1
