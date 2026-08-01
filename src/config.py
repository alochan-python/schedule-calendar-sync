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
DEFAULT_CALENDAR_CANDIDATES = ["primary", "学習予定", "英会話", "講義予定"]

# --- 通知(リマインダー)設定 ---
# ラベル -> 分前 の対応。選択肢の表示順としても使う。
REMINDER_PRESETS: dict[str, int] = {
    "5分前": 5,
    "10分前": 10,
    "15分前": 15,
    "30分前": 30,
    "1時間前": 60,
    "2時間前": 120,
    "3時間前": 180,
    "6時間前": 360,
    "12時間前": 720,
    "1日前": 1440,
    "2日前": 2880,
    "3日前": 4320,
    "1週間前": 10080,
}
# 初期値: 2時間前・1日前(何も選択しない場合は「通知なし」になる)
DEFAULT_REMINDER_LABELS: list[str] = ["2時間前", "1日前"]
DEFAULT_REMINDER_MINUTES: list[int] = [REMINDER_PRESETS[label] for label in DEFAULT_REMINDER_LABELS]


def minutes_to_label(minutes: int) -> str:
    """分前の値を表示用ラベルへ変換する(プリセットに無い値はそのまま「N分前」)。"""
    for label, value in REMINDER_PRESETS.items():
        if value == minutes:
            return label
    return f"{minutes}分前"

# --- Google Calendar API スコープ ---
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def google_credentials_available() -> bool:
    """credentials.json が存在するかどうか(=Google連携設定済みかどうか)を返す。"""
    return GOOGLE_CREDENTIALS_PATH.exists()


def google_token_available() -> bool:
    return GOOGLE_TOKEN_PATH.exists()
