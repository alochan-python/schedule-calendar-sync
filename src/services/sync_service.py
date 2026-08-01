"""Googleカレンダーへの同期処理(重複登録防止・ドライラン・削除候補検出)。

SQLite(sync_history)にsource_key <-> google_event_idの対応を保存し、
再同期時に同じsource_keyへは新規登録せず、内容が変わっていれば更新する。
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.database import (
    SyncRecord,
    compute_content_hash,
    delete_record,
    get_all_records,
    get_record,
    upsert_record,
)
from src.models import ScheduleEvent
from src.services.google_calendar_service import GoogleCalendarService

ACTION_NEW = "新規登録"
ACTION_UPDATE = "更新"
ACTION_UNCHANGED = "変更なし"
ACTION_SKIP = "スキップ(変更しない)"
ACTION_ERROR = "エラー"

CONFLICT_UPDATE = "更新する"
CONFLICT_INSERT_NEW = "新規登録する"
CONFLICT_SKIP = "変更しない"


@dataclass
class EventPlan:
    event: ScheduleEvent
    action: str
    reason: str = ""


@dataclass
class DryRunResult:
    plans: list[EventPlan] = field(default_factory=list)

    @property
    def counts(self) -> Counter:
        return Counter(p.action for p in self.plans)

    @property
    def new_count(self) -> int:
        return self.counts.get(ACTION_NEW, 0)

    @property
    def update_count(self) -> int:
        return self.counts.get(ACTION_UPDATE, 0)

    @property
    def unchanged_count(self) -> int:
        return self.counts.get(ACTION_UNCHANGED, 0)

    @property
    def error_count(self) -> int:
        return self.counts.get(ACTION_ERROR, 0)


@dataclass
class SyncOutcome:
    event: ScheduleEvent
    result: str  # "成功(新規)" / "成功(更新)" / "スキップ" / "失敗"
    google_event_id: Optional[str] = None
    error_message: str = ""


def find_duplicate_source_keys(events: list[ScheduleEvent]) -> list[str]:
    """同一バッチ内でsource_keyが重複しているものを検出する。"""
    counter = Counter(e.source_key for e in events)
    return [key for key, count in counter.items() if count > 1]


def _event_content_hash(event: ScheduleEvent) -> str:
    return compute_content_hash(
        title=event.title,
        start_datetime=event.start_datetime.isoformat() if event.start_datetime else "",
        end_datetime=event.end_datetime.isoformat() if event.end_datetime else "",
        location=event.location,
        description=event.description,
    )


def plan_event(conn: sqlite3.Connection, event: ScheduleEvent, conflict_mode: str = CONFLICT_UPDATE) -> EventPlan:
    if not event.is_valid_time_range():
        return EventPlan(event, ACTION_ERROR, "開始日時が終了日時以降になっています")

    record = get_record(conn, event.source_key)
    current_hash = _event_content_hash(event)

    if record is None or not record.google_event_id:
        return EventPlan(event, ACTION_NEW, "未登録のため新規登録します")

    if record.content_hash == current_hash:
        return EventPlan(event, ACTION_UNCHANGED, "前回登録時から内容が変わっていません")

    if conflict_mode == CONFLICT_UPDATE:
        return EventPlan(event, ACTION_UPDATE, "内容が変更されているため更新します")
    if conflict_mode == CONFLICT_INSERT_NEW:
        return EventPlan(event, ACTION_NEW, "内容が変更されていますが、新規登録として扱います")
    return EventPlan(event, ACTION_SKIP, "内容は変更されていますが、変更しない設定のためスキップします")


def dry_run(conn: sqlite3.Connection, events: list[ScheduleEvent], conflict_mode: str = CONFLICT_UPDATE) -> DryRunResult:
    """実際には登録せず、各予定がどう扱われるかを判定する。"""
    result = DryRunResult()
    for event in events:
        result.plans.append(plan_event(conn, event, conflict_mode))
    return result


def sync_events(
    conn: sqlite3.Connection,
    calendar_service: GoogleCalendarService,
    calendar_id: str,
    events: list[ScheduleEvent],
    conflict_mode: str = CONFLICT_UPDATE,
    reminder_minutes: Optional[list[int]] = None,
) -> list[SyncOutcome]:
    """予定をGoogleカレンダーへ実際に登録・更新する。"""
    outcomes: list[SyncOutcome] = []

    for event in events:
        plan = plan_event(conn, event, conflict_mode)

        if plan.action == ACTION_ERROR:
            outcomes.append(SyncOutcome(event, "失敗", error_message=plan.reason))
            continue
        if plan.action == ACTION_UNCHANGED:
            outcomes.append(SyncOutcome(event, "スキップ", google_event_id=event.google_event_id))
            continue
        if plan.action == ACTION_SKIP:
            outcomes.append(SyncOutcome(event, "スキップ", google_event_id=event.google_event_id))
            continue

        try:
            record = get_record(conn, event.source_key)
            content_hash = _event_content_hash(event)
            if plan.action == ACTION_UPDATE and record and record.google_event_id:
                google_event_id = calendar_service.update_event(
                    calendar_id, record.google_event_id, event, reminder_minutes
                )
                result_label = "成功(更新)"
            else:
                google_event_id = calendar_service.insert_event(calendar_id, event, reminder_minutes)
                result_label = "成功(新規)"

            upsert_record(
                conn,
                SyncRecord(
                    source_key=event.source_key,
                    google_event_id=google_event_id,
                    calendar_id=calendar_id,
                    last_synced_at=datetime.now().isoformat(),
                    content_hash=content_hash,
                    sync_status=result_label,
                    title=event.title,
                    start_datetime=event.start_datetime.isoformat() if event.start_datetime else "",
                    end_datetime=event.end_datetime.isoformat() if event.end_datetime else "",
                ),
            )
            outcomes.append(SyncOutcome(event, result_label, google_event_id=google_event_id))
        except Exception as exc:  # noqa: BLE001 - 失敗理由をUIへそのまま表示するため捕捉する
            outcomes.append(SyncOutcome(event, "失敗", error_message=str(exc)))

    return outcomes


def find_delete_candidates(conn: sqlite3.Connection, current_events: list[ScheduleEvent]) -> list[SyncRecord]:
    """以前登録済みだが、今回の一覧に存在しない予定を削除候補として返す。

    自動削除は行わない(呼び出し側でユーザーの明示的な選択・確認を必須とする)。
    """
    current_keys = {e.source_key for e in current_events}
    candidates = []
    for record in get_all_records(conn):
        if record.google_event_id and record.source_key not in current_keys:
            candidates.append(record)
    return candidates


def delete_events(
    conn: sqlite3.Connection,
    calendar_service: GoogleCalendarService,
    source_keys: list[str],
) -> list[tuple[str, bool, str]]:
    """ユーザーが選択・確認したsource_keyの予定をGoogleカレンダーとDBから削除する。

    戻り値: (source_key, 成功したか, エラーメッセージ) のリスト
    """
    results = []
    for source_key in source_keys:
        record = get_record(conn, source_key)
        if record is None or not record.google_event_id or not record.calendar_id:
            results.append((source_key, False, "同期履歴が見つかりません"))
            continue
        try:
            calendar_service.delete_event(record.calendar_id, record.google_event_id)
            delete_record(conn, source_key)
            results.append((source_key, True, ""))
        except Exception as exc:  # noqa: BLE001
            results.append((source_key, False, str(exc)))
    return results
