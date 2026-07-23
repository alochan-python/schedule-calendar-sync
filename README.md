# schedule-calendar-sync

Excelの講義スケジュールや、Webページ(英会話スクールの予約一覧など)に表示される
表形式スケジュールを取り込み、内容を確認・編集したうえでGoogleカレンダーへ登録する、
Mac上で動かすローカルWebアプリ(Streamlit製)です。

- Google Calendar APIを設定していなくても、予定の確認・CSV出力・ICS出力までは使えます。
- GitHubにはソースコードのみを保存し、認証情報や実データはアップロードしません。
- GitHub Pagesへの公開は行いません(ローカル実行専用です)。

アプリ内の右上(サイドバー)にある **「❓ 使い方ヘルプ」** ボタンから、画面ごとの詳しい使い方を
いつでも確認できます。このREADMEはセットアップ(初回準備)を重視した内容になっています。

---

## 1. 必要なもの

- macOS
- Python 3.12(推奨。3.11でも動作します。3.10以前は非対応です)
- (任意)Googleアカウント ※Googleカレンダーへ実際に登録したい場合のみ必要
- (任意)GitHub CLI(`gh`) ※GitHubへpushしたい場合のみ必要

Pythonのバージョンは以下で確認できます。

```bash
python3 --version
```

`python3.12` が入っていない場合は [python.org](https://www.python.org/downloads/) や
`brew install python@3.12` などでインストールしてください。3.12が無い場合でも、
`python3`(3.11以上)があればひとまず動作します。

---

## 2. セットアップ手順(初めての方向け)

ターミナルを開き、このプロジェクトのフォルダへ移動してから、次を順番に実行してください。

```bash
# 1. 仮想環境を作成する
python3 -m venv .venv

# 2. 仮想環境を有効化する(プロンプトの先頭に (.venv) と表示されればOK)
source .venv/bin/activate

# 3. 必要なライブラリをインストールする
pip install -r requirements.txt

# 4. アプリを起動する
streamlit run app.py
```

起動すると自動的にブラウザが開き、`http://localhost:8501` でアプリが表示されます。
開かない場合は、ターミナルに表示されたURLを手動でブラウザに貼り付けてください。

`Makefile` を使う場合は、次のコマンドでも同じことができます。

```bash
make setup   # 仮想環境の作成 + ライブラリインストール
make run     # アプリの起動
make test    # テストの実行
make lint    # コードチェック(ruff)
```

### 2回目以降の起動

```bash
cd schedule-calendar-sync
source .venv/bin/activate
streamlit run app.py
```

---

## 3. まずは触ってみる(サンプルデータ)

`samples/` フォルダに、匿名化されたサンプルデータが入っています。実データはアプリ起動直後には
含まれていないため、まずはこのサンプルで動作を確認することをおすすめします。

- `samples/sample_schedule.xlsx` … Excel講義スケジュールのサンプル(9回分、AI実装/AI分析コース)
- `samples/sample_web_schedule.txt` … Web予約一覧(表テキスト貼り付け用)のサンプル、25件

アプリの「Excel取込」画面で `sample_schedule.xlsx` をアップロード、
「Web取込」画面のテキストエリアに `sample_web_schedule.txt` の中身を貼り付けて、
「解析する」を押してみてください。

---

## 4. 画面構成

| 画面 | できること |
|---|---|
| ホーム | アプリの概要、Google接続状況、件数サマリーの確認 |
| Excel取込 | 講義スケジュール(xlsx)の取込、コース選択、候補の登録方式選択 |
| Web取込 | 表テキスト貼り付け / HTMLファイルからの予約一覧取込 |
| 予定確認・編集 | 取り込んだ予定の確認・修正、絞り込み、CSV/ICS出力 |
| Googleカレンダー連携 | Google接続、ドライラン、本登録、削除候補の確認 |
| 登録履歴・設定 | 同期履歴(SQLite)の確認、リマインダーなどの設定確認 |

---

## 5. Excel取込フォーマットについて

想定しているExcelは、シート名「ライブ講義スケジュール」、`A1:E28` 付近に次のような構造で
書かれているものです。

- A列: 「第○回」(空欄の行は直前の回を引き継ぎます)
- B列: AI実装コースの日時(例: `7/27(月)20:00-21:30`)
- C列: AI実装コースの担当者
- D列: AI分析コースの日時
- E列: AI分析コースの担当者
- 第1回・最終成果発表会は両コース共通として扱われます

Excelには西暦が書かれていない前提のため、取込画面で「対象年」を指定してください(初期値: 2026年)。
記載されている曜日と、実際にその日付から計算した曜日が異なる場合は警告が表示されます。

シート構造が想定と異なる場合は、`src/parsers/excel_schedule_parser.py` を実際のファイルに
合わせて調整してください(データ駆動で読み取っているため、行数が多少ずれても動作しますが、
列の意味(A〜E)が異なる場合はコードの修正が必要です)。

---

## 6. Web取込について

### 6-1. 表テキスト貼り付け

予約一覧ページの表をブラウザ上でコピーし、「Web取込」画面のテキストエリアに貼り付けます。
タブ区切り・スペース区切り(全角/半角)・改行に対応しています。

### 6-2. HTMLファイル取込

ログイン後のページをブラウザの「名前を付けて保存」で `.html` 形式で保存し、
そのファイルをアップロードします。ページ内の `table` 要素を自動的に探し、
複数の表が見つかった場合はプレビューを見ながら対象の表を選べます。

※サイトのHTML構造は実際のページごとに異なります。想定通りに解析できない場合は、
`src/parsers/html_table_parser.py` の列の割り当てを調整してください。

---

## 7. CSV・ICS出力(Google Calendar API不要)

「予定確認・編集」画面から、以下をダウンロードできます。Google Calendar APIを
設定していなくても利用できます。

- 正規化済みCSV(全項目を含む)
- Googleカレンダー取込用CSV(Subject/Start Date/…形式)
- ICSファイル(他のカレンダーアプリへの取込用)

---

## 8. Google Calendar APIの設定方法(初心者向け)

**この設定をしなくてもアプリは起動し、Excel/Web取込・確認編集・CSV/ICS出力は使えます。**
Googleカレンダーへ実際に登録したい場合のみ、以下を行ってください。

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセスし、新しいプロジェクトを作成する
2. 左メニューの「APIとサービス」→「ライブラリ」から **Google Calendar API** を検索して有効化する
3. 「APIとサービス」→「OAuth同意画面」で、User Type は「外部」を選び、アプリ名などを入力する。
   「テストユーザー」に自分のGoogleアカウントのメールアドレスを追加する
4. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuthクライアントID」を選ぶ
5. アプリケーションの種類で **「デスクトップアプリ」** を選び、名前を付けて作成する
6. 作成されたクライアントの「JSONをダウンロード」を押す
7. ダウンロードしたファイルの名前を `credentials.json` に変更し、このプロジェクトのフォルダ直下
   (`app.py` と同じ場所)に置く
8. アプリを起動し、「Googleカレンダー連携」画面で **「Googleと接続」** ボタンを押す
9. ブラウザが自動的に開くので、Googleアカウントを選択し、カレンダーへのアクセス権限を許可する
10. 許可すると `token.json` が自動的に生成され、以後は再度ログインする必要はありません

**重要: `credentials.json` と `token.json` は、絶対にGitHubへアップロードしないでください。**
`.gitignore` によって既に除外されていますが、誤って `git add -f` などをしないよう注意してください。

---

## 9. データの保存場所・セキュリティ

| 種類 | 保存場所 | GitHubに上げるか |
|---|---|---|
| Google認証情報 | `credentials.json` / `token.json`(プロジェクト直下) | 上げない |
| 同期履歴DB | `data/schedule_sync.db` | 上げない |
| Web自動ログイン状態(将来機能) | `playwright/.auth/` など | 上げない |
| サイト固有設定(将来機能) | `config/web_sources.local.yaml` | 上げない |
| 実際のExcel/HTML/CSV/ICSファイル | 各自の作業フォルダ | 上げない |
| 匿名化サンプルデータ | `samples/` | 上げてよい |

`.gitignore` にこれらの除外設定が入っています。`git status` や `git ls-files` で
実データや認証情報が追跡対象になっていないか、pushする前に必ず確認してください。

---

## 10. テスト・コードチェック

```bash
source .venv/bin/activate
pytest -q          # またはmake test
ruff check .        # またはmake lint
```

テストは以下を含みます(`tests/` 配下)。

- Excel/Web日時文字列の解析(全角チルダ・タブ・複数スペース・西暦付与・曜日不一致検出)
- Excelサンプルの候補件数の検証(全体約40件、AI実装22件、AI分析20件、各コース9回)
- Webサンプル25件の解析
- 同じsource_keyを2回同期しても重複登録されないこと(SQLite・モック使用)
- CSV/ICS出力、Asia/Tokyoタイムゾーンでの登録内容
- Google認証情報が無くてもアプリ(app.py)がインポート(起動)できること

Google Calendar APIへの実通信テストは行わず、モック(`FakeCalendarService`)を使用しています。

---

## 11. プロジェクト構成

```
schedule-calendar-sync/
├── app.py                        # Streamlitアプリ本体(全画面・ヘルプ)
├── src/
│   ├── models.py                 # 共通データモデル(ScheduleEvent)
│   ├── database.py               # SQLite同期履歴管理
│   ├── config.py                 # 設定・パス管理
│   ├── parsers/
│   │   ├── datetime_utils.py     # 日時文字列解析の共通処理
│   │   ├── excel_schedule_parser.py
│   │   ├── web_text_parser.py
│   │   └── html_table_parser.py
│   ├── services/
│   │   ├── google_calendar_service.py
│   │   ├── sync_service.py       # 重複防止・ドライラン・削除候補
│   │   ├── csv_export_service.py
│   │   └── ics_export_service.py
│   └── web_sources/              # Web自動取得(将来機能)の拡張ポイント
│       ├── base.py
│       └── english_school.py
├── tests/
├── samples/                      # 匿名化サンプルデータ
├── scripts/generate_sample_excel.py  # サンプルExcel生成スクリプト(開発用)
├── .streamlit/config.toml
├── .env.example
├── requirements.txt
├── Makefile
└── README.md
```

---

## 12. Web自動取得機能を追加するには(将来拡張)

MVPでは、ログインの自動化(Playwrightなどによる自動ログイン・自動取得)は行っていません。
代わりに、後から追加しやすいように次の拡張ポイントを用意しています。

- `src/web_sources/base.py` … `WebSource` 抽象クラス、`WebSourceConfig` 設定クラス
- `src/web_sources/english_school.py` … 実装イメージ(コメントのみ、未実装)
- `config/web_sources.example.yaml` … サイト設定のサンプル
  (実際に使う場合は `config/web_sources.local.yaml` としてコピーする。Git管理外)

自動取得を追加するために、あらかじめ次の情報が必要です。

1. ログインページのURL
2. 予約一覧ページのURL
3. 予約一覧の表(table)を特定するCSSセレクタ、またはHTML構造
4. ログイン方式(ID/パスワード、多要素認証の有無など)

実装時は、`Playwright` を使い、**パスワードをコードに書かず、初回のみユーザーが手動でログインし、
その状態を `playwright/.auth/` 等へ保存する方式**を推奨します(`src/web_sources/english_school.py`
内のコメントに実装イメージを記載しています)。Playwrightは本MVPの必須依存には含めていません。
追加する場合は `pip install playwright && playwright install chromium` を別途実行してください。

---

## 13. よくあるトラブル

**Q. `streamlit run app.py` を実行しても何も起きない/エラーになる**
→ 仮想環境を有効化(`source .venv/bin/activate`)してから実行しているか確認してください。

**Q. Excelを取り込んだら候補が0件だった**
→ シート名が「ライブ講義スケジュール」以外の場合、先頭シートを使う旨の警告が出ます。
　列の並び(A〜E)が想定と異なる場合は、`src/parsers/excel_schedule_parser.py` の調整が必要です。

**Q. Web取込でうまく列が分かれない**
→ 区切りがタブ・全角/半角スペース・改行以外(カンマ等)の場合、区切り文字を
　`src/parsers/web_text_parser.py` の `_COLUMN_SPLIT_PATTERN` に追加してください。

**Q. Googleカレンダー連携でエラーが出る**
→ まず「Googleカレンダー連携」画面の案内、および `credentials.json` の配置場所を確認してください。
　それでも解決しない場合は、`token.json` を削除して再度「Googleと接続」をやり直してください。

---

## 14. ライセンス

`LICENSE` ファイルを参照してください。
