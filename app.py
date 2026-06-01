import streamlit as st
import pandas as pd
from pathlib import Path
import asyncio
import hashlib
from datetime import date, datetime, timedelta
import base64
import html
import json

import gspread
from google.oauth2.service_account import Credentials


# ============================================================
# 國中英文單字智慧複習系統
# app_v9.py
#
# 本版重點：
# 1. words.csv 仍然是單字資料來源
# 2. Google Sheets 改成學習紀錄資料庫
# 3. 支援三個使用者：女兒 / 兒子 / 測試帳
# 4. 每個使用者有自己的學習進度
# 5. 不再依賴 progress.db
# ============================================================


# ============================================================
# 1. 基本檔案路徑設定
# ============================================================

DATA_PATH = Path("words.csv")

AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

VOICE = "en-US-JennyNeural"


# ============================================================
# 2. Google Sheets 設定
# ============================================================
#
# 這一版需要在 Streamlit Secrets 設定：
#
# [gcp_service_account]
# type = "service_account"
# project_id = "你的 project_id"
# private_key_id = "你的 private_key_id"
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "你的 service account email"
# client_id = "你的 client_id"
# auth_uri = "https://accounts.google.com/o/oauth2/auth"
# token_uri = "https://oauth2.googleapis.com/token"
# auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
# client_x509_cert_url = "..."
#
# google_sheet_id = "你的 Google Sheet ID"
#
# Google Sheet 裡會用到兩個工作表：
# 1. users
# 2. progress
# ============================================================

USER_HEADERS = ["user_id", "user_name", "role"]

PROGRESS_HEADERS = [
    "user_id",
    "word_id",
    "word",
    "grade",
    "semester",
    "lesson",
    "status",
    "mastery",
    "review_count",
    "correct_count",
    "wrong_count",
    "streak_correct",
    "last_review",
    "next_review",
    "updated_at",
]


DEFAULT_USERS = [
    ["daughter", "女兒", "learner"],
    ["son", "兒子", "learner"],
    ["test", "測試帳", "test"],
]


# ============================================================
# 3. Streamlit 頁面設定
# ============================================================

st.set_page_config(
    page_title="國中英文單字複習",
    page_icon="📘",
    layout="wide"
)


# ============================================================
# 4. 自訂 CSS
# ============================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.0rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .small-caption {
        color: #888;
        font-size: 0.95rem;
        margin-bottom: 1.0rem;
    }
    .word-card {
        border: 1px solid rgba(180,180,180,0.35);
        border-radius: 18px;
        padding: 22px;
        margin-bottom: 14px;
        background-color: rgba(255,255,255,0.04);
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    }
    .word-text {
        text-align: center;
        font-size: 3.0rem;
        font-weight: 900;
        line-height: 1.1;
        margin-bottom: 0.6rem;
    }
    .meaning-text {
        text-align: center;
        font-size: 1.45rem;
        font-weight: 700;
        color: #BBBBBB;
    }
    .section-title {
        font-size: 1.18rem;
        font-weight: 800;
        margin-top: 0.8rem;
        margin-bottom: 0.4rem;
    }
    .example-card {
        border: 1px solid rgba(160,160,160,0.25);
        border-radius: 14px;
        padding: 12px 14px;
        margin-bottom: 10px;
        background-color: rgba(255,255,255,0.035);
    }
    .example-en {
        font-size: 1.02rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .example-zh {
        font-size: 0.95rem;
        color: #AAAAAA;
    }
    .mini-note {
        color: #999;
        font-size: 0.92rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.45rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 5. 小工具函式
# ============================================================

def safe_str(value) -> str:
    """把資料安全轉成字串。"""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def safe_int(value, default=0) -> int:
    """把資料安全轉成整數。"""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def make_word_id(row: pd.Series) -> str:
    """
    建立單字唯一 ID。
    用年級、學期、課次、單字組合，避免不同課出現同一單字時混在一起。
    """
    parts = [
        safe_str(row.get("grade", "")),
        safe_str(row.get("semester", "")),
        safe_str(row.get("lesson", "")),
        safe_str(row.get("word", "")),
    ]
    raw_id = "|".join(parts)
    return hashlib.md5(raw_id.encode("utf-8")).hexdigest()


def text_to_audio_filename(text: str) -> Path:
    """同一句文字對應同一個 mp3 檔名。"""
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    return AUDIO_DIR / f"{text_hash}.mp3"


async def _create_audio_async(text: str, output_path: Path):
    """用 edge-tts 產生 mp3。"""
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=VOICE)
    await communicate.save(str(output_path))


def get_audio_file(text: str) -> Path | None:
    """取得發音檔，沒有就自動產生。"""
    text = safe_str(text)
    if not text:
        return None

    output_path = text_to_audio_filename(text)

    if output_path.exists():
        return output_path

    try:
        asyncio.run(_create_audio_async(text, output_path))
        return output_path
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_create_audio_async(text, output_path))
        loop.close()
        return output_path
    except Exception as e:
        st.warning(f"產生發音失敗：{e}")
        return None


