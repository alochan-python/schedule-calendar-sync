"""ScheduleEventのリストをCSVへ出力するサービス。

Google Calendar APIを設定していなくても利用できる機能。
"""
from __future__ import annotations

import csv
import io

from src.models import ScheduleEvent

_DATETIME_FMT = "%Y-%m-%d %H:%M"
_GOOGLE_DATETIME_FMT = "%m/%d/%Y %I:%M %p"


def to_normalized_csv(events: list[ScheduleEvent]) -> str:
    """正規化済みCSV(ScheduleEventの全項目)を生成する。"""
    buf = io.StringIO()
    fieldnames = [
        "選択", "登録状態", "取込元", "コース", "回", "件名",
        "開始日時", "終了日時", "場所", "講師", "予約番号", "状態",
        "説明", "source_key",
    ]
    writer = csv.writer(buf)
    writer.writerow(fieldnames)
    for e in events:
        writer.writerow([
            "○" if e.selected else "",
            e.sync_status,
            "Excel" if e.source_type == "excel" else "Web",
            e.course,
            e.session_name,
            e.title,
            e.start_datetime.strftime(_DATETIME_FMT) if e.start_datetime else "",
            e.end_datetime.strftime(_DATETIME_FMT) if e.end_datetime else "",
            e.location,
            e.instructor,
            e.reservation_code,
            e.status,
            e.description,
            e.source_key,
        ])
    return buf.getvalue()


def to_google_calendar_csv(events: list[ScheduleEvent]) -> str:
    """Googleカレンダーの旧CSVインポート形式互換のCSVを生成する。

    列: Subject, Start Date, Start Time, End Date, End Time, Description, Location
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Subject", "Start Date", "Start Time", "End Date", "End Time", "Description", "Location"])
    for e in events:
        if e.start_datetime is None or e.end_datetime is None:
            continue
        writer.writerow([
            e.title,
            e.start_datetime.strftime("%m/%d/%Y"),
            e.start_datetime.strftime("%I:%M %p"),
            e.end_datetime.strftime("%m/%d/%Y"),
            e.end_datetime.strftime("%I:%M %p"),
            e.description,
            e.location,
        ])
    return buf.getvalue()
