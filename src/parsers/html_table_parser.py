"""ログイン後ページを保存したHTMLファイルからtable要素を抽出するパーサー。

複数のtableが存在する場合はすべて抽出してプレビュー用に返し、
呼び出し側(Streamlit画面)でユーザーに対象の表を選択させる想定。

注意: サイトごとにHTML構造が異なるため、1つの<td>に「日付(曜)時刻」が
まとまって入っている構造を前提としている(表テキスト貼り付けと同じ列構成)。
実際のHTML構造が判明した際は、この前提を調整すること。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from src.parsers.web_text_parser import WebParseResult, columns_to_event


@dataclass
class ExtractedTable:
    index: int
    rows: list[list[str]] = field(default_factory=list)

    def preview_rows(self, limit: int = 5) -> list[list[str]]:
        return self.rows[:limit]


def extract_tables(html: str) -> list[ExtractedTable]:
    """HTML内のすべてのtable要素を抽出する。"""
    soup = BeautifulSoup(html, "lxml")
    tables: list[ExtractedTable] = []
    for idx, table in enumerate(soup.find_all("table")):
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c != ""]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(ExtractedTable(index=idx, rows=rows))
    return tables


def parse_table_rows(rows: list[list[str]], target_year: int, source_file: str = "web_html") -> WebParseResult:
    """抽出済みの表データ(行のリスト)をScheduleEventのリストへ変換する。"""
    result = WebParseResult()
    for row_no, columns in enumerate(rows, start=1):
        raw_text = " ".join(columns)
        event, error, mismatch = columns_to_event(columns, target_year, source_file, raw_text)
        if error is not None:
            result.errors.append(f"{row_no}行目: {error}: {raw_text}")
            continue
        if mismatch and event is not None:
            result.warnings.append(
                f"{row_no}行目: 曜日不一致の可能性があります(記載の曜日と実際の曜日が異なります): {raw_text}"
            )
        if event is not None:
            result.events.append(event)
    return result
