"""schedule-calendar-sync: Streamlitアプリのエントリポイント。

Excel講義スケジュール・Web予約一覧を取り込み、内容を確認・編集したうえで
Googleカレンダーへ同期するためのローカルWebアプリ。

起動方法:
    streamlit run app.py
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from src.config import (
    DEFAULT_CALENDAR_CANDIDATES,
    DEFAULT_REMINDER_LABELS,
    DEFAULT_TARGET_YEAR,
    REMINDER_PRESETS,
)
from src.database import get_all_records, get_connection
from src.models import (
    COURSE_AI_ANALYSIS,
    COURSE_AI_IMPLEMENTATION,
    SOURCE_TYPE_EXCEL,
    SOURCE_TYPE_WEB,
    STATUS_CANDIDATE,
    STATUS_CONFIRMED,
    STATUS_TENTATIVE,
    SYNC_STATUS_NOT_SYNCED,
    SYNC_STATUS_SYNCED,
    ScheduleEvent,
)
from src.parsers.excel_schedule_parser import group_by_round, parse_excel_schedule
from src.parsers.html_table_parser import extract_tables, parse_table_rows
from src.parsers.web_text_parser import parse_web_schedule_text
from src.services.csv_export_service import to_google_calendar_csv, to_normalized_csv
from src.services.google_calendar_service import GoogleCalendarService
from src.services.ics_export_service import build_ics
from src.services.sync_service import (
    CONFLICT_INSERT_NEW,
    CONFLICT_SKIP,
    CONFLICT_UPDATE,
    dry_run,
    find_delete_candidates,
    find_duplicate_source_keys,
    sync_events,
)

PAGES = ["ホーム", "Excel取込", "Web取込", "予定確認・編集", "Googleカレンダー連携", "登録履歴・設定"]


# ============================================================
# セッション状態の初期化
# ============================================================

def init_session_state() -> None:
    if "events" not in st.session_state:
        st.session_state.events = {}  # source_key -> ScheduleEvent
    if "excel_parse_result" not in st.session_state:
        st.session_state.excel_parse_result = None
    if "web_text_parse_result" not in st.session_state:
        st.session_state.web_text_parse_result = None
    if "web_html_parse_result" not in st.session_state:
        st.session_state.web_html_parse_result = None
    if "html_tables" not in st.session_state:
        st.session_state.html_tables = None
    if "calendar_id" not in st.session_state:
        st.session_state.calendar_id = "primary"
    if "reminder_labels" not in st.session_state:
        st.session_state.reminder_labels = list(DEFAULT_REMINDER_LABELS)
    if "conflict_mode" not in st.session_state:
        st.session_state.conflict_mode = CONFLICT_UPDATE
    if "last_sync_outcomes" not in st.session_state:
        st.session_state.last_sync_outcomes = []
    if "gcal_service" not in st.session_state:
        st.session_state.gcal_service = GoogleCalendarService()


def get_conn():
    return get_connection()


def all_events() -> list[ScheduleEvent]:
    return list(st.session_state.events.values())


def add_events(events: list[ScheduleEvent]) -> int:
    added = 0
    for e in events:
        if e.source_key not in st.session_state.events:
            added += 1
        st.session_state.events[e.source_key] = e
    return added


def remove_events(source_keys: list[str]) -> int:
    removed = 0
    for key in source_keys:
        if st.session_state.events.pop(key, None) is not None:
            removed += 1
    return removed


def reminder_minutes_from_labels(labels: list[str]) -> list[int]:
    """通知ラベル(例: ["2時間前", "1日前"])を分前の数値リストへ変換する。空なら通知なし。"""
    return sorted({REMINDER_PRESETS[label] for label in labels if label in REMINDER_PRESETS})


# ============================================================
# ヘルプ(モーダルダイアログ)
# ============================================================

@st.dialog("使い方ヘルプ", width="large")
def show_help_dialog() -> None:
    st.markdown(HELP_TEXT)
    if st.button("閉じる"):
        st.rerun()


HELP_TEXT = """
### このアプリでできること
Excelの講義スケジュールや、英会話スクールなどのWeb予約一覧を取り込み、
内容を確認・修正してからGoogleカレンダーへまとめて登録できます。
Google Calendar APIを設定していなくても、予定の確認・CSV出力・ICS出力までは利用できます。

