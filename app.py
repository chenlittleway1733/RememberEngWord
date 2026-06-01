import streamlit as st
import pandas as pd
from pathlib import Path
import asyncio
import hashlib
import sqlite3
from datetime import date, datetime, timedelta
import base64
import html
import io

# ============================================================
# 國中英文單字智慧複習系統
# app_v11.py
#
# 本版方向：
# 回到 SQLite + 下載備份，不使用 Google Sheets。
#
# 目前功能：
# 1. words.csv 作為單字資料來源
# 2. progress.db 作為本機 / Streamlit 執行環境中的學習紀錄資料庫
# 3. 支援三個使用者：女兒、兒子、測試帳
# 4. 每位使用者的學習紀錄分開
# 5. 單字卡、自動發音、例句發音
# 6. 忘記了 / 不熟 / 認識 / 很熟
# 7. 簡化記憶曲線
# 8. 今日複習、未學單字、學習中、已掌握
# 9. 依帳號下載 / 上傳 CSV 備份，並可還原完整 progress.db
# ============================================================


# ============================================================
# 1. 基本檔案路徑設定
# ============================================================

DATA_PATH = Path("words.csv")
DB_PATH = Path("progress.db")

AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

VOICE = "en-US-JennyNeural"


# ============================================================
# 2. 使用者設定
# ============================================================

USERS = {
    "daughter": "女兒",
    "son": "兒子",
    "test": "測試帳",
}


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
    """把任何資料安全轉成字串。"""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def safe_int(value, default=0) -> int:
    """把任何資料安全轉成整數。"""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def make_word_id(row: pd.Series) -> str:
    """
    建立單字唯一 ID。
    使用年級、學期、課次、單字組合。
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
    """同一句文字對應同一個音檔。"""
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    return AUDIO_DIR / f"{text_hash}.mp3"


async def _create_audio_async(text: str, output_path: Path):
    """使用 edge-tts 產生 mp3。"""
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=VOICE)
    await communicate.save(str(output_path))


def get_audio_file(text: str) -> Path | None:
    """取得發音檔，若不存在就自動產生。"""
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


def autoplay_audio(audio_path: Path | None):
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


# ============================================================
# 6. 讀取 words.csv
# ============================================================

@st.cache_data
def load_words() -> pd.DataFrame:
    """讀取單字表。"""
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
# 7. SQLite 資料庫
# ============================================================

def get_conn():
    """連線到 SQLite 資料庫。"""
    return sqlite3.connect(DB_PATH)


def init_db():
    """建立 users 與 progress 資料表。"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            role TEXT DEFAULT 'learner',
            created_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            user_id TEXT NOT NULL,
            word_id TEXT NOT NULL,
            word TEXT,
            grade TEXT,
            semester TEXT,
            lesson TEXT,
            status TEXT DEFAULT '未學',
            mastery INTEGER DEFAULT 0,
            review_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak_correct INTEGER DEFAULT 0,
            last_review TEXT,
            next_review TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, word_id)
        )
        """
    )

    now = datetime.now().isoformat(timespec="seconds")
    for user_id, user_name in USERS.items():
        role = "test" if user_id == "test" else "learner"
        cur.execute(
            """
            INSERT OR IGNORE INTO users (user_id, user_name, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, user_name, role, now)
        )

    conn.commit()
    conn.close()


def ensure_progress_for_words(df: pd.DataFrame):
    """
    確保每位使用者、每個單字，都有一筆 progress 紀錄。
    """
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")

    for user_id in USERS.keys():
        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT OR IGNORE INTO progress
                (user_id, word_id, word, grade, semester, lesson, status, mastery,
                 review_count, correct_count, wrong_count, streak_correct,
                 last_review, next_review, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '未學', 0, 0, 0, 0, 0, NULL, NULL, ?)
                """,
                (
                    user_id,
                    safe_str(row["word_id"]),
                    safe_str(row.get("word", "")),
                    safe_str(row.get("grade", "")),
                    safe_str(row.get("semester", "")),
                    safe_str(row.get("lesson", "")),
                    now,
                )
            )

    conn.commit()
    conn.close()


def load_users() -> pd.DataFrame:
    """讀取使用者資料。"""
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM users ORDER BY user_id", conn)
    conn.close()
    return df


def load_progress(user_id: str | None = None) -> pd.DataFrame:
    """讀取學習紀錄。"""
    conn = get_conn()

    if user_id:
        df = pd.read_sql_query(
            "SELECT * FROM progress WHERE user_id = ?",
            conn,
            params=(user_id,)
        )
    else:
        df = pd.read_sql_query("SELECT * FROM progress", conn)

    conn.close()
    return df


def get_progress(user_id: str, word_id: str) -> dict:
    """讀取某位使用者某個單字的學習紀錄。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM progress WHERE user_id = ? AND word_id = ?",
        (user_id, word_id)
    )
    row = cur.fetchone()
    columns = [desc[0] for desc in cur.description] if cur.description else []
    conn.close()

    if row is None:
        return {}

    return dict(zip(columns, row))


