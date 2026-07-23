"""アプリ全体の設定値・パス定義。

.env が存在すれば読み込み、無ければ既定値を使用する。
Google Calendar APIの認証ファイルが無くてもアプリが起動できることを前提とする。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- .env の簡易読み込み(python-dotenv非依存で十分なため自前実装) ---


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / ".env")

# --- パス設定 ---
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", str(DATA_DIR / "schedule_sync.db")))
GOOGLE_CREDENTIALS_PATH = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH", str(BASE_DIR / "credentials.json")))
GOOGLE_TOKEN_PATH = Path(os.environ.get("GOOGLE_TOKEN_PATH", str(BASE_DIR / "token.json")))
WEB_SOURCES_CONFIG_PATH = BASE_DIR / "config" / "web_sources.local.yaml"

# --- タイムゾーン ---
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Tokyo")

# --- 既定値 ---
DEFAULT_TARGET_YEAR = 2026
DEFAULT_REMINDER_MINUTES = 15
DEFAULT_CALENDAR_CANDIDATES = ["primary", "学習予定", "英会話", "講義予定"]

# --- Google Calendar API スコープ ---
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def google_credentials_available() -> bool:
    """credentials.json が存在するかどうか(=Google連携設定済みかどうか)を返す。"""
    return GOOGLE_CREDENTIALS_PATH.exists()


def google_token_available() -> bool:
    return GOOGLE_TOKEN_PATH.exists()
