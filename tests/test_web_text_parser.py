from __future__ import annotations

from datetime import datetime

from src.parsers.web_text_parser import parse_web_schedule_text


def test_web_sample_25_events(sample_web_text):
    result = parse_web_schedule_text(sample_web_text, target_year=2026)
    assert len(result.events) == 25
    assert result.errors == []


def test_web_sample_start_end_times(sample_web_text):
    result = parse_web_schedule_text(sample_web_text, target_year=2026)
    first = result.events[0]
    assert first.start_datetime == datetime(2026, 7, 3, 19, 30)
    assert first.end_datetime == datetime(2026, 7, 3, 20, 30)


def test_web_location_net_converted_to_online():
    text = "07月04日(土) 15:35～16:00\tネット\tG07014\tDSK\t旅行FCフレーズ【A13】オンラインレッスン"
    result = parse_web_schedule_text(text, target_year=2026)
    assert len(result.events) == 1
    event = result.events[0]
    assert event.location == "オンライン"
    assert event.original_location == "ネット"


def test_web_title_format():
    text = "07月04日(土) 15:35～16:00\tネット\tG07014\tDSK\t旅行FCフレーズ【A13】オンラインレッスン"
    result = parse_web_schedule_text(text, target_year=2026)
    assert result.events[0].title == "英会話｜旅行FCフレーズ【A13】"


def test_web_tab_separated():
    text = "07月03日(金) 19:30～20:30\t梅田\t70308\tSRA\t日常アクション10x10【A3】"
    result = parse_web_schedule_text(text, target_year=2026)
    assert len(result.events) == 1
    assert result.events[0].location == "梅田"


def test_web_multiple_spaces_separated():
    text = "07月03日(金) 19:30～20:30    梅田    70308    SRA    日常アクション10x10【A3】"
    result = parse_web_schedule_text(text, target_year=2026)
    assert len(result.events) == 1


def test_web_fullwidth_space_separated():
    text = "07月03日(金) 19:30～20:30　　梅田　　70308　　SRA　　日常アクション"
    result = parse_web_schedule_text(text, target_year=2026)
    assert len(result.events) == 1


def test_web_source_key_uses_reservation_code():
    text = "07月04日(土) 15:35～16:00\tネット\tG07014\tDSK\tレッスン"
    result = parse_web_schedule_text(text, target_year=2026)
    assert result.events[0].source_key == "web|G07014"


def test_web_weekday_mismatch_warning():
    text = "07月03日(月) 19:30～20:30\t梅田\t70308\tSRA\t日常アクション"
    result = parse_web_schedule_text(text, target_year=2026)
    assert len(result.events) == 1
    assert len(result.warnings) == 1


def test_web_year_applied():
    text = "07月03日(金) 19:30～20:30\t梅田\t70308\tSRA\t日常アクション"
    result = parse_web_schedule_text(text, target_year=2031)
    assert result.events[0].start_datetime.year == 2031
