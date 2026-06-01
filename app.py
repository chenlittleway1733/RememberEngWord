import streamlit as st
import pandas as pd
from pathlib import Path
import asyncio
import hashlib
import sqlite3
from datetime import date, datetime, timedelta
import base64
import html

# ============================================================
# 國中英文單字智慧複習系統
# app_v6.py
#
# 目前版本功能：
# 第一階段：
# 1. 讀取 words.csv
# 2. 單字卡
# 3. 年級 / 學期 / 課次 / 詞性篩選
# 4. 單字與例句顯示
# 5. edge-tts 發音
# 6. 開啟單字卡後自動播放單字一次
#
# 第二階段：
# 1. 使用 SQLite 建立 progress.db
# 2. 記錄每個單字的學習狀況
# 3. 加入「忘記了 / 不熟 / 認識 / 很熟」按鈕
# 4. 依簡化記憶曲線自動安排下次複習日
# 5. 今日複習清單
# 6. 學習進度統計
# ============================================================


# ============================================================
# 1. 基本檔案路徑設定
# ============================================================

# 單字表固定使用 words.csv
DATA_PATH = Path("words.csv")

# 學習紀錄資料庫
DB_PATH = Path("progress.db")

# 發音快取資料夾
AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

# edge-tts 語音設定
# zh-TW-HsiaoChenNeural 是中文聲音，英文建議用 en-US-JennyNeural 或 en-US-AriaNeural
VOICE = "en-US-JennyNeural"


# ============================================================
# 2. Streamlit 頁面設定
# ============================================================

st.set_page_config(
    page_title="國中英文單字複習",
    page_icon="📘",
    layout="wide"
)


# ============================================================
# 3. 自訂 CSS：讓畫面比較適合 iPad 橫向瀏覽
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
# 4. 小工具函式
# ============================================================

def safe_str(value) -> str:
    """把任何資料安全轉成字串，避免 NaN 或 None 造成顯示錯誤。"""
    if pd.isna(value):
        return ""
    return str(value).strip()


