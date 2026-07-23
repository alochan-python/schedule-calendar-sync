"""日時文字列解析の共通ユーティリティ。

Excel解析・Web解析の双方で、全角/半角の揺れや、
「～」「〜」「-」などの区切り文字の違いを吸収するために使用する。
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import NamedTuple, Optional

KANJI_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# 時刻の範囲区切り文字として許容する文字(半角ハイフン、波ダッシュ、全角チルダ等)
_RANGE_SEP = r"[-−〜～~]"

# 空白として扱う文字(半角スペース、全角スペース、タブ、ノーブレークスペース)
_WS = r"[ \t　\xa0]"

# 例: 7/27(月)20:00-21:30 / 7/27（月）20:00〜21:30
EXCEL_DATETIME_PATTERN = re.compile(
    r"(?P<month>\d{1,2})\s*/\s*(?P<day>\d{1,2})\s*[（(](?P<weekday>[月火水木金土日])[）)]\s*"
    r"(?P<start_h>\d{1,2}):(?P<start_m>\d{2})\s*" + _RANGE_SEP + r"\s*"
    r"(?P<end_h>\d{1,2}):(?P<end_m>\d{2})"
)

# 例: 07月03日(金) 19:30～20:30
WEB_DATETIME_PATTERN = re.compile(
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日\s*[（(](?P<weekday>[月火水木金土日])[）)]"
    + _WS + r"*"
    r"(?P<start_h>\d{1,2}):(?P<start_m>\d{2})\s*" + _RANGE_SEP + r"\s*"
    r"(?P<end_h>\d{1,2}):(?P<end_m>\d{2})"
)


class DateTimeCandidate(NamedTuple):
    date: date
    weekday_written: str
    weekday_actual: str
    weekday_mismatch: bool
    start_time: time
    end_time: time
    raw_match: str


def normalize_whitespace(text: str) -> str:
    """タブ・全角スペース・NBSPなどを半角スペース1つに正規化する(改行は保持)。"""
    if text is None:
        return ""
    lines = text.split("\n")
    normalized_lines = [re.sub(_WS + r"+", " ", line).strip() for line in lines]
    return "\n".join(normalized_lines)


def actual_weekday_kanji(d: date) -> str:
    return KANJI_WEEKDAYS[d.weekday()]


def _build_candidate(match: re.Match, year: int) -> Optional[DateTimeCandidate]:
    month = int(match.group("month"))
    day = int(match.group("day"))
    weekday_written = match.group("weekday")
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    start_t = time(int(match.group("start_h")), int(match.group("start_m")))
    end_t = time(int(match.group("end_h")), int(match.group("end_m")))
    actual = actual_weekday_kanji(d)
    return DateTimeCandidate(
        date=d,
        weekday_written=weekday_written,
        weekday_actual=actual,
        weekday_mismatch=(actual != weekday_written),
        start_time=start_t,
        end_time=end_t,
        raw_match=match.group(0),
    )


def find_excel_datetime_candidates(text: str, year: int) -> list[DateTimeCandidate]:
    """Excelセル内のテキストから「M/D(曜)HH:MM-HH:MM」形式の候補をすべて抽出する。"""
    if not text:
        return []
    candidates = []
    for m in EXCEL_DATETIME_PATTERN.finditer(text):
        c = _build_candidate(m, year)
        if c is not None:
            candidates.append(c)
    return candidates


def find_web_datetime_candidate(text: str, year: int) -> Optional[DateTimeCandidate]:
    """Web予約テキストから「MM月DD日(曜) HH:MM～HH:MM」形式の候補を1件抽出する。"""
    if not text:
        return None
    m = WEB_DATETIME_PATTERN.search(text)
    if m is None:
        return None
    return _build_candidate(m, year)


def combine(d: date, t: time) -> datetime:
    return datetime.combine(d, t)
