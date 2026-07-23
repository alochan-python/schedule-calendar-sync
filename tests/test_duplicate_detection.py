from __future__ import annotations

from datetime import datetime, timedelta

from src.database import get_connection
from src.models import ScheduleEvent
from src.services.sync_service import (
    ACTION_NEW,
    ACTION_UNCHANGED,
    ACTION_UPDATE,
    dry_run,
    find_delete_candidates,
    find_duplicate_source_keys,
    sync_events,
)


class FakeCalendarService:
    """Google Calendar APIの実通信を行わないモック。"""

    def __init__(self) -> None:
        self.inserted = []
        self.updated = []
        self.deleted = []
        self._counter = 0

    def insert_event(self, calendar_id, event, reminder_minutes=15):
        self._counter += 1
        event_id = f"fake-event-{self._counter}"
        self.inserted.append((calendar_id, event.source_key, event_id))
        return event_id

    def update_event(self, calendar_id, google_event_id, event, reminder_minutes=15):
        self.updated.append((calendar_id, event.source_key, google_event_id))
        return google_event_id

    def delete_event(self, calendar_id, google_event_id):
        self.deleted.append((calendar_id, google_event_id))


def make_event(source_key="web|G00001", title="英会話｜テスト", minutes_offset=0):
    start = datetime(2026, 8, 1, 10, 0) + timedelta(minutes=minutes_offset)
    end = start + timedelta(minutes=30)
    return ScheduleEvent(
        source_type="web",
        source_file="test",
        source_key=source_key,
        title=title,
        start_datetime=start,
        end_datetime=end,
        location="オンライン",
        selected=True,
    )


def test_same_source_key_synced_twice_does_not_duplicate(tmp_db_path):
    conn = get_connection(tmp_db_path)
    service = FakeCalendarService()
    event = make_event()

    sync_events(conn, service, "primary", [event])
    sync_events(conn, service, "primary", [event])

    assert len(service.inserted) == 1  # 2回目は新規登録されない
    row_count = conn.execute("SELECT COUNT(*) FROM sync_history WHERE source_key = ?",
                              (event.source_key,)).fetchone()[0]
    assert row_count == 1


def test_dry_run_reports_new_then_unchanged(tmp_db_path):
    conn = get_connection(tmp_db_path)
    service = FakeCalendarService()
    event = make_event()

    result_before = dry_run(conn, [event])
    assert result_before.plans[0].action == ACTION_NEW

    sync_events(conn, service, "primary", [event])

    result_after = dry_run(conn, [event])
    assert result_after.plans[0].action == ACTION_UNCHANGED


def test_dry_run_reports_update_when_content_changes(tmp_db_path):
    conn = get_connection(tmp_db_path)
    service = FakeCalendarService()
    event = make_event()
    sync_events(conn, service, "primary", [event])

    event.title = "英会話｜変更後のタイトル"
    result = dry_run(conn, [event])
    assert result.plans[0].action == ACTION_UPDATE

    sync_events(conn, service, "primary", [event])
    assert len(service.updated) == 1
    assert len(service.inserted) == 1  # 新規登録は1回のまま


def test_find_duplicate_source_keys():
    e1 = make_event(source_key="web|DUP")
    e2 = make_event(source_key="web|DUP")
    e3 = make_event(source_key="web|UNIQUE")
    dups = find_duplicate_source_keys([e1, e2, e3])
    assert dups == ["web|DUP"]


def test_delete_candidates_are_not_auto_deleted(tmp_db_path):
    conn = get_connection(tmp_db_path)
    service = FakeCalendarService()
    event = make_event(source_key="web|WILL_DISAPPEAR")
    sync_events(conn, service, "primary", [event])

    # 今回の一覧にはこの予定が含まれない(Web一覧から消えたケースを模擬)
    candidates = find_delete_candidates(conn, current_events=[])
    assert len(candidates) == 1
    assert candidates[0].source_key == "web|WILL_DISAPPEAR"
    # 自動削除はしていないことを確認(FakeCalendarServiceのdeleteは呼ばれていない)
    assert service.deleted == []


def test_invalid_time_range_is_error(tmp_db_path):
    conn = get_connection(tmp_db_path)
    event = make_event()
    event.end_datetime = event.start_datetime - timedelta(minutes=10)
    result = dry_run(conn, [event])
    assert result.error_count == 1
