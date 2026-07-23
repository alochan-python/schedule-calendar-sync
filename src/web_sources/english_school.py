"""英会話スクール予約サイト向けのWeb自動取得(将来実装のスケルトン)。

MVPでは未実装。実際のログインURL・HTML構造が判明した後、
WebSource を継承して実装することを想定している。

実装イメージ(Playwrightを使う場合):

    from playwright.sync_api import sync_playwright

    class EnglishSchoolWebSource(WebSource):
        def is_logged_in(self) -> bool:
            return Path(self.config.auth_storage_path).exists()

        def login_manually(self) -> None:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(self.config.login_url)
                input("ブラウザでログインしてください。完了したらEnterキーを押してください: ")
                context.storage_state(path=self.config.auth_storage_path)
                browser.close()

        def fetch_schedule_html(self) -> str:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(storage_state=self.config.auth_storage_path)
                page = context.new_page()
                page.goto(self.config.schedule_url)
                html = page.content()
                browser.close()
                return html

パスワードは絶対にコードへ書かない。ユーザーが最初の1回だけ手動ログインし、
その状態を config.auth_storage_path (playwright/.auth/ 配下、Git管理外) に保存する方式とする。
"""
from __future__ import annotations

from src.web_sources.base import WebSource, WebSourceConfig

__all__ = ["WebSource", "WebSourceConfig"]

# NOTE: MVP完成時点では未実装。config/web_sources.local.yaml にサイト情報を
#       用意したうえで、上記の実装イメージを参考にクラスを追加すること。
