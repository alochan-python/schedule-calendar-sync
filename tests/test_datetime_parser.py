from __future__ import annotations

from datetime import date, time

from src.parsers.datetime_utils import (
    find_excel_datetime_candidates,
    find_web_datetime_candidate,
)


def test_excel_datetime_basic():
    candidates = find_excel_datetime_candidates("7/27(月)20:00-21:30", 2026)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.date == date(2026, 7, 27)
    assert c.start_time == time(20, 0)
    assert c.end_time == time(21, 30)
    assert c.weekday_mismatch is False


def test_excel_datetime_multiple_candidates_in_one_cell():
    text = "7/27(月)20:00-21:30\n8/1(土)13:00-14:30"
    candidates = find_excel_datetime_candidates(text, 2026)
    assert len(candidates) == 2
    assert candidates[0].date == date(2026, 7, 27)
    assert candidates[1].date == date(2026, 8, 1)


def test_excel_datetime_weekday_mismatch_detected():
    # 2026-11-01 の実際の曜日は日曜日だが、月と誤記した場合
    candidates = find_excel_datetime_candidates("11/1(月)10:00-11:30", 2026)
    assert len(candidates) == 1
    assert candidates[0].weekday_mismatch is True
    assert candidates[0].weekday_actual == "日"


def test_excel_datetime_year_is_applied():
    candidates = find_excel_datetime_candidates("10/17(土)13:00-15:00", 2030)
    assert candidates[0].date.year == 2030


def test_web_datetime_half_width_hyphen():
    c = find_web_datetime_candidate("07月03日(金) 19:30-20:30", 2026)
    assert c is not None
    assert c.date == date(2026, 7, 3)
    assert c.start_time == time(19, 30)
    assert c.end_time == time(20, 30)


def test_web_datetime_fullwidth_tilde():
    c = find_web_datetime_candidate("07月04日(土) 15:35～16:00", 2026)
    assert c is not None
    assert c.start_time == time(15, 35)
    assert c.end_time == time(16, 0)


def test_web_datetime_wave_dash():
    c = find_web_datetime_candidate("07月05日(日) 10:35〜11:00", 2026)
    assert c is not None
    assert c.end_time == time(11, 0)


def test_web_datetime_weekday_mismatch():
    # 2026-07-03 の実際の曜日は金曜日
    c = find_web_datetime_candidate("07月03日(月) 19:30～20:30", 2026)
    assert c is not None
    assert c.weekday_mismatch is True
    assert c.weekday_written == "月"
    assert c.weekday_actual == "金"