def calculate_review_result(level: str, current_progress: dict) -> dict:
    """
    根據熟悉度按鈕計算新紀錄。
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
        "mastery": mastery,
        "review_count": review_count,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "streak_correct": streak_correct,
        "last_review": today.isoformat(),
        "next_review": next_review.isoformat(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def update_progress(user_id: str, word_row: pd.Series, level: str):
    """更新學習紀錄。"""
    word_id = safe_str(word_row["word_id"])
    current_progress = get_progress(user_id, word_id)
    result = calculate_review_result(level, current_progress)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE progress
        SET
            word = ?,
            grade = ?,
            semester = ?,
            lesson = ?,
            status = ?,
            mastery = ?,
            review_count = ?,
            correct_count = ?,
            wrong_count = ?,
            streak_correct = ?,
            last_review = ?,
            next_review = ?,
            updated_at = ?
        WHERE user_id = ? AND word_id = ?
        """,
        (
            safe_str(word_row.get("word", "")),
            safe_str(word_row.get("grade", "")),
            safe_str(word_row.get("semester", "")),
            safe_str(word_row.get("lesson", "")),
            result["status"],
            result["mastery"],
            result["review_count"],
            result["correct_count"],
            result["wrong_count"],
            result["streak_correct"],
            result["last_review"],
            result["next_review"],
            result["updated_at"],
            user_id,
            word_id,
        )
    )

    conn.commit()
    conn.close()


