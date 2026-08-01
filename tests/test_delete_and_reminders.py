from __future__ import annotations

from src.config import REMINDER_PRESETS
from src.models import ScheduleEvent


def _make_app_event(source_key: str) -> ScheduleEvent:
    return ScheduleEvent(
        source_type="web", source_file="t", source_key=source_key, title=f"予定:{source_key}"
    )


def test_add_and_remove_events_from_store():
    import app

    app.init_session_state()
    app.st.session_state.events = {}

    added = app.add_events([_make_app_event("web|DEL1"), _make_app_event("web|DEL2")])
    assert added == 2
    assert len(app.all_events()) == 2

    removed = app.remove_events(["web|DEL1"])
    assert removed == 1
    remaining = app.all_events()
    assert len(remaining) == 1
    assert remaining[0].source_key == "web|DEL2"


def test_remove_events_ignores_unknown_key():
    import app

    app.init_session_state()
    app.st.session_state.events = {}
    app.add_events([_make_app_event("web|DEL3")])

    removed = app.remove_events(["web|NOT_EXIST"])
    assert removed == 0
    assert len(app.all_events()) == 1


def test_reminder_minutes_from_labels_default():
    import app

    minutes = app.reminder_minutes_from_labels(["2時間前", "1日前"])
    assert minutes == [120, 1440]


def test_reminder_minutes_from_labels_empty_means_no_notification():
    import app

    assert app.reminder_minutes_from_labels([]) == []


def test_reminder_minutes_from_labels_dedup_and_sort():
    import app

    minutes = app.reminder_minutes_from_labels(["1日前", "5分前", "5分前"])
    assert minutes == [5, 1440]


def test_reminder_presets_contain_all_documented_options():
    for label in ["5分前", "10分前", "15分前", "30分前", "1時間前", "2時間前",
                  "3時間前", "6時間前", "12時間前", "1日前", "2日前", "3日前", "1週間前"]:
        assert label in REMINDER_PRESETS
