"""Web自動取得機能(将来追加分)のための共通インターフェース。

MVPでは実際の自動ログイン・自動取得は行わない。
このモジュールは、後から Playwright 等を使った自動取得を追加しやすくするための
拡張ポイントとして用意している。

追加方法の例は README.md の「Web自動取得機能を追加するには」を参照。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.parsers.web_text_parser import WebParseResult


@dataclass
class WebSourceConfig:
    """config/web_sources.local.yaml から読み込む、サイト固有の設定。

    URLやCSSセレクタなどのサイト固有情報はコードへ直接埋め込まず、
    この設定オブジェクト経由で扱う想定。
    """

    name: str
    login_url: str = ""
    schedule_url: str = ""
    table_selector: str = ""
    auth_storage_path: str = "playwright/.auth/state.json"


class WebSource(ABC):
    """Web予約サイトからスケジュールを取得するための共通インターフェース。

    実装クラスの例: src/web_sources/english_school.py (未実装・将来追加)
    """

    def __init__(self, config: WebSourceConfig) -> None:
        self.config = config

    @abstractmethod
    def is_logged_in(self) -> bool:
        """保存済みのログイン状態が有効かどうかを返す。"""
        raise NotImplementedError

    @abstractmethod
    def login_manually(self) -> None:
        """ブラウザを開いてユーザーに手動ログインしてもらい、状態を保存する。

        パスワードはコードに書かず、ユーザーがブラウザ上で入力する。
        ログイン状態は config.auth_storage_path (例: playwright/.auth/) へ保存する。
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_schedule_html(self) -> str:
        """ログイン状態を使ってスケジュールページのHTMLを取得する。"""
        raise NotImplementedError

    def fetch_and_parse(self, target_year: int) -> WebParseResult:
        """HTML取得 + 既存のhtml_table_parserによる解析をまとめて行うヘルパー。"""
        from src.parsers.html_table_parser import extract_tables, parse_table_rows

        html = self.fetch_schedule_html()
        tables = extract_tables(html)
        if not tables:
            return WebParseResult(errors=["表(table)が見つかりませんでした"])
        # 既定では最初に見つかった表を使う。複数ある場合はUI側での選択を推奨。
        return parse_table_rows(tables[0].rows, target_year, source_file=self.config.name)