def import_user_progress_from_csv(user_id: str, csv_df: pd.DataFrame, import_mode: str = "replace") -> tuple[bool, str]:
    """
    匯入單一使用者的學習紀錄 CSV。

    import_mode:
    - replace：先刪除這個使用者原本所有進度，再匯入 CSV
    - merge：只更新 CSV 裡有的紀錄，原本其他單字紀錄保留

    為了避免把女兒紀錄匯到兒子帳號，程式會強制把匯入資料的 user_id 改成目前選定的 user_id。
    """
    required_cols = [
        "word_id", "word", "grade", "semester", "lesson", "status",
        "mastery", "review_count", "correct_count", "wrong_count",
        "streak_correct", "last_review", "next_review", "updated_at"
    ]

    missing_cols = [col for col in required_cols if col not in csv_df.columns]
    if missing_cols:
        return False, f"CSV 缺少欄位：{', '.join(missing_cols)}"

    conn = get_conn()
    cur = conn.cursor()

    if import_mode == "replace":
        cur.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))

    for _, row in csv_df.iterrows():
        word_id = safe_str(row.get("word_id", ""))
        if not word_id:
            continue

        cur.execute(
            """
            INSERT OR REPLACE INTO progress
            (user_id, word_id, word, grade, semester, lesson, status, mastery,
             review_count, correct_count, wrong_count, streak_correct,
             last_review, next_review, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                word_id,
                safe_str(row.get("word", "")),
                safe_str(row.get("grade", "")),
                safe_str(row.get("semester", "")),
                safe_str(row.get("lesson", "")),
                safe_str(row.get("status", "未學")) or "未學",
                safe_int(row.get("mastery", 0)),
                safe_int(row.get("review_count", 0)),
                safe_int(row.get("correct_count", 0)),
                safe_int(row.get("wrong_count", 0)),
                safe_int(row.get("streak_correct", 0)),
                safe_str(row.get("last_review", "")),
                safe_str(row.get("next_review", "")),
                safe_str(row.get("updated_at", "")) or datetime.now().isoformat(timespec="seconds"),
            )
        )

    conn.commit()
    conn.close()

    # 確保 words.csv 內的新單字仍然有預設紀錄
    ensure_progress_for_words(words_df)

    return True, f"已匯入 {len(csv_df)} 筆紀錄到目前帳號。"


def restore_full_db(uploaded_file) -> tuple[bool, str]:
    """
    還原完整 progress.db。
    注意：這會覆蓋目前整個 progress.db，包含女兒、兒子、測試帳所有資料。
    """
    try:
        uploaded_bytes = uploaded_file.getvalue()

        # 先用記憶體測試是不是 SQLite 檔
        test_path = Path("progress_upload_test.db")
        test_path.write_bytes(uploaded_bytes)

        test_conn = sqlite3.connect(test_path)
        test_cur = test_conn.cursor()
        test_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [row[0] for row in test_cur.fetchall()]
        test_conn.close()
        test_path.unlink(missing_ok=True)

        if "progress" not in table_names:
            return False, "這個 db 檔沒有 progress 資料表，可能不是本程式的備份檔。"

        # 覆蓋目前資料庫
        DB_PATH.write_bytes(uploaded_bytes)

        # 重新初始化，確保必要資料表存在
        init_db()
        ensure_progress_for_words(words_df)

        return True, "已還原完整 progress.db。請重新整理頁面確認資料。"

    except Exception as e:
        return False, f"還原失敗：{e}"


# ============================================================
# 8. 載入資料與初始化
# ============================================================

words_df = load_words()

if words_df.empty:
    st.stop()

init_db()
ensure_progress_for_words(words_df)

users_df = load_users()


# ============================================================
# 9. 側邊欄：選擇使用者
# ============================================================

st.sidebar.header("👤 使用者")

user_options = {
    f"{row['user_name']}（{row['user_id']}）": row["user_id"]
    for _, row in users_df.iterrows()
}

selected_user_label = st.sidebar.selectbox("選擇使用者", list(user_options.keys()))
selected_user_id = user_options[selected_user_label]
selected_user_name = selected_user_label.split("（")[0]


# ============================================================
# 10. 合併單字與目前使用者進度
# ============================================================

progress_df = load_progress(selected_user_id)

merged_df = words_df.merge(
    progress_df,
    on="word_id",
    how="left",
    suffixes=("", "_progress")
)

# 缺漏值補齊
for col in [
    "status", "mastery", "review_count", "correct_count", "wrong_count",
    "streak_correct", "last_review", "next_review"
]:
    if col not in merged_df.columns:
        merged_df[col] = ""

merged_df["status"] = merged_df["status"].replace("", "未學")
merged_df["mastery"] = merged_df["mastery"].replace("", 0)
merged_df["review_count"] = merged_df["review_count"].replace("", 0)
merged_df["correct_count"] = merged_df["correct_count"].replace("", 0)
merged_df["wrong_count"] = merged_df["wrong_count"].replace("", 0)
merged_df["streak_correct"] = merged_df["streak_correct"].replace("", 0)

merged_df = merged_df.fillna("")


# ============================================================
# 11. 側邊欄：範圍與模式
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
# 12. 統計
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
# 13. 主畫面
# ============================================================

st.markdown('<div class="main-title">📘 國中英文單字複習</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="small-caption">第二階段：SQLite 學習紀錄 + 多使用者 + 分帳號上傳下載備份</div>',
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
# 14. 單字卡索引控制
# ============================================================

filter_signature = hashlib.md5(
    "|".join([
        selected_user_id, mode, selected_grade, selected_semester,
        selected_lesson, selected_pos, keyword
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
current_progress = get_progress(selected_user_id, current_word_id)


# ============================================================
# 15. 自動播放單字
# ============================================================

if "last_autoplay_word_id" not in st.session_state:
    st.session_state.last_autoplay_word_id = ""

autoplay_key = f"{selected_user_id}|{current_word_id}"

if st.session_state.last_autoplay_word_id != autoplay_key:
    word_audio = get_audio_file(safe_str(current_word["word"]))
    autoplay_audio(word_audio)
    st.session_state.last_autoplay_word_id = autoplay_key


# ============================================================
# 16. 單字卡左右欄
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
        ("熟練度", f"{safe_str(current_progress.get('mastery', 0))} / 100"),
        ("複習次數", safe_str(current_progress.get("review_count", 0))),
        ("答對次數", safe_str(current_progress.get("correct_count", 0))),
        ("答錯次數", safe_str(current_progress.get("wrong_count", 0))),
        ("連續答對", safe_str(current_progress.get("streak_correct", 0))),
        ("上次複習", safe_str(current_progress.get("last_review", ""))),
        ("下次複習", safe_str(current_progress.get("next_review", ""))),
    ]
    show_info_table(progress_rows)

    st.markdown('<div class="section-title">我對這個字的熟悉度</div>', unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    b3, b4 = st.columns(2)

    with b1:
        if st.button("😵 忘記了", use_container_width=True, key=f"forgot_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "forgot")
            st.success("已記錄：忘記了。明天會再複習。")
            st.rerun()

    with b2:
        if st.button("😐 不熟", use_container_width=True, key=f"hard_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "hard")
            st.success("已記錄：不熟。2 天後會再複習。")
            st.rerun()

    with b3:
        if st.button("🙂 認識", use_container_width=True, key=f"good_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "good")
            st.success("已記錄：認識。4 天後會再複習。")
            st.rerun()

    with b4:
        if st.button("😄 很熟", use_container_width=True, key=f"easy_{selected_user_id}_{current_word_id}"):
            update_progress(selected_user_id, current_word, "easy")
            st.success("已記錄：很熟。會延後複習。")
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
# 17. 例句
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

# 自動播放第一句例句一次
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
# 18. 資料檢視與備份下載
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


with st.expander("備份 / 上傳更新學習紀錄"):
    st.write("目前學習紀錄存在 `progress.db`。")
    st.warning("如果部署在 Streamlit Cloud，重新部署或休眠後資料可能遺失，建議定期下載備份。")

    all_progress = load_progress()
    selected_progress = load_progress(selected_user_id)

    tab_download, tab_upload_user, tab_upload_db = st.tabs([
        "下載備份",
        "上傳單一帳號紀錄",
        "還原完整資料庫"
    ])

    with tab_download:
        st.subheader("下載備份")
        st.write(f"目前使用者：**{selected_user_name}**")
        st.write(f"這位使用者目前共有 **{len(selected_progress)}** 筆學習紀錄。")

        st.dataframe(selected_progress, use_container_width=True, hide_index=True)

        csv_bytes = selected_progress.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"下載 {selected_user_name} 的學習紀錄 CSV",
            data=csv_bytes,
            file_name=f"{selected_user_id}_progress_backup.csv",
            mime="text/csv",
            key=f"download_csv_{selected_user_id}"
        )

        all_csv_bytes = all_progress.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="下載全部使用者學習紀錄 CSV",
            data=all_csv_bytes,
            file_name="all_progress_backup.csv",
            mime="text/csv",
            key="download_all_csv"
        )

        if DB_PATH.exists():
            with open(DB_PATH, "rb") as db_file:
                st.download_button(
                    label="下載 progress.db 完整備份",
                    data=db_file,
                    file_name="progress.db",
                    mime="application/octet-stream",
                    key="download_db"
                )
        else:
            st.error("目前找不到 progress.db。")

    with tab_upload_user:
        st.subheader("上傳單一帳號紀錄")
        st.info(
            f"這裡只會更新目前選定帳號：{selected_user_name}（{selected_user_id}）。"
            "即使 CSV 裡有其他 user_id，匯入時也會改成目前帳號，避免匯錯。"
        )

        import_mode_label = st.radio(
            "匯入方式",
            ["覆蓋目前帳號紀錄", "合併更新目前帳號紀錄"],
            index=0,
            key=f"import_mode_{selected_user_id}"
        )

        import_mode = "replace" if import_mode_label == "覆蓋目前帳號紀錄" else "merge"

        uploaded_csv = st.file_uploader(
            f"上傳 {selected_user_name} 的 progress CSV 備份",
            type=["csv"],
            key=f"upload_csv_{selected_user_id}"
        )

        confirm_user_import = st.checkbox(
            f"我確認要把上傳的 CSV 匯入到 {selected_user_name} 帳號",
            key=f"confirm_user_import_{selected_user_id}"
        )

        if uploaded_csv is not None:
            try:
                preview_df = pd.read_csv(uploaded_csv)
                st.write("CSV 預覽：")
                st.dataframe(preview_df.head(10), use_container_width=True, hide_index=True)

                if st.button("開始匯入單一帳號紀錄", disabled=not confirm_user_import, key=f"start_import_{selected_user_id}"):
                    ok, msg = import_user_progress_from_csv(selected_user_id, preview_df, import_mode=import_mode)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

            except Exception as e:
                st.error(f"讀取 CSV 失敗：{e}")

    with tab_upload_db:
        st.subheader("還原完整 progress.db")
        st.error("這個功能會覆蓋整個 progress.db，包含女兒、兒子、測試帳所有資料。請只有在完整還原備份時使用。")

        uploaded_db = st.file_uploader(
            "上傳 progress.db 完整備份",
            type=["db", "sqlite", "sqlite3"],
            key="upload_full_db"
        )

        confirm_db_restore = st.checkbox(
            "我確認要覆蓋目前完整 progress.db",
            key="confirm_db_restore"
        )

        if uploaded_db is not None:
            st.write(f"已選擇檔案：{uploaded_db.name}")

            if st.button("開始還原完整資料庫", disabled=not confirm_db_restore, key="start_restore_db"):
                ok, msg = restore_full_db(uploaded_db)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


with st.expander("開發備註：目前版本"):
    st.markdown(
        """
        目前版本已回到 SQLite + 下載備份，不使用 Google Sheets。

        檔案說明：

        - `words.csv`：單字資料
        - `progress.db`：學習紀錄資料庫，可完整下載與還原
        - `audio_cache/`：發音 mp3 快取

        支援三個使用者：

        - 女兒
        - 兒子
        - 測試帳
        
        備份功能：
        
        - 可依目前帳號下載 CSV
        - 可依目前帳號上傳 CSV 更新紀錄
        - 可下載全部使用者 CSV
        - 可下載 / 還原完整 progress.db

        接下來可繼續開發：

        1. 第三階段：基本測驗功能
        2. 第四階段：錯題本
        3. 第五階段：每日任務
        """
    )