### 基本の流れ
1. **Excel取込** または **Web取込** で予定を読み込む
2. **予定確認・編集** 画面で内容を確認し、必要に応じて修正する
3. 必要ならCSV/ICSをダウンロードする(Google未設定でもここまで可能)
4. **Googleカレンダー連携** 画面で接続し、ドライラン→登録を行う

---

#### 1. Excel取込画面の使い方
- xlsxファイルをアップロードします(想定シート名: 「ライブ講義スケジュール」)。
- Excelには西暦が書かれていないため、「対象年」を指定してください(初期値2026年)。
- 「AI実装コース」「AI分析コース」のどちらを取り込むか選べます。第1回と最終成果発表会は両コース共通です。
- 各回に複数の候補日時がある場合、次の3つから登録方式を選べます。
  - **各回から1件だけ選択**: ラジオボタンで1つずつ選びます(通常はこれを使います)。
  - **すべての候補を仮予定として登録**: 候補全部を「仮予定」状態で確認画面へ送ります。
  - **任意の候補を複数選択**: 回ごとにチェックボックスで好きな候補を選べます。
- 「予定確認画面へ追加」ボタンを押すと、選んだ予定が確認・編集画面に反映されます。
- 記載の曜日と実際の曜日が異なる場合は警告が表示されます(入力ミスの可能性があります)。

#### 2. Web取込画面の使い方
- **表テキスト貼り付け**: 予約一覧ページの表をコピーし、テキストエリアに貼り付けて「解析する」を押します。
  タブ区切り・スペース区切り・全角/半角どちらでも解析できます。
- **HTMLファイル取込**: ログイン後のページを「名前を付けて保存(HTML)」したファイルをアップロードします。
  複数の表(table)が見つかった場合は、プレビューを見ながら対象の表を選んでください。
- Webページにも西暦が無いことが多いため、「対象年」を指定してください。
- 「ネット」という場所表記は画面上「オンライン」に変換されますが、元の表記も保持されます。

#### 3. 予定確認・編集画面の使い方
- 取り込んだ予定を表形式で確認・修正できます。「登録対象」のチェックを外すと、その予定はGoogleカレンダーへ登録されません。
- 絞り込み(すべて/未登録/登録済み/Excel/Web/AI実装/AI分析/過去/今後)で表示を絞れます。
- 過去の予定が含まれる場合は警告が出ますが、自動的には削除・非表示にしません。
- 開始日時が終了日時より後(または同じ)の予定は登録できません。
- 同じsource_key(予定を一意に識別する値)が複数ある場合も警告されます。
- **一覧から削除したい予定**は、表の一番右の「削除」列にチェックを入れ、下に表示される確認チェックボックスに
  チェックしたうえで「一覧から削除する」を押してください。この削除は、あくまで**アプリの一覧からの削除**です。
  既にGoogleカレンダーへ登録済みの予定は自動では消えません(下記「4.」の削除候補から個別に削除してください)。
- この画面からCSV・ICSファイルをダウンロードできます(Google未設定でも利用可能)。ICSファイルには
  「Googleカレンダー連携」画面で設定した通知タイミングが反映されます。

#### 4. Googleカレンダー連携画面の使い方
- Google Calendar APIの設定手順は、下の「Google連携の設定方法」を参照してください。
- 未設定の場合は画面にエラーが出るのではなく、設定手順が表示されます。
- 接続後、登録先カレンダー(primary/学習予定/英会話/講義予定、または任意の名前)を選べます。
- **通知(リマインダー)タイミング**は複数選択できます。初期値は「2時間前」「1日前」の2つです。
  「5分前」〜「1週間前」まで好きな組み合わせを選べるほか、すべて選択解除すれば「通知なし」で登録されます。
  ここで設定した内容は、iPhoneのGoogleカレンダーアプリやカレンダーに同期しているアプリへの通知タイミングにも
  反映されます(デバイス側で通知が許可されている必要があります)。
- **必ず「ドライラン実行」で新規/更新/変更なし/エラーの件数を確認してから**、本登録してください。
- 内容が以前と変わっている予定は「更新する」(既定)/「新規登録する」/「変更しない」から選べます。
- 本登録前には確認チェックボックスへのチェックが必要です(誤操作防止)。
- 失敗した予定だけを選んで再実行できます。
- Web一覧から消えた予定や、「予定確認・編集」画面で一覧から削除した予定は自動削除されません。
  「削除候補」として表示されるので、必要な場合だけチェック・確認のうえ手動で削除してください。

