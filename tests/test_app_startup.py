from __future__ import annotations

from datetime import datetime, timedelta

from src.models import ScheduleEvent
from src.services.google_calendar_service import GoogleCalendarService


def test_google_calendar_service_importable_and_not_configured(monkeypatch, tmp_path):
    import src.config as config

    monkeypatch.setattr(config, "GOOGLE_CREDENTIALS_PATH", tmp_path / "credentials.json")
    assert GoogleCalendarService.is_configured() is False

    # credentials.jsonが無くてもインスタンス化はできる(アプリ起動時にエラーにしない)
    service = GoogleCalendarService()
    assert service.is_connected() is False


def test_google_calendar_service_raises_only_when_api_actually_used(monkeypatch, tmp_path):
    import src.config as config
    from src.services.google_calendar_service import GoogleCalendarNotConfiguredError

    monkeypatch.setattr(config, "GOOGLE_CREDENTIALS_PATH", tmp_path / "credentials.json")
    service = GoogleCalendarService()
    try:
        service.connect()
        assert False, "credentials.json が無いのに例外が発生しませんでした"
    except GoogleCalendarNotConfiguredError:
        pass


def test_app_module_imports_without_google_credentials(monkeypatch, tmp_path):
    """Google認証情報が無い状態でも app.py がインポート(=起動)できることを確認する。"""
    import importlib

    import src.config as config

    monkeypatch.setattr(config, "GOOGLE_CREDENTIALS_PATH", tmp_path / "credentials.json")
    monkeypatch.setattr(config, "GOOGLE_TOKEN_PATH", tmp_path / "token.json")

    import app  # noqa: F401
    importlib.reload(app)


def test_filter_events_past_does_not_remove_from_store():
    import app

    past_start = datetime.now() - timedelta(days=10)
    past_event = ScheduleEvent(
        source_type="web", source_file="t", source_key="web|PAST",
        title="過去の予定",
        start_datetime=past_start,
        end_datetime=past_start + timedelta(hours=1),
    )
    future_event = ScheduleEvent(
        source_type="web", source_file="t", source_key="web|FUTURE",
        title="今後の予定",
        start_datetime=datetime.now() + timedelta(days=10),
        end_datetime=datetime.now() + timedelta(days=10, hours=1),
    )
    all_events = [past_event, future_event]

    past_only = app.filter_events(all_events, "過去")
    all_only = app.filter_events(all_events, "すべて")

    assert past_event in past_only
    # 「過去」で絞り込んでも元のリスト(=保存されている全予定)からは削除されない
    assert past_event in all_only
    assert future_event in all_only
    assert len(all_only) == 2