def autoplay_audio(audio_path: Path):
    """自動播放音檔。"""
    if audio_path is None or not audio_path.exists():
        return

    audio_bytes = audio_path.read_bytes()
    audio_base64 = base64.b64encode(audio_bytes).decode()

    audio_html = f"""
    <audio autoplay>
        <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
    </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)


def audio_button(text: str, label: str, key: str):
    """手動播放按鈕。"""
    if st.button(label, key=key):
        audio_path = get_audio_file(text)
        autoplay_audio(audio_path)


def show_info_table(rows: list[tuple[str, str]]):
    """用表格顯示資料。"""
    clean_rows = [(k, v) for k, v in rows if safe_str(v)]
    if not clean_rows:
        return

    df = pd.DataFrame(clean_rows, columns=["項目", "內容"])
    st.dataframe(df, hide_index=True, use_container_width=True)


def normalize_progress_record(record: dict, user_id: str, word_row: pd.Series) -> dict:
    """
    把 Google Sheets 讀回來的資料補齊欄位。
    如果某個單字還沒有紀錄，就建立預設紀錄。
    """
    base = {
        "user_id": user_id,
        "word_id": safe_str(word_row["word_id"]),
        "word": safe_str(word_row.get("word", "")),
        "grade": safe_str(word_row.get("grade", "")),
        "semester": safe_str(word_row.get("semester", "")),
        "lesson": safe_str(word_row.get("lesson", "")),
        "status": "未學",
        "mastery": "0",
        "review_count": "0",
        "correct_count": "0",
        "wrong_count": "0",
        "streak_correct": "0",
        "last_review": "",
        "next_review": "",
        "updated_at": "",
    }

    if record:
        for key in PROGRESS_HEADERS:
            if key in record:
                base[key] = safe_str(record.get(key, ""))

    return base


# ============================================================
# 6. 讀取 words.csv
# ============================================================

@st.cache_data
def load_words() -> pd.DataFrame:
    """讀取單字表 words.csv。"""
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請確認 words.csv 和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH)
    df = df.fillna("")

    required_columns = [
        "word", "meaning", "pos", "grade", "semester", "lesson"
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        st.error(f"words.csv 缺少必要欄位：{', '.join(missing_columns)}")
        return pd.DataFrame()

    if "pos_en" not in df.columns:
        df["pos_en"] = df["pos"]

    if "pos_zh" not in df.columns:
        df["pos_zh"] = df["pos"]

    df["word_id"] = df.apply(make_word_id, axis=1)

    return df


# ============================================================
# 7. Google Sheets 連線與初始化
# ============================================================

@st.cache_resource
def get_google_client():
    """
    建立 Google Sheets API 連線。
    使用 Streamlit Secrets 中的 gcp_service_account。
    """
    if "gcp_service_account" not in st.secrets:
        st.error("尚未設定 Streamlit Secrets：缺少 [gcp_service_account]。")
        st.stop()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    service_account_info = dict(st.secrets["gcp_service_account"])

    # private_key 在 toml 裡常需要處理換行
    if "private_key" in service_account_info:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes
    )

    return gspread.authorize(credentials)


@st.cache_resource
def get_spreadsheet():
    """開啟 Google Sheet。"""
    if "google_sheet_id" not in st.secrets:
        st.error("尚未設定 Streamlit Secrets：缺少 google_sheet_id。")
        st.stop()

    client = get_google_client()
    sheet_id = st.secrets["google_sheet_id"]

    try:
        return client.open_by_key(sheet_id)
    except Exception as e:
        st.error(f"無法開啟 Google Sheet。請確認 google_sheet_id 正確，且已分享給 Service Account。錯誤：{e}")
        st.stop()


def get_or_create_worksheet(spreadsheet, title: str, headers: list[str], default_rows: list[list[str]] | None = None):
    """
    取得工作表；如果不存在就建立。
    並確保第一列是指定欄位名稱。
    """
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(20, len(headers)))

    existing_values = ws.get_all_values()

    if not existing_values:
        ws.update("A1", [headers])
        if default_rows:
            ws.append_rows(default_rows, value_input_option="USER_ENTERED")
    else:
        first_row = existing_values[0]
        if first_row[:len(headers)] != headers:
            ws.update("A1", [headers])

    return ws


@st.cache_data(ttl=20)
def load_users_from_sheet() -> pd.DataFrame:
    """讀取 users 工作表。ttl=20 表示最多快取 20 秒。"""
    spreadsheet = get_spreadsheet()
    ws = get_or_create_worksheet(spreadsheet, "users", USER_HEADERS, DEFAULT_USERS)

    records = ws.get_all_records()
    if not records:
        ws.append_rows(DEFAULT_USERS, value_input_option="USER_ENTERED")
        records = ws.get_all_records()

    return pd.DataFrame(records)


@st.cache_data(ttl=20)
def load_progress_from_sheet() -> pd.DataFrame:
    """讀取 progress 工作表。"""
    spreadsheet = get_spreadsheet()
    ws = get_or_create_worksheet(spreadsheet, "progress", PROGRESS_HEADERS, None)

    records = ws.get_all_records()

    if not records:
        return pd.DataFrame(columns=PROGRESS_HEADERS)

    df = pd.DataFrame(records)

    for col in PROGRESS_HEADERS:
        if col not in df.columns:
            df[col] = ""

    return df[PROGRESS_HEADERS]


def clear_sheet_cache():
    """更新 Google Sheet 後，清除快取，讓畫面讀到新資料。"""
    load_progress_from_sheet.clear()
    load_users_from_sheet.clear()


def find_progress_row_number(ws, user_id: str, word_id: str) -> int | None:
    """
    在 progress 工作表中找出某個 user_id + word_id 的列號。
    Google Sheets 的列號從 1 開始，第 1 列是標題，所以資料從第 2 列開始。
    """
    all_values = ws.get_all_values()

    if len(all_values) <= 1:
        return None

    headers = all_values[0]
    try:
        user_col = headers.index("user_id")
        word_col = headers.index("word_id")
    except ValueError:
        return None

    for row_number, row in enumerate(all_values[1:], start=2):
        row_user = row[user_col] if user_col < len(row) else ""
        row_word = row[word_col] if word_col < len(row) else ""

        if row_user == user_id and row_word == word_id:
            return row_number

    return None


def upsert_progress_to_sheet(user_id: str, word_row: pd.Series, progress_record: dict):
    """
    新增或更新一筆學習紀錄到 Google Sheets。
    """
    spreadsheet = get_spreadsheet()
    ws = get_or_create_worksheet(spreadsheet, "progress", PROGRESS_HEADERS, None)

    word_id = safe_str(word_row["word_id"])
    row_number = find_progress_row_number(ws, user_id, word_id)

    row_data = [safe_str(progress_record.get(col, "")) for col in PROGRESS_HEADERS]

    if row_number is None:
        ws.append_row(row_data, value_input_option="USER_ENTERED")
    else:
        cell_range = f"A{row_number}:{chr(64 + len(PROGRESS_HEADERS))}{row_number}"
        ws.update(cell_range, [row_data], value_input_option="USER_ENTERED")

    clear_sheet_cache()


# ============================================================
# 8. 記憶曲線計算
# ============================================================

def calculate_review_result(level: str, current_progress: dict) -> dict:
    """
    根據熟悉度按鈕，計算新的學習紀錄。
    """
    today = date.today()

    mastery = safe_int(current_progress.get("mastery"), 0)
    review_count = safe_int(current_progress.get("review_count"), 0)
    correct_count = safe_int(current_progress.get("correct_count"), 0)
    wrong_count = safe_int(current_progress.get("wrong_count"), 0)
    streak_correct = safe_int(current_progress.get("streak_correct"), 0)

    review_count += 1

    if level == "forgot":
        mastery = max(0, mastery - 20)
        wrong_count += 1
        streak_correct = 0
        next_days = 1
        status = "學習中"

    elif level == "hard":
        mastery = min(100, mastery + 5)
        correct_count += 1
        streak_correct += 1
        next_days = 2
        status = "學習中"

    elif level == "good":
        mastery = min(100, mastery + 15)
        correct_count += 1
        streak_correct += 1
        next_days = 4
        status = "熟悉"

    elif level == "easy":
        mastery = min(100, mastery + 25)
        correct_count += 1
        streak_correct += 1

        if streak_correct >= 5:
            next_days = 30
            status = "已掌握"
        elif streak_correct >= 3:
            next_days = 14
            status = "熟悉"
        else:
            next_days = 7
            status = "熟悉"

    else:
        next_days = 1
        status = "學習中"

    next_review = today + timedelta(days=next_days)

    return {
        "status": status,
        "mastery": str(mastery),
        "review_count": str(review_count),
        "correct_count": str(correct_count),
        "wrong_count": str(wrong_count),
        "streak_correct": str(streak_correct),
        "last_review": today.isoformat(),
        "next_review": next_review.isoformat(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def update_progress(user_id: str, word_row: pd.Series, level: str, current_progress: dict):
    """
    更新某位使用者某個單字的學習紀錄。
    """
    base_record = normalize_progress_record(current_progress, user_id, word_row)
    result = calculate_review_result(level, base_record)

    updated_record = base_record.copy()
    updated_record.update(result)

    upsert_progress_to_sheet(user_id, word_row, updated_record)


# ============================================================
# 9. 載入資料
# ============================================================

words_df = load_words()

if words_df.empty:
    st.stop()

users_df = load_users_from_sheet()
progress_df = load_progress_from_sheet()

# 確保 progress_df 有完整欄位
for col in PROGRESS_HEADERS:
    if col not in progress_df.columns:
        progress_df[col] = ""

progress_df = progress_df[PROGRESS_HEADERS].fillna("")


# ============================================================
# 10. 側邊欄：選擇使用者
# ============================================================

st.sidebar.header("👤 使用者")

if users_df.empty:
    st.error("users 工作表沒有使用者資料。")
    st.stop()

user_options = {
    f"{row['user_name']}（{row['user_id']}）": row["user_id"]
    for _, row in users_df.iterrows()
}

selected_user_label = st.sidebar.selectbox("選擇使用者", list(user_options.keys()))
selected_user_id = user_options[selected_user_label]
selected_user_name = selected_user_label.split("（")[0]


# ============================================================
# 11. 合併單字資料與該使用者的學習紀錄
# ============================================================

user_progress_df = progress_df[progress_df["user_id"].astype(str) == selected_user_id].copy()

merged_df = words_df.merge(
    user_progress_df,
    on="word_id",
    how="left",
    suffixes=("", "_progress")
)

# progress 欄位補空
for col in PROGRESS_HEADERS:
    if col not in merged_df.columns:
        merged_df[col] = ""

# word / grade 等欄位 merge 後可能有 progress 版本，這裡以 words.csv 為主
merged_df["status"] = merged_df["status"].replace("", "未學")
merged_df["mastery"] = merged_df["mastery"].replace("", "0")
merged_df["review_count"] = merged_df["review_count"].replace("", "0")
merged_df["correct_count"] = merged_df["correct_count"].replace("", "0")
merged_df["wrong_count"] = merged_df["wrong_count"].replace("", "0")
merged_df["streak_correct"] = merged_df["streak_correct"].replace("", "0")

merged_df = merged_df.fillna("")


# ============================================================
# 12. 側邊欄：學習範圍與模式
# ============================================================

st.sidebar.divider()
st.sidebar.header("📚 選擇學習範圍")

mode = st.sidebar.radio(
    "學習模式",
    ["全部單字", "今日複習", "未學單字", "學習中", "已掌握"],
    index=0
)

filtered_df = merged_df.copy()

grade_options = ["全部"] + sorted([x for x in filtered_df["grade"].unique().tolist() if safe_str(x)])
selected_grade = st.sidebar.selectbox("年級", grade_options)

if selected_grade != "全部":
    filtered_df = filtered_df[filtered_df["grade"] == selected_grade]

semester_options = ["全部"] + sorted([x for x in filtered_df["semester"].unique().tolist() if safe_str(x)])
selected_semester = st.sidebar.selectbox("學期", semester_options)

if selected_semester != "全部":
    filtered_df = filtered_df[filtered_df["semester"] == selected_semester]

lesson_options = ["全部"] + sorted([x for x in filtered_df["lesson"].unique().tolist() if safe_str(x)])
selected_lesson = st.sidebar.selectbox("課次", lesson_options)

if selected_lesson != "全部":
    filtered_df = filtered_df[filtered_df["lesson"] == selected_lesson]

pos_options = ["全部"] + sorted([x for x in filtered_df["pos_zh"].unique().tolist() if safe_str(x)])
selected_pos = st.sidebar.selectbox("詞性", pos_options)

if selected_pos != "全部":
    filtered_df = filtered_df[filtered_df["pos_zh"] == selected_pos]

keyword = st.sidebar.text_input("搜尋單字、中文、例句、用法或標籤")

if keyword.strip():
    keyword_lower = keyword.strip().lower()

    search_columns = [
        "word", "meaning", "pos", "pos_zh", "tags", "note",
        "required_prepositions", "usage_patterns",
        "example_1", "example_2", "example_3", "example_4", "example_5",
        "example_zh_1", "example_zh_2", "example_zh_3", "example_zh_4", "example_zh_5"
    ]

    search_columns = [col for col in search_columns if col in filtered_df.columns]

    mask = False
    for col in search_columns:
        mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword_lower, na=False)

    filtered_df = filtered_df[mask]

today_str = date.today().isoformat()

if mode == "今日複習":
    filtered_df = filtered_df[
        (filtered_df["next_review"].astype(str) == "") |
        (filtered_df["next_review"].astype(str) <= today_str)
    ]

elif mode == "未學單字":
    filtered_df = filtered_df[filtered_df["status"].astype(str).isin(["", "未學"])]

elif mode == "學習中":
    filtered_df = filtered_df[filtered_df["status"].astype(str).isin(["學習中", "熟悉"])]

elif mode == "已掌握":
    filtered_df = filtered_df[filtered_df["status"].astype(str) == "已掌握"]


# ============================================================
# 13. 側邊欄：學習統計
# ============================================================

st.sidebar.divider()
st.sidebar.header("📊 學習統計")

total_words = len(merged_df)
not_started = len(merged_df[merged_df["status"].astype(str).isin(["", "未學"])])
learning = len(merged_df[merged_df["status"].astype(str).isin(["學習中", "熟悉"])])
mastered = len(merged_df[merged_df["status"].astype(str) == "已掌握"])

due_today = len(
    merged_df[
        (merged_df["next_review"].astype(str) == "") |
        (merged_df["next_review"].astype(str) <= today_str)
    ]
)

st.sidebar.write(f"使用者：**{selected_user_name}**")
st.sidebar.write(f"全部單字：**{total_words}**")
st.sidebar.write(f"今日可複習：**{due_today}**")
st.sidebar.write(f"未學：**{not_started}**")
st.sidebar.write(f"學習中 / 熟悉：**{learning}**")
st.sidebar.write(f"已掌握：**{mastered}**")


# ============================================================
# 14. 主畫面標題與統計卡
# ============================================================

st.markdown('<div class="main-title">📘 國中英文單字複習</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="small-caption">第二階段正式版：Google Sheets 學習紀錄 + 多使用者進度</div>',
    unsafe_allow_html=True
)

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("目前範圍單字", len(filtered_df))
metric_col2.metric("今日可複習", due_today)
metric_col3.metric("學習中", learning)
metric_col4.metric("已掌握", mastered)

st.caption(
    f"使用者：{selected_user_name}　｜　目前範圍：{selected_grade} / {selected_semester} / {selected_lesson} / {selected_pos}　｜　模式：{mode}"
)

if filtered_df.empty:
    st.warning("目前範圍沒有單字，請調整左側篩選條件。")
    st.stop()


# ============================================================
# 15. 單字卡索引控制
# ============================================================

filter_signature = hashlib.md5(
    "|".join([
        selected_user_id, mode, selected_grade, selected_semester, selected_lesson, selected_pos, keyword
    ]).encode("utf-8")
).hexdigest()

if "last_filter_signature" not in st.session_state:
    st.session_state.last_filter_signature = filter_signature

if st.session_state.last_filter_signature != filter_signature:
    st.session_state.card_index = 0
    st.session_state.last_filter_signature = filter_signature

if "card_index" not in st.session_state:
    st.session_state.card_index = 0

if st.session_state.card_index >= len(filtered_df):
    st.session_state.card_index = 0

filtered_df = filtered_df.reset_index(drop=True)
current_word = filtered_df.iloc[st.session_state.card_index]
current_word_id = safe_str(current_word["word_id"])


# ============================================================
# 16. 取得目前單字的學習紀錄
# ============================================================

current_progress_row = user_progress_df[
    user_progress_df["word_id"].astype(str) == current_word_id
]

if len(current_progress_row) > 0:
    current_progress = current_progress_row.iloc[0].to_dict()
else:
    current_progress = normalize_progress_record({}, selected_user_id, current_word)


# ============================================================
# 17. 自動播放單字與第一句例句
# ============================================================

if "last_autoplay_word_id" not in st.session_state:
    st.session_state.last_autoplay_word_id = ""

autoplay_key = f"{selected_user_id}|{current_word_id}"

if st.session_state.last_autoplay_word_id != autoplay_key:
    word_audio = get_audio_file(safe_str(current_word["word"]))
    autoplay_audio(word_audio)
    st.session_state.last_autoplay_word_id = autoplay_key


# ============================================================
# 18. 單字卡：左右兩欄
# ============================================================

left_col, right_col = st.columns([0.92, 1.35], gap="large")

with left_col:
    st.markdown('<div class="word-card">', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="word-text">{html.escape(safe_str(current_word["word"]))}</div>
        <div class="meaning-text">{html.escape(safe_str(current_word["meaning"]))}</div>
        """,
        unsafe_allow_html=True
    )

    st.write("")
    audio_button(safe_str(current_word["word"]), "🔊 重聽單字", key=f"word_audio_{selected_user_id}_{current_word_id}")

    st.divider()

    st.write(f"**詞性：** {safe_str(current_word.get('pos', ''))}")

    if safe_str(current_word.get("pos_note", "")):
        st.caption(safe_str(current_word.get("pos_note", "")))

    st.markdown('<div class="section-title">學習狀態</div>', unsafe_allow_html=True)

    progress_rows = [
        ("使用者", selected_user_name),
        ("狀態", safe_str(current_progress.get("status", "未學"))),
        ("熟練度", f"{safe_str(current_progress.get('mastery', '0'))} / 100"),
        ("複習次數", safe_str(current_progress.get("review_count", "0"))),
        ("答對次數", safe_str(current_progress.get("correct_count", "0"))),
        ("答錯次數", safe_str(current_progress.get("wrong_count", "0"))),
        ("連續答對", safe_str(current_progress.get("streak_correct", "0"))),
        ("上次複習", safe_str(current_progress.get("last_review", ""))),
        ("下次複習", safe_str(current_progress.get("next_review", ""))),
    ]
    show_info_table(progress_rows)

    st.markdown('<div class="section-title">我對這個字的熟悉度</div>', unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    b3, b4 = st.columns(2)

    with b1:
        if st.button("😵 忘記了", use_container_width=True, key=f"forgot_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "forgot", current_progress)
            st.success("已同步到 Google Sheets：忘記了。明天會再複習。")
            st.rerun()

    with b2:
        if st.button("😐 不熟", use_container_width=True, key=f"hard_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "hard", current_progress)
            st.success("已同步到 Google Sheets：不熟。2 天後會再複習。")
            st.rerun()

    with b3:
        if st.button("🙂 認識", use_container_width=True, key=f"good_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "good", current_progress)
            st.success("已同步到 Google Sheets：認識。4 天後會再複習。")
            st.rerun()

    with b4:
        if st.button("😄 很熟", use_container_width=True, key=f"easy_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "easy", current_progress)
            st.success("已同步到 Google Sheets：很熟。會延後複習。")
            st.rerun()

    st.divider()

    nav1, nav2, nav3 = st.columns([1, 1.2, 1])

    with nav1:
        if st.button("⬅️ 上一個", use_container_width=True):
            st.session_state.card_index -= 1
            if st.session_state.card_index < 0:
                st.session_state.card_index = len(filtered_df) - 1
            st.rerun()

    with nav2:
        st.write(f"第 {st.session_state.card_index + 1} / {len(filtered_df)} 個")

    with nav3:
        if st.button("下一個 ➡️", use_container_width=True):
            st.session_state.card_index += 1
            if st.session_state.card_index >= len(filtered_df):
                st.session_state.card_index = 0
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


with right_col:
    st.markdown('<div class="section-title">基本資料</div>', unsafe_allow_html=True)

    basic_rows = [
        ("年級", safe_str(current_word.get("grade", ""))),
        ("學期", safe_str(current_word.get("semester", ""))),
        ("課次", safe_str(current_word.get("lesson", ""))),
        ("標籤", safe_str(current_word.get("tags", ""))),
        ("補充說明", safe_str(current_word.get("note", ""))),
    ]
    show_info_table(basic_rows)

    pos_en = safe_str(current_word.get("pos_en", "")).lower()
    pos = safe_str(current_word.get("pos", "")).lower()

    is_verb = ("verb" in pos_en) or ("verb" in pos) or ("動詞" in safe_str(current_word.get("pos_zh", "")))

    if is_verb:
        st.markdown('<div class="section-title">動詞資料</div>', unsafe_allow_html=True)

        base_form = safe_str(current_word.get("base_form", ""))
        if not base_form:
            base_form = safe_str(current_word.get("word", ""))

        verb_rows = [
            ("原形", base_form),
            ("過去式", safe_str(current_word.get("past", ""))),
            ("過去分詞", safe_str(current_word.get("past_participle", ""))),
            ("現在分詞", safe_str(current_word.get("present_participle", ""))),
            ("及物 / 不及物", safe_str(current_word.get("transitivity", ""))),
        ]
        show_info_table(verb_rows)

        if base_form:
            audio_button(base_form, "🔊 原形發音", key=f"base_audio_{selected_user_id}_{current_word_id}")

    plural = safe_str(current_word.get("plural", ""))
    plural_rule = safe_str(current_word.get("plural_rule", ""))

    if plural or plural_rule:
        st.markdown('<div class="section-title">名詞 / 數字用法</div>', unsafe_allow_html=True)

        noun_rows = [
            ("複數形", plural),
            ("複數規則", plural_rule),
        ]
        show_info_table(noun_rows)

    required_prepositions = safe_str(current_word.get("required_prepositions", ""))
    usage_patterns = safe_str(current_word.get("usage_patterns", ""))

    if required_prepositions or usage_patterns:
        st.markdown('<div class="section-title">常用用法</div>', unsafe_allow_html=True)

        usage_rows = [
            ("常搭配介系詞", required_prepositions),
            ("常用句型 / 用法", usage_patterns),
        ]
        show_info_table(usage_rows)


# ============================================================
# 19. 例句
# ============================================================

st.divider()
st.markdown('<div class="section-title">例句</div>', unsafe_allow_html=True)

examples = []

for i in range(1, 6):
    en_col = f"example_{i}"
    zh_col = f"example_zh_{i}"

    en_text = safe_str(current_word.get(en_col, ""))
    zh_text = safe_str(current_word.get(zh_col, ""))

    if en_text:
        examples.append((i, en_text, zh_text))

if not examples:
    old_en = safe_str(current_word.get("example", ""))
    old_zh = safe_str(current_word.get("example_zh", ""))
    if old_en:
        examples.append((1, old_en, old_zh))

if examples:
    first_example_text = examples[0][1]
    if "last_autoplay_example_id" not in st.session_state:
        st.session_state.last_autoplay_example_id = ""

    example_autoplay_id = f"{selected_user_id}|{current_word_id}|{first_example_text}"

    if st.session_state.last_autoplay_example_id != example_autoplay_id:
        example_audio = get_audio_file(first_example_text)
        autoplay_audio(example_audio)
        st.session_state.last_autoplay_example_id = example_autoplay_id

example_cols = st.columns(2)

for idx, (num, en_text, zh_text) in enumerate(examples):
    with example_cols[idx % 2]:
        example_html = f"""
        <div class="example-card">
            <div class="example-en">{num}. {html.escape(en_text)}</div>
            <div class="example-zh">{html.escape(zh_text)}</div>
        </div>
        """
        st.markdown(example_html, unsafe_allow_html=True)
        audio_button(en_text, f"🔊 播放例句 {num}", key=f"example_audio_{selected_user_id}_{current_word_id}_{num}")


# ============================================================
# 20. 資料檢視與備份
# ============================================================

st.divider()

with st.expander("查看目前範圍的單字與學習狀態"):
    display_columns = [
        "word", "meaning", "pos", "grade", "semester", "lesson",
        "status", "mastery", "review_count", "correct_count", "wrong_count",
        "last_review", "next_review"
    ]

    display_columns = [col for col in display_columns if col in filtered_df.columns]

    st.dataframe(
        filtered_df[display_columns],
        use_container_width=True,
        hide_index=True
    )


with st.expander("查看 Google Sheets 學習紀錄 / 下載備份"):
    st.write("目前學習紀錄直接存放在 Google Sheets 的 `progress` 工作表。")
    st.write(f"目前顯示使用者：**{selected_user_name}**")

    selected_progress = progress_df[progress_df["user_id"].astype(str) == selected_user_id]

    if selected_progress.empty:
        st.info("這位使用者目前還沒有任何學習紀錄。按下熟悉度按鈕後，就會寫入 Google Sheets。")
    else:
        st.dataframe(selected_progress, use_container_width=True, hide_index=True)

        csv_bytes = selected_progress.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"下載 {selected_user_name} 的學習紀錄 CSV",
            data=csv_bytes,
            file_name=f"{selected_user_id}_progress_backup.csv",
            mime="text/csv",
            key=f"download_progress_{selected_user_id}"
        )


with st.expander("Google Sheets 設定檢查"):
    st.write("這一版不使用 `progress.db`。")
    st.write("學習紀錄會寫入 Google Sheets。")
    st.write("需要的工作表：`users`、`progress`。")
    st.write("若工作表不存在，程式會嘗試自動建立。")
    st.write("若無法連線，請檢查 Streamlit Secrets 與 Google Sheet 分享權限。")