#### 5. 登録履歴・設定画面の使い方
- これまでの同期履歴(SQLiteに保存)を確認できます。
- リマインダーの初期値などの設定を確認・変更できます。

---

### よくある質問

**Q. source_keyとは何ですか?**
予定を一意に識別するための文字列です。Webは「web|予約番号」、Excelは
「excel|コース名|第○回|開始日時」の形式です。これを使って同じ予定の二重登録を防いでいます。

**Q. ドライランとは何ですか?**
実際にはGoogleカレンダーへ登録せず、「新規登録される件数」「更新される件数」
「変更なしの件数」「エラー件数」だけを事前確認できる機能です。本登録前に必ず確認してください。

**Q. credentials.json・token.jsonはどこに置きますか? GitHubに上げても良いですか?**
プロジェクト直下に置いてください。**絶対にGitHubへアップロードしないでください**
(.gitignoreで除外済みです)。これらは個人のGoogleアカウントへのアクセス権を含みます。

**Q. Google Calendar APIを設定していませんが使えますか?**
使えます。Excel/Webの取込、予定の確認・編集、CSV/ICS出力まではAPI未設定でも利用できます。
Googleカレンダーへの実際の登録のみAPI設定が必要です。

---

### Google連携の設定方法(初めての方向け)
1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成する
2. 「APIとサービス」から **Google Calendar API** を有効化する
3. 「OAuth同意画面」を設定する(テストユーザーとしてご自身のGoogleアカウントを追加)
4. 「認証情報」から **OAuthクライアントID** を作成する(アプリケーションの種類: デスクトップアプリ)
5. 作成したクライアントの認証情報(JSON)をダウンロードし、ファイル名を `credentials.json` にする
6. `credentials.json` をこのプロジェクトのフォルダ直下(app.pyと同じ場所)に置く
7. アプリの「Googleカレンダー連携」画面で「Googleと接続」ボタンを押す
8. ブラウザが開くので、Googleアカウントを選択する
9. 権限(カレンダーへのアクセス)を許可する
10. 自動的に `token.json` が生成され、以後は再ログイン不要になる

`credentials.json`・`token.json` はどちらも `.gitignore` に含まれており、GitHubにはアップロードされません。
"""


# ============================================================
# 共通ヘルパー
# ============================================================

def filter_events(events: list[ScheduleEvent], choice: str) -> list[ScheduleEvent]:
    now = datetime.now()
    if choice == "すべて":
        return events
    if choice == "未登録":
        return [e for e in events if e.sync_status == SYNC_STATUS_NOT_SYNCED]
    if choice == "登録済み":
        return [e for e in events if e.sync_status != SYNC_STATUS_NOT_SYNCED]
    if choice == "Excel":
        return [e for e in events if e.source_type == SOURCE_TYPE_EXCEL]
    if choice == "Web":
        return [e for e in events if e.source_type == SOURCE_TYPE_WEB]
    if choice == "AI実装":
        return [e for e in events if e.course == COURSE_AI_IMPLEMENTATION]
    if choice == "AI分析":
        return [e for e in events if e.course == COURSE_AI_ANALYSIS]
    if choice == "過去":
        return [e for e in events if e.end_datetime and e.end_datetime < now]
    if choice == "今後":
        return [e for e in events if e.end_datetime and e.end_datetime >= now]
    return events


def events_to_dataframe(events: list[ScheduleEvent]) -> pd.DataFrame:
    rows = []
    for e in events:
        rows.append({
            "source_key": e.source_key,
            "登録対象": e.selected,
            "件名": e.title,
            "開始日時": e.start_datetime,
            "終了日時": e.end_datetime,
            "場所": e.location,
            "講師": e.instructor,
            "状態": e.status,
            "説明": e.description,
            "取込元": "Excel" if e.source_type == SOURCE_TYPE_EXCEL else "Web",
            "コース/回": f"{e.course} {e.session_name}".strip(),
            "登録状況": e.sync_status,
            "削除": False,
        })
    return pd.DataFrame(rows)


def apply_dataframe_edits(events: list[ScheduleEvent], edited: pd.DataFrame) -> None:
    for i, event in enumerate(events):
        row = edited.iloc[i]
        event.selected = bool(row["登録対象"])
        event.title = str(row["件名"])
        start = row["開始日時"]
        end = row["終了日時"]
        event.start_datetime = start.to_pydatetime() if isinstance(start, pd.Timestamp) else start
        event.end_datetime = end.to_pydatetime() if isinstance(end, pd.Timestamp) else end
        event.location = str(row["場所"])
        event.instructor = str(row["講師"])
        event.status = str(row["状態"])
        event.description = str(row["説明"])
        event.updated_at = datetime.now()


def candidate_label(event: ScheduleEvent) -> str:
    dt = event.start_datetime
    dt_str = dt.strftime("%Y/%m/%d(%a) %H:%M") if dt else "?"
    end_str = event.end_datetime.strftime("%H:%M") if event.end_datetime else "?"
    return f"{dt_str}〜{end_str}  講師:{event.instructor or '未定'}"


# ============================================================
# ホーム画面
# ============================================================

def render_home() -> None:
    st.title("ホーム")
    st.markdown("""
