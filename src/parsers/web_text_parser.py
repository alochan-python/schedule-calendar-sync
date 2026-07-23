"""Webページの表テキスト貼り付けを解析するパーサー。

ログイン後の予約一覧ページからコピーした表形式テキストを、
タブ・複数スペース・改行区切りとして解析し、ScheduleEventのリストへ変換する。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models import (
    SOURCE_TYPE_WEB,
    STATUS_CONFIRMED,
    ScheduleEvent,
    make_web_source_key,
)
from src.parsers.datetime_utils import combine, find_web_datetime_candidate

# 列区切り: タブの連続、または半角/全角スペース・NBSPの2文字以上の連続
_COLUMN_SPLIT_PATTERN = re.compile(r"\t+|[ 　\xa0]{2,}")

_RESERVATION_TYPE_SUFFIXES = ["オンラインレッスン", "対面レッスン", "来校レッスン"]


@dataclass
class WebParseResult:
    events: list[ScheduleEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def split_columns(line: str) -> list[str]:
    return [c for c in _COLUMN_SPLIT_PATTERN.split(line.strip()) if c.strip() != ""]


def _extract_reservation_type(lesson_name_raw: str, location_raw: str) -> tuple[str, str]:
    for suffix in _RESERVATION_TYPE_SUFFIXES:
        if lesson_name_raw.endswith(suffix):
            return lesson_name_raw[: -len(suffix)].strip(), suffix
    if location_raw in ("ネット", "オンライン"):
        return lesson_name_raw, "オンラインレッスン"
    return lesson_name_raw, "来校レッスン"


def _build_description(instructor: str, reservation_code: str, reservation_type: str,
                        extra_status: str, location_raw: str) -> str:
    lines = [
        f"講師: {instructor}",
        f"予約番号: {reservation_code}",
        f"予約種別: {reservation_type}",
        f"状態: {extra_status or '-'}",
        "取込元: Web(表テキスト貼り付け)",
        f"元の場所表記: {location_raw}",
    ]
    return "\n".join(lines)


def columns_to_event(columns: list[str], target_year: int, source_file: str,
                      raw_text: str) -> tuple[ScheduleEvent | None, str | None, bool]:
    """列リストを1件のScheduleEventへ変換する。

    戻り値: (イベント or None, エラーメッセージ or None, 曜日不一致フラグ)
    """
    if len(columns) < 2:
        return None, "列数が不足しているため解析できません", False

    datetime_part = columns[0]
    candidate = find_web_datetime_candidate(datetime_part, target_year)
    if candidate is None:
        return None, "日時を解析できません", False

    location_raw = columns[1] if len(columns) > 1 else ""
    reservation_code = columns[2] if len(columns) > 2 else ""
    instructor = columns[3] if len(columns) > 3 else ""
    lesson_name_raw = columns[4] if len(columns) > 4 else ""
    extra_status = " ".join(columns[5:]) if len(columns) > 5 else ""

    lesson_name, reservation_type = _extract_reservation_type(lesson_name_raw, location_raw)
    location_display = "オンライン" if location_raw == "ネット" else location_raw

    start_dt = combine(candidate.date, candidate.start_time)
    end_dt = combine(candidate.date, candidate.end_time)

    description = _build_description(instructor, reservation_code, reservation_type, extra_status, location_raw)

    event = ScheduleEvent(
        source_type=SOURCE_TYPE_WEB,
        source_file=source_file,
        source_key=make_web_source_key(reservation_code),
        title=f"英会話｜{lesson_name}" if lesson_name else "英会話｜(レッスン名不明)",
        start_datetime=start_dt,
        end_datetime=end_dt,
        location=location_display,
        instructor=instructor,
        reservation_code=reservation_code,
        description=description,
        status=STATUS_CONFIRMED,
        selected=True,
        weekday=candidate.weekday_written,
        reservation_type=reservation_type,
        raw_text=raw_text,
        original_location=location_raw,
    )
    return event, None, candidate.weekday_mismatch


def parse_web_schedule_text(text: str, target_year: int, source_file: str = "web_text") -> WebParseResult:
    """表テキスト貼り付けを解析し、WebParseResultを返す。"""
    result = WebParseResult()
    if not text:
        return result

    lines = [line for line in text.split("\n") if line.strip() != ""]
    for line_no, line in enumerate(lines, start=1):
        columns = split_columns(line)
        event, error, mismatch = columns_to_event(columns, target_year, source_file, line)
        if error is not None:
            result.errors.append(f"{line_no}行目: {error}: {line}")
            continue
        if mismatch and event is not None:
            result.warnings.append(
                f"{line_no}行目: 曜日不一致の可能性があります(記載の曜日と実際の曜日が異なります): {line}"
            )
        if event is not None:
            result.events.append(event)

    return result