def make_word_id(row: pd.Series) -> str:
    """
    建立單字的唯一 ID。
    因為 words.csv 可能沒有 word_id 欄位，所以用年級、學期、課次、單字組合。
    之後如果同一個字出現在不同課，也能分開記錄。
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
    """
    根據文字內容產生固定音檔檔名。
    這樣同一句話不會重複產生音檔。
    """
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    return AUDIO_DIR / f"{text_hash}.mp3"


async def _create_audio_async(text: str, output_path: Path):
    """使用 edge-tts 非同步產生 mp3。"""
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=VOICE)
    await communicate.save(str(output_path))


def get_audio_file(text: str) -> Path | None:
    """
    取得文字的發音檔。
    如果音檔不存在，就自動產生。
    """
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
        # 某些執行環境 event loop 已存在時，改用新的 event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_create_audio_async(text, output_path))
        loop.close()
        return output_path
    except Exception as e:
        st.warning(f"產生發音失敗：{e}")
        return None


def autoplay_audio(audio_path: Path):
    """
    自動播放音檔。
    Streamlit 原生 st.audio 需要再按播放鈕。
    這裡用 HTML audio autoplay，讓單字卡切換時自動播放一次。
    """
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
    """
    顯示手動播放按鈕。
    雖然單字卡會自動播放單字，但保留按鈕方便重聽。
    """
    if st.button(label, key=key):
        audio_path = get_audio_file(text)
        autoplay_audio(audio_path)


def show_info_table(rows: list[tuple[str, str]]):
    """
    用表格顯示資料。
    rows 格式：[("欄位名稱", "內容"), ...]
    空內容不顯示。
    """
    clean_rows = [(k, v) for k, v in rows if safe_str(v)]
    if not clean_rows:
        return

    df = pd.DataFrame(clean_rows, columns=["項目", "內容"])
    st.dataframe(df, hide_index=True, use_container_width=True)


# ============================================================
# 5. 讀取 words.csv
# ============================================================

@st.cache_data
def load_words() -> pd.DataFrame:
    """
    讀取 words.csv。
    @st.cache_data 的意思是資料沒有變時，Streamlit 不會每次重跑都重新讀檔。
    """
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請確認 words.csv 和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH)
    df = df.fillna("")

    # 必要欄位：程式至少需要這些欄位才能運作
    required_columns = [
        "word", "meaning", "pos", "grade", "semester", "lesson"
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        st.error(f"words.csv 缺少必要欄位：{', '.join(missing_columns)}")
        return pd.DataFrame()

    # 若沒有 pos_en / pos_zh，也可以用 pos 先補上，避免程式中斷
    if "pos_en" not in df.columns:
        df["pos_en"] = df["pos"]
    if "pos_zh" not in df.columns:
        df["pos_zh"] = df["pos"]

    # 補上第二階段需要的 word_id
    df["word_id"] = df.apply(make_word_id, axis=1)

    return df


words_df = load_words()

if words_df.empty:
    st.stop()


# ============================================================
# 6. SQLite 資料庫：建立與讀寫學習紀錄
# ============================================================

def get_conn():
    """連線到 SQLite 資料庫。"""
    return sqlite3.connect(DB_PATH)


def init_db():
    """
    建立學習紀錄資料表。
    如果 progress.db 不存在，會自動建立。
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            word_id TEXT PRIMARY KEY,
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
            updated_at TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def ensure_progress_for_words(df: pd.DataFrame):
    """
    確保 words.csv 裡每一個單字，在 progress.db 都有一筆紀錄。
    """
    conn = get_conn()
    cur = conn.cursor()

    for _, row in df.iterrows():
        cur.execute(
            """
            INSERT OR IGNORE INTO progress
            (word_id, word, grade, semester, lesson, status, mastery, review_count,
             correct_count, wrong_count, streak_correct, last_review, next_review, updated_at)
            VALUES (?, ?, ?, ?, ?, '未學', 0, 0, 0, 0, 0, NULL, NULL, ?)
            """,
            (
                row["word_id"],
                safe_str(row.get("word", "")),
                safe_str(row.get("grade", "")),
                safe_str(row.get("semester", "")),
                safe_str(row.get("lesson", "")),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    conn.commit()
    conn.close()


def load_progress() -> pd.DataFrame:
    """讀取全部學習紀錄。"""
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM progress", conn)
    conn.close()
    return df


def get_progress(word_id: str) -> dict:
    """讀取單一單字的學習紀錄。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,))
    row = cur.fetchone()
    columns = [desc[0] for desc in cur.description] if cur.description else []
    conn.close()

    if row is None:
        return {}

    return dict(zip(columns, row))


def calculate_review_result(level: str, current_progress: dict) -> dict:
    """
    根據使用者按下的熟悉程度，計算新的學習紀錄。

    level 可為：
    - forgot：忘記了
    - hard：不熟
    - good：認識
    - easy：很熟
    """
    today = date.today()

    mastery = int(current_progress.get("mastery") or 0)
    review_count = int(current_progress.get("review_count") or 0)
    correct_count = int(current_progress.get("correct_count") or 0)
    wrong_count = int(current_progress.get("wrong_count") or 0)
    streak_correct = int(current_progress.get("streak_correct") or 0)

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

        # 連續答對越多，複習間隔越長
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


def update_progress(word_row: pd.Series, level: str):
    """
    更新單一單字的學習紀錄。
    """
    word_id = safe_str(word_row["word_id"])
    current_progress = get_progress(word_id)
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
        WHERE word_id = ?
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
            word_id,
        ),
    )

    conn.commit()
    conn.close()


# 初始化資料庫
init_db()
ensure_progress_for_words(words_df)


# ============================================================
# 7. 合併單字資料與學習紀錄
# ============================================================

progress_df = load_progress()
merged_df = words_df.merge(progress_df, on="word_id", how="left", suffixes=("", "_progress"))

# 避免空值造成錯誤
merged_df = merged_df.fillna("")


# ============================================================
# 8. 側邊欄：學習範圍與模式
# ============================================================

st.sidebar.header("📚 選擇學習範圍")

# 學習模式
mode = st.sidebar.radio(
    "學習模式",
    ["全部單字", "今日複習", "未學單字", "學習中", "已掌握"],
    index=0
)

filtered_df = merged_df.copy()

# 年級篩選
grade_options = ["全部"] + sorted([x for x in filtered_df["grade"].unique().tolist() if safe_str(x)])
selected_grade = st.sidebar.selectbox("年級", grade_options)

if selected_grade != "全部":
    filtered_df = filtered_df[filtered_df["grade"] == selected_grade]

# 學期篩選
semester_options = ["全部"] + sorted([x for x in filtered_df["semester"].unique().tolist() if safe_str(x)])
selected_semester = st.sidebar.selectbox("學期", semester_options)

if selected_semester != "全部":
    filtered_df = filtered_df[filtered_df["semester"] == selected_semester]

# 課次篩選
lesson_options = ["全部"] + sorted([x for x in filtered_df["lesson"].unique().tolist() if safe_str(x)])
selected_lesson = st.sidebar.selectbox("課次", lesson_options)

if selected_lesson != "全部":
    filtered_df = filtered_df[filtered_df["lesson"] == selected_lesson]

# 詞性篩選
pos_options = ["全部"] + sorted([x for x in filtered_df["pos_zh"].unique().tolist() if safe_str(x)])
selected_pos = st.sidebar.selectbox("詞性", pos_options)

if selected_pos != "全部":
    filtered_df = filtered_df[filtered_df["pos_zh"] == selected_pos]

# 搜尋功能
keyword = st.sidebar.text_input("搜尋單字、中文、例句、用法或標籤")

if keyword.strip():
    keyword = keyword.strip().lower()

    search_columns = [
        "word", "meaning", "pos", "pos_zh", "tags", "note",
        "required_prepositions", "usage_patterns",
        "example_1", "example_2", "example_3", "example_4", "example_5",
        "example_zh_1", "example_zh_2", "example_zh_3", "example_zh_4", "example_zh_5"
    ]

    # 只搜尋實際存在的欄位
    search_columns = [col for col in search_columns if col in filtered_df.columns]

    mask = False
    for col in search_columns:
        mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword, na=False)

    filtered_df = filtered_df[mask]

# 依模式篩選
today_str = date.today().isoformat()

if mode == "今日複習":
    # 今日複習包含：
    # 1. next_review 是空的：還沒學過
    # 2. next_review 小於等於今天：到期該複習
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
# 9. 側邊欄：學習統計
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

st.sidebar.write(f"全部單字：**{total_words}**")
st.sidebar.write(f"今日可複習：**{due_today}**")
st.sidebar.write(f"未學：**{not_started}**")
st.sidebar.write(f"學習中 / 熟悉：**{learning}**")
st.sidebar.write(f"已掌握：**{mastered}**")


# ============================================================
# 10. 主畫面標題與統計卡
# ============================================================

st.markdown('<div class="main-title">📘 國中英文單字複習</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="small-caption">第二階段：單字卡 + 自動發音 + SQLite 學習紀錄 + 簡化記憶曲線</div>',
    unsafe_allow_html=True
)

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("目前範圍單字", len(filtered_df))
metric_col2.metric("今日可複習", due_today)
metric_col3.metric("學習中", learning)
metric_col4.metric("已掌握", mastered)

st.caption(
    f"目前範圍：{selected_grade} / {selected_semester} / {selected_lesson} / {selected_pos}　｜　模式：{mode}"
)

if filtered_df.empty:
    st.warning("目前範圍沒有單字，請調整左側篩選條件。")
    st.stop()


# ============================================================
# 11. 單字卡索引控制
# ============================================================

# 每次篩選結果改變時，讓單字卡回到第一張
filter_signature = hashlib.md5(
    "|".join([
        mode, selected_grade, selected_semester, selected_lesson, selected_pos, keyword
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


# ============================================================
# 12. 自動播放控制
# ============================================================

# 只在切換到新單字時，自動播放單字一次
current_word_id = safe_str(current_word["word_id"])

if "last_autoplay_word_id" not in st.session_state:
    st.session_state.last_autoplay_word_id = ""

if st.session_state.last_autoplay_word_id != current_word_id:
    word_audio = get_audio_file(safe_str(current_word["word"]))
    autoplay_audio(word_audio)
    st.session_state.last_autoplay_word_id = current_word_id


# ============================================================
# 13. 單字卡：左右兩欄
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
    audio_button(safe_str(current_word["word"]), "🔊 重聽單字", key=f"word_audio_{current_word_id}")

    st.divider()

    st.write(f"**詞性：** {safe_str(current_word.get('pos', ''))}")

    if safe_str(current_word.get("pos_note", "")):
        st.caption(safe_str(current_word.get("pos_note", "")))

    # 學習狀態顯示
    progress = get_progress(current_word_id)

    st.markdown('<div class="section-title">學習狀態</div>', unsafe_allow_html=True)

    progress_rows = [
        ("狀態", safe_str(progress.get("status", "未學"))),
        ("熟練度", f"{progress.get('mastery', 0)} / 100"),
        ("複習次數", str(progress.get("review_count", 0))),
        ("答對次數", str(progress.get("correct_count", 0))),
        ("答錯次數", str(progress.get("wrong_count", 0))),
        ("連續答對", str(progress.get("streak_correct", 0))),
        ("上次複習", safe_str(progress.get("last_review", ""))),
        ("下次複習", safe_str(progress.get("next_review", ""))),
    ]
    show_info_table(progress_rows)

    st.markdown('<div class="section-title">我對這個字的熟悉度</div>', unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    b3, b4 = st.columns(2)

    with b1:
        if st.button("😵 忘記了", use_container_width=True, key=f"forgot_{current_word_id}"):
            update_progress(current_word, "forgot")
            st.success("已記錄：忘記了。明天會再複習。")
            st.rerun()

    with b2:
        if st.button("😐 不熟", use_container_width=True, key=f"hard_{current_word_id}"):
            update_progress(current_word, "hard")
            st.success("已記錄：不熟。2 天後會再複習。")
            st.rerun()

    with b3:
        if st.button("🙂 認識", use_container_width=True, key=f"good_{current_word_id}"):
            update_progress(current_word, "good")
            st.success("已記錄：認識。4 天後會再複習。")
            st.rerun()

    with b4:
        if st.button("😄 很熟", use_container_width=True, key=f"easy_{current_word_id}"):
            update_progress(current_word, "easy")
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
    # 基本資料
    st.markdown('<div class="section-title">基本資料</div>', unsafe_allow_html=True)

    basic_rows = [
        ("年級", safe_str(current_word.get("grade", ""))),
        ("學期", safe_str(current_word.get("semester", ""))),
        ("課次", safe_str(current_word.get("lesson", ""))),
        ("標籤", safe_str(current_word.get("tags", ""))),
        ("補充說明", safe_str(current_word.get("note", ""))),
    ]
    show_info_table(basic_rows)

    # 動詞資料
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
            audio_button(base_form, "🔊 原形發音", key=f"base_audio_{current_word_id}")

    # 名詞複數資料
    plural = safe_str(current_word.get("plural", ""))
    plural_rule = safe_str(current_word.get("plural_rule", ""))

    if plural or plural_rule:
        st.markdown('<div class="section-title">名詞 / 數字用法</div>', unsafe_allow_html=True)

        noun_rows = [
            ("複數形", plural),
            ("複數規則", plural_rule),
        ]
        show_info_table(noun_rows)

    # 常用用法
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
# 14. 例句：兩欄排列，每句可播放
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
    # 如果新欄位沒有例句，退回舊版 example / example_zh
    old_en = safe_str(current_word.get("example", ""))
    old_zh = safe_str(current_word.get("example_zh", ""))
    if old_en:
        examples.append((1, old_en, old_zh))

# 例句自動播放：切換單字後，自動播放第一句例句一次
if examples:
    first_example_text = examples[0][1]
    if "last_autoplay_example_id" not in st.session_state:
        st.session_state.last_autoplay_example_id = ""

    example_autoplay_id = f"{current_word_id}|{first_example_text}"

    if st.session_state.last_autoplay_example_id != example_autoplay_id:
        example_audio = get_audio_file(first_example_text)
        autoplay_audio(example_audio)
        st.session_state.last_autoplay_example_id = example_autoplay_id

example_cols = st.columns(2)

for idx, (num, en_text, zh_text) in enumerate(examples):
    with example_cols[idx % 2]:
        # 注意：
        # 不要用「先開 <div>、中間放 st.button、最後再關 </div>」的寫法。
        # Streamlit 會把 HTML 和按鈕拆成不同區塊，導致畫面出現空白框。
        # 這裡改成把英文與中文放在同一段 HTML 裡，播放按鈕另外放在下面。
        example_html = f"""
        <div class="example-card">
            <div class="example-en">{num}. {html.escape(en_text)}</div>
            <div class="example-zh">{html.escape(zh_text)}</div>
        </div>
        """
        st.markdown(example_html, unsafe_allow_html=True)
        audio_button(en_text, f"🔊 播放例句 {num}", key=f"example_audio_{current_word_id}_{num}")


# ============================================================
# 15. 目前範圍單字清單與進度表
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


with st.expander("開發備註：第二階段目前完成內容"):
    st.markdown(
        """
        第二階段目前已加入：

        1. `progress.db`：自動建立 SQLite 學習紀錄資料庫，學習紀錄就存在這個檔案裡  
        2. 每個單字會記錄：狀態、熟練度、複習次數、答對、答錯、連續答對、上次複習、下次複習  
        3. 單字卡上有四個熟悉度按鈕：忘記了、不熟、認識、很熟  
        4. 依按鈕結果自動安排下次複習日期  
        5. 側邊欄可以選「今日複習」、「未學單字」、「學習中」、「已掌握」  
        6. 切換單字卡時，單字會自動播放一次，第一句例句也會自動播放一次  

        下一步可以繼續做：

        - 第三階段：基本測驗功能  
        - 第四階段：錯題本  
        - 第五階段：每日任務  
        """
    )