schedule-calendar-sync は、Excelの講義スケジュールやWeb予約一覧をGoogleカレンダーへ
まとめて登録するためのローカルWebアプリです。
""")

    st.subheader("処理手順")
    st.markdown("""
1. **Excel取込** または **Web取込** で予定を読み込む
2. **予定確認・編集** で内容を確認・修正する(必要ならCSV/ICSを出力する)
3. **Googleカレンダー連携** でドライラン→本登録する
""")

    gcal_configured = GoogleCalendarService.is_configured()
    gcal_connected = st.session_state.gcal_service.is_connected()

    col1, col2, col3 = st.columns(3)
    with col1:
        if gcal_configured and gcal_connected:
            st.success("Googleカレンダー: 接続済み")
        elif gcal_configured:
            st.warning("Googleカレンダー: 設定済み(未接続)")
        else:
            st.info("Googleカレンダー: 未設定")
    with col2:
        st.metric("取込済み件数", len(all_events()))
    with col3:
        unregistered = len([e for e in all_events() if e.sync_status == SYNC_STATUS_NOT_SYNCED])
        st.metric("未登録件数", unregistered)

    registered = len([e for e in all_events() if e.sync_status != SYNC_STATUS_NOT_SYNCED])
    st.metric("登録済み件数", registered)

    if not gcal_configured:
        st.info(
            "Google Calendar APIが未設定でも、Excel解析・Web解析・予定の確認編集・"
            "CSV出力・ICS出力は利用できます。Googleカレンダーへの実登録のみ設定が必要です。"
            "設定方法はサイドバーの「使い方ヘルプ」を参照してください。"
        )


# ============================================================
# Excel取込画面
# ============================================================

def render_excel_import() -> None:
    st.title("Excel取込")
    st.caption("ライブ講義スケジュール(xlsx)を取り込みます。")

    target_year = st.number_input("対象年(西暦)", min_value=2000, max_value=2100,
                                   value=DEFAULT_TARGET_YEAR, step=1, key="excel_target_year")

    uploaded = st.file_uploader("Excelファイル(.xlsx)を選択してください", type=["xlsx"])

    if uploaded is not None and st.button("解析する", type="primary"):
        try:
            result = parse_excel_schedule(io.BytesIO(uploaded.getvalue()), int(target_year),
                                           source_file=uploaded.name)
            st.session_state.excel_parse_result = result
            st.success(f"解析が完了しました(シート: {result.sheet_name} / 全候補 {len(result.events)}件)")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Excelの解析に失敗しました: {exc}")
            st.session_state.excel_parse_result = None

    result = st.session_state.excel_parse_result
    if result is None:
        st.info("Excelファイルをアップロードし、「解析する」を押してください。")
        return

    for w in result.warnings:
        st.warning(w)
    for err in result.errors:
        st.error(err)

    course = st.radio("取り込むコース", [COURSE_AI_IMPLEMENTATION, COURSE_AI_ANALYSIS], horizontal=True)
    course_events = result.by_course(course)
    st.caption(f"{course}: 共通講義を含めて {len(course_events)} 候補")

    mode = st.radio(
        "登録方式",
        ["各回から1件だけ選択", "すべての候補を仮予定として登録", "任意の候補を複数選択"],
    )

    grouped = group_by_round(course_events)
    to_commit: list[ScheduleEvent] = []

    if mode == "各回から1件だけ選択":
        for round_name, candidates in grouped.items():
            st.markdown(f"**{round_name}**")
            labels = [candidate_label(c) for c in candidates]
            idx = st.radio(f"{round_name}の日時を選択", options=range(len(candidates)),
                            format_func=lambda i, labels=labels: labels[i],
                            key=f"excel_radio_{course}_{round_name}", label_visibility="collapsed")
            chosen = candidates[idx]
            chosen.status = STATUS_CONFIRMED
            chosen.selected = True
            to_commit.append(chosen)
    elif mode == "すべての候補を仮予定として登録":
        for round_name, candidates in grouped.items():
            st.markdown(f"**{round_name}** ({len(candidates)}候補すべてを仮予定として登録)")
            for c in candidates:
                st.caption("・" + candidate_label(c))
                c.status = STATUS_TENTATIVE
                c.selected = True
                to_commit.append(c)
    else:  # 任意の候補を複数選択
        for round_name, candidates in grouped.items():
            st.markdown(f"**{round_name}**")
            labels = [candidate_label(c) for c in candidates]
            chosen_idx = st.multiselect(f"{round_name}の候補", options=range(len(candidates)),
                                         format_func=lambda i, labels=labels: labels[i],
                                         key=f"excel_multi_{course}_{round_name}")
            for i in chosen_idx:
                candidates[i].status = STATUS_TENTATIVE
                candidates[i].selected = True
                to_commit.append(candidates[i])

    st.divider()
    st.write(f"登録候補として選択中: {len(to_commit)}件")
    if st.button("予定確認画面へ追加", type="primary", disabled=(len(to_commit) == 0)):
        added = add_events(to_commit)
        st.success(f"{added}件を新規追加、{len(to_commit) - added}件を更新しました。"
                    "「予定確認・編集」画面で確認してください。")


# ============================================================
# Web取込画面
# ============================================================

def render_web_import() -> None:
    st.title("Web取込")
    st.caption("英会話スクールなどの予約一覧を取り込みます。ログイン自動化は行いません。")

    target_year = st.number_input("対象年(西暦)", min_value=2000, max_value=2100,
                                   value=DEFAULT_TARGET_YEAR, step=1, key="web_target_year")

    tab1, tab2 = st.tabs(["表テキスト貼り付け", "HTMLファイル取込"])

    with tab1:
        st.markdown("予約一覧ページの表をコピーし、下に貼り付けてください。")
        text = st.text_area("貼り付けたテキスト", height=200, key="web_text_input")
        if st.button("解析する", key="web_text_parse_btn", type="primary"):
            result = parse_web_schedule_text(text, int(target_year))
            st.session_state.web_text_parse_result = result

        result = st.session_state.web_text_parse_result
        if result is not None:
            st.success(f"{len(result.events)}件解析できました。")
            for w in result.warnings:
                st.warning(w)
            for err in result.errors:
                st.error(err)
            if result.events:
                st.dataframe(events_to_dataframe(result.events), use_container_width=True)
                if st.button("予定確認画面へ追加", key="web_text_add_btn", type="primary"):
                    added = add_events(result.events)
                    st.success(f"{added}件を新規追加しました。")

    with tab2:
        st.markdown("ログイン後ページを保存したHTMLファイルをアップロードしてください。")
        html_file = st.file_uploader("HTMLファイル", type=["html", "htm"], key="html_uploader")
        if html_file is not None and st.button("表を抽出する", key="html_extract_btn"):
            html_text = html_file.getvalue().decode("utf-8", errors="ignore")
            tables = extract_tables(html_text)
            st.session_state.html_tables = tables
            if not tables:
                st.error("table要素が見つかりませんでした。")
            else:
                st.success(f"{len(tables)}個の表が見つかりました。対象の表を選んでください。")

        tables = st.session_state.html_tables
        if tables:
            options = [f"表{t.index + 1} ({len(t.rows)}行)" for t in tables]
            selected_idx = st.selectbox("対象の表", options=range(len(tables)),
                                         format_func=lambda i: options[i])
            chosen_table = tables[selected_idx]
            st.write("プレビュー(先頭5行):")
            st.table(chosen_table.preview_rows())

            if st.button("この表を解析する", key="html_parse_btn", type="primary"):
                result = parse_table_rows(chosen_table.rows, int(target_year), source_file=html_file.name)
                st.session_state.web_html_parse_result = result

            result = st.session_state.web_html_parse_result
            if result is not None and result.events:
                st.success(f"{len(result.events)}件解析できました。")
                for w in result.warnings:
                    st.warning(w)
                for err in result.errors:
                    st.error(err)
                st.dataframe(events_to_dataframe(result.events), use_container_width=True)
                if st.button("予定確認画面へ追加", key="html_add_btn", type="primary"):
                    added = add_events(result.events)
                    st.success(f"{added}件を新規追加しました。")


# ============================================================
# 予定確認・編集画面
# ============================================================

def render_confirm_edit() -> None:
    st.title("予定確認・編集")

    events = all_events()
    if not events:
        st.info("まだ予定が取り込まれていません。「Excel取込」または「Web取込」で予定を追加してください。")
        return

    filter_choice = st.selectbox(
        "絞り込み",
        ["すべて", "未登録", "登録済み", "Excel", "Web", "AI実装", "AI分析", "過去", "今後"],
    )
    filtered = filter_events(events, filter_choice)

    dup_keys = find_duplicate_source_keys(filtered)
    if dup_keys:
        st.warning(f"同じsource_keyの予定が複数あります: {', '.join(dup_keys)}")

    past_count = len([e for e in filtered if e.end_datetime and e.end_datetime < datetime.now()])
    if past_count:
        st.warning(f"過去の予定が{past_count}件含まれています(自動削除・非表示は行いません)。")

    invalid = [e for e in filtered if not e.is_valid_time_range()]
    if invalid:
        st.error(f"開始日時が終了日時以降になっている予定が{len(invalid)}件あります。登録できません。")

    df = events_to_dataframe(filtered)
    display_df = df.drop(columns=["source_key"])

    edited = st.data_editor(
        display_df,
        use_container_width=True,
        num_rows="fixed",
        disabled=["取込元", "コース/回", "登録状況"],
        column_config={
            "開始日時": st.column_config.DatetimeColumn("開始日時", format="YYYY-MM-DD HH:mm"),
            "終了日時": st.column_config.DatetimeColumn("終了日時", format="YYYY-MM-DD HH:mm"),
            "状態": st.column_config.SelectboxColumn(
                "状態", options=[STATUS_CANDIDATE, STATUS_CONFIRMED, STATUS_TENTATIVE, "キャンセル"]
            ),
            "削除": st.column_config.CheckboxColumn(
                "削除", help="チェックして「一覧から削除する」を押すと、この一覧から削除できます。"
            ),
        },
        key="confirm_edit_table",
    )

    if st.button("編集内容を反映", type="primary"):
        apply_dataframe_edits(filtered, edited)
        st.success("編集内容を反映しました。")
        st.rerun()

    st.divider()
    st.subheader("一覧からの削除")
    to_delete_keys = [filtered[i].source_key for i in range(len(filtered)) if bool(edited.iloc[i]["削除"])]
    if to_delete_keys:
        already_synced = [k for k in to_delete_keys
                           if st.session_state.events[k].sync_status != SYNC_STATUS_NOT_SYNCED]
        st.warning(f"{len(to_delete_keys)}件が削除対象として選択されています。")
        if already_synced:
            st.info(
                f"うち{len(already_synced)}件はGoogleカレンダーへ登録済みです。一覧から削除しても、"
                "Googleカレンダー側の予定は自動削除されません。「Googleカレンダー連携」画面の"
                "「削除候補」から個別に確認・削除してください。"
            )
        confirm_delete = st.checkbox("この操作は元に戻せません。一覧から削除することを確認しました。",
                                      key="list_delete_confirm")
        if st.button("一覧から削除する", type="primary", disabled=not confirm_delete):
            removed = remove_events(to_delete_keys)
            st.success(f"{removed}件を一覧から削除しました。")
            st.rerun()
    else:
        st.caption("削除したい予定の「削除」列にチェックを入れると、ここに削除ボタンが表示されます。")

    st.divider()
    st.subheader("CSV・ICS出力")
    st.caption("Google Calendar API未設定でも利用できます。")
    reminder_minutes = reminder_minutes_from_labels(st.session_state.reminder_labels)
    reminder_display = "、".join(st.session_state.reminder_labels) if reminder_minutes else "通知なし"
    st.caption(f"ICSファイルの通知設定: {reminder_display}(「Googleカレンダー連携」画面で変更できます)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("正規化済みCSVをダウンロード", data=to_normalized_csv(filtered).encode("utf-8-sig"),
                            file_name="schedule_normalized.csv", mime="text/csv")
    with col2:
        st.download_button("Googleカレンダー取込用CSVをダウンロード",
                            data=to_google_calendar_csv(filtered).encode("utf-8-sig"),
                            file_name="schedule_google_import.csv", mime="text/csv")
    with col3:
        st.download_button("ICSファイルをダウンロード", data=build_ics(filtered, reminder_minutes),
                            file_name="schedule.ics", mime="text/calendar")


# ============================================================
# Googleカレンダー連携画面
# ============================================================

def render_google_calendar() -> None:
    st.title("Googleカレンダー連携")

    service: GoogleCalendarService = st.session_state.gcal_service

    if not GoogleCalendarService.is_configured():
        st.warning("credentials.json が見つかりません。Google Calendar APIが未設定です。")
        st.markdown("設定方法はサイドバーの「使い方ヘルプ」内『Google連携の設定方法』を参照してください。")
        return

    if not service.is_connected():
        st.info("credentials.json は見つかりましたが、まだ接続(初回ログイン)していません。")
        if st.button("Googleと接続", type="primary"):
            try:
                service.connect()
                st.success("接続しました。")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"接続に失敗しました: {exc}")
        return

    st.success("Googleカレンダーに接続済みです。")

    calendar_name = st.selectbox(
        "登録先カレンダー", DEFAULT_CALENDAR_CANDIDATES + ["(その他の名前を指定)"],
    )
    if calendar_name == "(その他の名前を指定)":
        calendar_name = st.text_input("カレンダー名", value="")

    st.markdown("#### 通知(リマインダー)設定")
    reminder_labels = st.multiselect(
        "通知タイミング(複数選択可・未選択の場合は通知なし)",
        options=list(REMINDER_PRESETS.keys()),
        default=st.session_state.reminder_labels,
        help="iPhone・Googleカレンダーアプリへの通知タイミングです。初期値は「2時間前」「1日前」です。"
             "何も選択しなければ通知なしで登録されます。",
    )
    st.session_state.reminder_labels = reminder_labels
    reminder_minutes = reminder_minutes_from_labels(reminder_labels)
    if reminder_minutes:
        st.caption(f"通知設定: {'、'.join(reminder_labels)}")
    else:
        st.caption("通知なしで登録されます。")

    conflict_mode = st.radio("内容が変更されている予定への対応", [CONFLICT_UPDATE, CONFLICT_INSERT_NEW, CONFLICT_SKIP])
    st.session_state.conflict_mode = conflict_mode

    events = [e for e in all_events() if e.selected]
    st.write(f"登録対象として選択されている予定: {len(events)}件")

    conn = get_conn()

    if st.button("ドライラン実行"):
        result = dry_run(conn, events, conflict_mode)
        st.session_state.last_dry_run = result

    dry = st.session_state.get("last_dry_run")
    if dry is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("新規登録", dry.new_count)
        c2.metric("更新", dry.update_count)
        c3.metric("変更なし", dry.unchanged_count)
        c4.metric("エラー", dry.error_count)
        with st.expander("詳細"):
            for p in dry.plans:
                st.write(f"- [{p.action}] {p.event.title} ({p.reason})")

    st.divider()
    confirmed = st.checkbox("内容を確認しました。Googleカレンダーへ登録します。", key="register_confirm_checkbox")
    if st.button("Googleカレンダーへ登録実行", type="primary", disabled=not confirmed):
        if not calendar_name:
            st.error("カレンダー名を指定してください。")
        else:
            try:
                calendar_id = service.ensure_calendar(calendar_name)
                st.session_state.calendar_id = calendar_id
                progress = st.progress(0.0, text="登録中...")
                outcomes = []
                for i, e in enumerate(events):
                    outcomes.extend(sync_events(conn, service, calendar_id, [e], conflict_mode, reminder_minutes))
                    progress.progress((i + 1) / max(len(events), 1), text=f"登録中... ({i + 1}/{len(events)})")
                    e.sync_status = SYNC_STATUS_SYNCED if outcomes[-1].result.startswith("成功") else e.sync_status
                    if outcomes[-1].google_event_id:
                        e.google_event_id = outcomes[-1].google_event_id
                st.session_state.last_sync_outcomes = outcomes
                progress.empty()
                st.success("登録処理が完了しました。")
            except Exception as exc:  # noqa: BLE001
                st.error(f"登録処理でエラーが発生しました: {exc}")

    outcomes = st.session_state.last_sync_outcomes
    if outcomes:
        st.subheader("登録結果")
        success = [o for o in outcomes if o.result.startswith("成功")]
        skipped = [o for o in outcomes if o.result == "スキップ"]
        failed = [o for o in outcomes if o.result == "失敗"]
        c1, c2, c3 = st.columns(3)
        c1.metric("成功・更新", len(success))
        c2.metric("スキップ", len(skipped))
        c3.metric("失敗", len(failed))
        if failed:
            st.error("失敗した予定:")
            for o in failed:
                st.write(f"- {o.event.title}: {o.error_message}")
            if st.button("失敗した予定だけ再実行"):
                retry_events = [o.event for o in failed]
                retry_outcomes = sync_events(conn, service, st.session_state.calendar_id, retry_events,
                                              conflict_mode, reminder_minutes)
                st.session_state.last_sync_outcomes = success + skipped + retry_outcomes
                st.rerun()

    st.divider()
    st.subheader("削除候補")
    st.caption("Web一覧から消えた予定は自動削除しません。必要な場合のみ選択して削除してください。")
    delete_candidates = find_delete_candidates(conn, all_events())
    if not delete_candidates:
        st.write("削除候補はありません。")
    else:
        selected_keys = []
        for rec in delete_candidates:
            checked = st.checkbox(f"{rec.title or rec.source_key} ({rec.source_key})", key=f"del_{rec.source_key}")
            if checked:
                selected_keys.append(rec.source_key)
        delete_confirmed = st.checkbox("選択した予定をGoogleカレンダーから削除することを確認しました。",
                                        key="delete_confirm_checkbox")
        if st.button("削除実行", disabled=not (selected_keys and delete_confirmed)):
            from src.services.sync_service import delete_events
            results = delete_events(conn, service, selected_keys)
            for source_key, ok, msg in results:
                if ok:
                    st.success(f"削除しました: {source_key}")
                else:
                    st.error(f"削除に失敗しました: {source_key} ({msg})")


# ============================================================
# 登録履歴・設定画面
# ============================================================

def render_history_settings() -> None:
    st.title("登録履歴・設定")

    conn = get_conn()
    records = get_all_records(conn)

    st.subheader("同期履歴")
    if not records:
        st.write("同期履歴はまだありません。")
    else:
        rows = [{
            "source_key": r.source_key,
            "件名": r.title,
            "開始日時": r.start_datetime,
            "終了日時": r.end_datetime,
            "google_event_id": r.google_event_id,
            "calendar_id": r.calendar_id,
            "最終同期日時": r.last_synced_at,
            "状態": r.sync_status,
        } for r in records]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.subheader("設定")
    st.write("タイムゾーン: Asia/Tokyo(固定)")
    reminder_display = "、".join(st.session_state.reminder_labels) if st.session_state.reminder_labels else "通知なし"
    st.write(f"既定の通知タイミング: {reminder_display}")
    st.write("データベース: data/schedule_sync.db (このフォルダはGitHubへアップロードされません)")


# ============================================================
# エントリポイント
# ============================================================

def main() -> None:
    st.set_page_config(page_title="schedule-calendar-sync", layout="wide")
    init_session_state()

    st.sidebar.title("schedule-calendar-sync")
    if st.sidebar.button("❓ 使い方ヘルプ", use_container_width=True):
        show_help_dialog()

    page = st.sidebar.radio("メニュー", PAGES)

    if page == "ホーム":
        render_home()
    elif page == "Excel取込":
        render_excel_import()
    elif page == "Web取込":
        render_web_import()
    elif page == "予定確認・編集":
        render_confirm_edit()
    elif page == "Googleカレンダー連携":
        render_google_calendar()
    elif page == "登録履歴・設定":
        render_history_settings()


if __name__ == "__main__":
    main()
