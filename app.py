# =====================================================
# 女兒專用英文單字複習系統
# app_v5 中文註解版
# -----------------------------------------------------
# 這個程式使用 Streamlit 製作網頁介面。
# 目前功能：
# 1. 固定讀取 words.csv
# 2. 依年級、學期、課次、詞性篩選單字
# 3. 顯示單字卡
# 4. 顯示動詞三態、現在分詞、及物/不及物、複數規則、常用用法
# 5. 使用 edge-tts 產生單字與例句發音 mp3
# 6. 將發音檔快取在 audio_cache 資料夾，避免重複產生
# =====================================================

# asyncio：處理非同步工作。edge-tts 產生語音時會用到。
import asyncio

# hashlib：用文字產生固定的雜湊值，讓每一句話都能對應到唯一 mp3 檔名。
import hashlib

# pathlib.Path：比一般字串路徑更好管理檔案與資料夾。
from pathlib import Path

# pandas：讀取與處理 CSV 表格資料。
import pandas as pd

# streamlit：建立網頁介面。
import streamlit as st


# =====================================================
# 一、Streamlit 網頁基本設定
# =====================================================
# st.set_page_config 通常要放在程式最前面。
# page_title：瀏覽器分頁標題。
# page_icon：瀏覽器分頁小圖示。
# layout="wide"：寬版版面，比較適合 iPad 橫向或電腦。
st.set_page_config(
    page_title="女兒專用英文單字複習",
    page_icon="📘",
    layout="wide"
)


# =====================================================
# 二、檔案與資料夾路徑設定
# =====================================================
# 單字表固定讀取 words.csv。
# 所以 GitHub / Streamlit Cloud 裡要有 app.py 和 words.csv。
DATA_PATH = Path("words.csv")

# 發音檔快取資料夾。
# 產生過的單字或例句 mp3 會存在這裡，下次不用重新產生。
AUDIO_DIR = Path("audio_cache")

# 如果 audio_cache 資料夾不存在，就自動建立。
# exist_ok=True 表示資料夾已存在也不會報錯。
AUDIO_DIR.mkdir(exist_ok=True)


# =====================================================
# 三、CSV 必要欄位設定
# =====================================================
# 程式至少需要這些欄位才能正常顯示單字卡。
# 如果 words.csv 缺少其中任何一欄，程式會顯示錯誤。
BASE_REQUIRED_COLUMNS = [
    "word", "meaning", "pos", "base_form", "past", "past_participle",
    "present_participle", "transitivity", "plural", "plural_rule",
    "grade", "semester", "lesson", "tags", "note"
]


# =====================================================
# 四、小工具函式：清理文字
# =====================================================
def clean_text(value) -> str:
    """
    把 CSV 讀進來的資料整理成乾淨文字。

    為什麼需要這個函式？
    1. CSV 空白欄位在 pandas 裡可能變成 NaN。
    2. 有些資料前後可能多空白。
    3. Streamlit 顯示 NaN 會不好看。

    回傳：
    - 如果是空值，回傳空字串 ""
    - 否則轉成字串並去掉前後空白
    """
    if pd.isna(value):
        return ""
    return str(value).strip()


# =====================================================
# 五、小工具函式：把詞性轉成程式判斷用英文代碼
# =====================================================
def normalize_pos_en(pos_text: str) -> str:
    """
    將詞性欄位轉成程式容易判斷的英文代碼。

    例如：
    - verb（動詞） → verb
    - 動詞 → verb
    - noun（名詞） → noun
    - adjective（形容詞） → adjective

    這樣後面就可以用：
        if pos_en == "verb":
    來判斷是不是動詞。
    """
    text = clean_text(pos_text).lower()

    if "verb" in text or "動詞" in text:
        return "verb"
    if "noun" in text or "名詞" in text:
        return "noun"
    if "adjective" in text or "adj" in text or "形容詞" in text:
        return "adjective"
    if "adverb" in text or "adv" in text or "副詞" in text:
        return "adverb"
    if "pronoun" in text or "代名詞" in text:
        return "pronoun"

    # 如果都不符合，就回傳清理後的原始文字。
    return text


# =====================================================
# 六、小工具函式：把詞性轉成中文顯示
# =====================================================
def normalize_pos_zh(pos_text: str) -> str:
    """
    將詞性欄位轉成女兒比較看得懂的中文。

    例如：
    - verb → 動詞
    - noun → 名詞
    - adjective → 形容詞
    - adverb → 副詞
    """
    text = clean_text(pos_text).lower()

    if "verb" in text or "動詞" in text:
        return "動詞"
    if "noun" in text or "名詞" in text:
        return "名詞"
    if "adjective" in text or "adj" in text or "形容詞" in text:
        return "形容詞"
    if "adverb" in text or "adv" in text or "副詞" in text:
        return "副詞"
    if "pronoun" in text or "代名詞" in text:
        return "代名詞"
    if "number" in text or "數字" in text:
        return "數字"

    # 如果無法判斷，就顯示原本內容；如果原本也空白，就顯示未分類。
    return clean_text(pos_text) or "未分類"


# =====================================================
# 七、小工具函式：自動產生詞性說明
# =====================================================
def default_pos_note(pos_en: str, pos_zh: str) -> str:
    """
    如果 words.csv 沒有 pos_note 欄位，程式會自動產生簡單中文說明。
    這是為了相容舊版單字表。
    """
    if pos_en == "verb":
        return "表示動作或狀態，例如 be 表示「是、在」。"
    if pos_en == "noun":
        return "表示人、事、物或概念。"
    if pos_en == "adjective":
        return "用來形容名詞，例如 my book、happy boy。"
    if pos_en == "adverb":
        return "用來修飾動詞、形容詞或整個句子。"
    if pos_en == "pronoun":
        return "用來代替名詞。"
    if "數字" in pos_zh:
        return "可表示數字，也可當名詞使用。"
    return ""


# =====================================================
# 八、讀取 words.csv
# =====================================================
@st.cache_data
def load_words() -> pd.DataFrame:
    """
    讀取 words.csv 並整理資料。

    @st.cache_data 的作用：
    Streamlit 每次互動都會重新執行整個 app.py。
    如果每次都重新讀 CSV，資料多時會變慢。
    加上 @st.cache_data 後，只要 words.csv 沒變，Streamlit 會使用快取結果。
    """

    # 檢查 words.csv 是否存在。
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請把 words.csv 和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    # 讀取 CSV。
    # dtype=str：全部欄位都用文字讀取，避免數字或空白被自動轉型。
    # fillna("")：把空值補成空字串。
    df = pd.read_csv(DATA_PATH, dtype=str).fillna("")

    # 清理欄位名稱前後空白。
    df.columns = [c.strip() for c in df.columns]

    # 檢查必要欄位是否存在。
    missing = [c for c in BASE_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        st.error("words.csv 缺少欄位：" + "、".join(missing))
        return pd.DataFrame()

    # 清理每一欄的文字內容。
    for col in df.columns:
        df[col] = df[col].map(clean_text)

    # -------------------------------------------------
    # 相容舊版 words.csv：如果缺少新版欄位，就自動補上。
    # -------------------------------------------------

    # pos_en：給程式判斷用。
    if "pos_en" not in df.columns:
        df["pos_en"] = df["pos"].map(normalize_pos_en)

    # pos_zh：給使用者看。
    if "pos_zh" not in df.columns:
        df["pos_zh"] = df["pos"].map(normalize_pos_zh)

    # pos_note：詞性說明。
    if "pos_note" not in df.columns:
        df["pos_note"] = df.apply(lambda r: default_pos_note(r["pos_en"], r["pos_zh"]), axis=1)

    # required_prepositions：固定搭配介系詞，例如 afraid of、listen to。
    if "required_prepositions" not in df.columns:
        df["required_prepositions"] = ""

    # usage_patterns：常用句型，例如 How old are you? / What about ...?
    if "usage_patterns" not in df.columns:
        df["usage_patterns"] = ""

    # -------------------------------------------------
    # 相容舊版單一例句欄位。
    # 舊版可能只有 example / example_zh。
    # 新版支援 example_1 ~ example_5。
    # -------------------------------------------------
    if "example_1" not in df.columns and "example" in df.columns:
        df["example_1"] = df["example"]
    if "example_zh_1" not in df.columns and "example_zh" in df.columns:
        df["example_zh_1"] = df["example_zh"]

    # 確保 example_1 ~ example_5 和 example_zh_1 ~ example_zh_5 都存在。
    for i in range(1, 6):
        if f"example_{i}" not in df.columns:
            df[f"example_{i}"] = ""
        if f"example_zh_{i}" not in df.columns:
            df[f"example_zh_{i}"] = ""

    return df


# =====================================================
# 九、小工具函式：產生下拉選單選項
# =====================================================
def option_list(df: pd.DataFrame, col: str):
    """
    從某個欄位抓出不重複的值，做成下拉選單選項。

    例如 grade 欄位有：七年級、八年級
    回傳：全部、七年級、八年級
    """
    values = sorted([v for v in df[col].dropna().unique().tolist() if clean_text(v)])
    return ["全部"] + values


# =====================================================
# 十、小工具函式：跨多欄搜尋
# =====================================================
def contains_any_column(df: pd.DataFrame, keyword: str, cols: list[str]) -> pd.Series:
    """
    在多個欄位中搜尋關鍵字。

    回傳一個 True/False 序列，表示每一列是否符合搜尋。

    regex=False：把關鍵字當一般文字，不當正規表示式，避免特殊符號造成錯誤。
    """
    mask = pd.Series(False, index=df.index)
    for col in cols:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(keyword, case=False, na=False, regex=False)
    return mask


# =====================================================
# 十一、發音功能：產生音檔檔名
# =====================================================
def audio_filename(text: str) -> Path:
    """
    將一段英文文字轉成固定 mp3 檔名。

    為什麼不用原本文字當檔名？
    因為例句可能有空白、標點符號、問號，當檔名可能不穩定。
    所以用 MD5 雜湊產生安全檔名。
    """
    key = hashlib.md5(text.encode("utf-8")).hexdigest()
    return AUDIO_DIR / f"{key}.mp3"


# =====================================================
# 十二、發音功能：非同步產生 mp3
# =====================================================
async def _make_audio_async(text: str, filename: Path):
    """
    使用 edge-tts 產生語音檔。

    edge-tts 是非同步套件，所以這個函式要加 async。
    voice="en-US-AriaNeural"：使用美式英文女聲。
    rate="-10%"：稍微放慢速度，適合國中生。
    """
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice="en-US-AriaNeural", rate="-10%")
    await communicate.save(str(filename))


# =====================================================
# 十三、發音功能：產生或讀取快取音檔
# =====================================================
def make_audio(text: str) -> Path | None:
    """
    產生英文發音 mp3，並回傳檔案路徑。

    流程：
    1. 清理文字。
    2. 如果文字為空，就不產生。
    3. 算出快取檔名。
    4. 如果 mp3 已存在，就直接回傳。
    5. 如果不存在，就用 edge-tts 產生。
    """
    text = clean_text(text)
    if not text:
        return None

    filename = audio_filename(text)

    # 如果音檔已存在，而且檔案大小大於 0，就直接使用，不重新產生。
    if filename.exists() and filename.stat().st_size > 0:
        return filename

    try:
        # 一般情況：直接執行非同步函式。
        asyncio.run(_make_audio_async(text, filename))
        return filename

    except RuntimeError:
        # 某些環境已經有 event loop，asyncio.run 可能會報錯。
        # 這時改用新的 event loop 執行。
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_make_audio_async(text, filename))
            return filename
        finally:
            loop.close()

    except ModuleNotFoundError:
        # requirements.txt 沒有 edge-tts 時會出現這個錯誤。
        st.warning("尚未安裝 edge-tts，請在 requirements.txt 加上 edge-tts 後重新部署。")
        return None

    except Exception as e:
        # 其他錯誤，例如網路問題、TTS 服務暫時失敗等。
        st.warning(f"產生發音失敗：{e}")
        return None


# =====================================================
# 十四、發音按鈕元件
# =====================================================
def speak_button(text: str, label: str, key: str):
    """
    建立一個發音按鈕。

    text：要朗讀的英文文字。
    label：按鈕文字，例如「🔊 單字發音」。
    key：Streamlit 按鈕的唯一識別碼。

    注意：
    Streamlit 同一頁如果有很多按鈕，每個按鈕的 key 必須不同。
    """
    if st.button(label, key=key, use_container_width=True):
        audio_path = make_audio(text)
        if audio_path and audio_path.exists():
            # st.audio 可以播放音檔。
            # 這裡用 read_bytes() 讀入音檔內容，部署時比較穩定。
            st.audio(audio_path.read_bytes(), format="audio/mp3")


# =====================================================
# 十五、表格顯示元件
# =====================================================
def info_table(rows: list[tuple[str, str]], columns: int = 2):
    """
    用 HTML 表格顯示資料。

    rows：資料列，格式是 [(標題, 內容), (標題, 內容)]
    columns：一列要放幾組資料。

    例如 columns=2 時，一列會放：
    標題 / 內容 / 標題 / 內容

    這樣可以避免畫面右邊太空。
    """

    # 移除內容空白的項目。
    rows = [(a, clean_text(b)) for a, b in rows if clean_text(b)]
    if not rows:
        return

    html_rows = []

    # 每 columns 個資料合成一列。
    for i in range(0, len(rows), columns):
        chunk = rows[i:i + columns]
        cells = []

        for label, value in chunk:
            safe_label = str(label)

            # 把英文分號 ; 換成中文分號與空格，比較好閱讀。
            safe_value = str(value).replace(";", "； ")
            cells.append(f"<td class='label'>{safe_label}</td><td>{safe_value}</td>")

        # 如果最後一列不足 columns 組，補空白欄位，避免表格歪掉。
        while len(chunk) < columns:
            cells.append("<td class='label'></td><td></td>")
            chunk.append(("", ""))

        html_rows.append("<tr>" + "".join(cells) + "</tr>")

    # unsafe_allow_html=True：允許 Streamlit 顯示自訂 HTML。
    st.markdown(
        "<table class='info-table'>" + "".join(html_rows) + "</table>",
        unsafe_allow_html=True
    )


# =====================================================
# 十六、小標題元件
# =====================================================
def section_title(text: str):
    """
    顯示小區塊標題。
    這裡用自訂 CSS class，讓標題比 Streamlit 預設標題小一點。
    """
    st.markdown(f"<div class='section-title'>{text}</div>", unsafe_allow_html=True)


# =====================================================
# 十七、CSS 版面設定
# =====================================================
# Streamlit 可以用 st.markdown 插入 CSS。
# 這裡主要用來調整：
# - 頁面寬度
# - 標題大小
# - 單字卡樣式
# - 表格樣式
# - 例句區塊樣式
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        max-width: 1180px;
    }
    h1 {
        font-size: 2rem !important;
    }
    h2, h3 {
        font-size: 1.15rem !important;
        margin-top: 0.6rem !important;
        margin-bottom: 0.35rem !important;
    }
    .section-title {
        font-size: 1.15rem;
        font-weight: 800;
        margin-top: 1rem;
        margin-bottom: 0.45rem;
        border-left: 5px solid #8aa4ff;
        padding-left: 0.55rem;
    }
    .word-card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 18px;
        padding: 1.1rem 1.25rem;
        margin: 0.6rem 0 0.8rem 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    }
    .word-title {
        font-size: 2.6rem;
        font-weight: 900;
        line-height: 1.1;
        margin-bottom: 0.2rem;
    }
    .meaning-title {
        font-size: 1.25rem;
        opacity: 0.85;
    }
    .small-note {
        font-size: 0.95rem;
        opacity: 0.75;
        margin-top: 0.25rem;
    }
    .info-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 0.45rem;
        font-size: 0.98rem;
    }
    .info-table td {
        border: 1px solid rgba(128,128,128,0.22);
        padding: 0.5rem 0.65rem;
        vertical-align: top;
    }
    .info-table .label {
        width: 16%;
        font-weight: 800;
        background: rgba(128,128,128,0.10);
        white-space: nowrap;
    }
    .example-box {
        border: 1px solid rgba(128,128,128,0.22);
        border-radius: 12px;
        padding: 0.65rem 0.8rem;
        margin-bottom: 0.5rem;
    }
    .example-en {
        font-weight: 800;
        font-size: 1.02rem;
    }
    .example-zh {
        opacity: 0.75;
        margin-top: 0.18rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =====================================================
# 十八、讀取單字資料
# =====================================================
# 呼叫前面的 load_words() 函式。
# 如果讀取成功，words_df 會是一個 pandas DataFrame。
words_df = load_words()

# 頁面主標題與說明文字。
st.title("📘 女兒專用英文單字複習")
st.caption("第一階段強化版：表格化單字卡 + 單字與例句發音")

# 如果資料是空的，停止執行後面的程式。
if words_df.empty:
    st.stop()


# =====================================================
# 十九、側邊欄：範圍篩選
# =====================================================
# st.sidebar 代表左側邊欄。
st.sidebar.header("📚 選擇學習範圍")

# 從完整單字表複製一份，後面會逐步篩選。
filtered_df = words_df.copy()

# 年級篩選。
selected_grade = st.sidebar.selectbox("年級", option_list(filtered_df, "grade"))
if selected_grade != "全部":
    filtered_df = filtered_df[filtered_df["grade"] == selected_grade]

# 學期篩選。注意：選項會根據前面的年級篩選結果產生。
selected_semester = st.sidebar.selectbox("學期", option_list(filtered_df, "semester"))
if selected_semester != "全部":
    filtered_df = filtered_df[filtered_df["semester"] == selected_semester]

# 課次篩選。
selected_lesson = st.sidebar.selectbox("課次", option_list(filtered_df, "lesson"))
if selected_lesson != "全部":
    filtered_df = filtered_df[filtered_df["lesson"] == selected_lesson]

# 詞性篩選。這裡使用 pos_zh，所以女兒看到的是中文詞性。
selected_pos = st.sidebar.selectbox("詞性", option_list(filtered_df, "pos_zh"))
if selected_pos != "全部":
    filtered_df = filtered_df[filtered_df["pos_zh"] == selected_pos]

# 關鍵字搜尋。
keyword = st.sidebar.text_input("搜尋單字、中文、例句、用法或標籤")
if keyword.strip():
    kw = keyword.strip()

    # 設定要搜尋的欄位。
    search_cols = [
        "word", "meaning", "pos", "pos_zh", "pos_note", "base_form",
        "past", "past_participle", "present_participle", "transitivity",
        "plural", "plural_rule", "required_prepositions", "usage_patterns",
        "example_1", "example_zh_1", "example_2", "example_zh_2",
        "example_3", "example_zh_3", "example_4", "example_zh_4",
        "example_5", "example_zh_5", "tags", "note"
    ]

    # 只留下任一欄位包含關鍵字的資料。
    filtered_df = filtered_df[contains_any_column(filtered_df, kw, search_cols)]


# =====================================================
# 二十、主畫面：篩選摘要
# =====================================================
st.markdown(
    f"目前範圍：**{selected_grade}** / **{selected_semester}** / **{selected_lesson}** / **{selected_pos}**　　"
    f"共 **{len(filtered_df)}** 個單字"
)

# 如果篩選後沒有資料，就提示並停止。
if filtered_df.empty:
    st.warning("這個範圍目前沒有單字，請調整篩選條件。")
    st.stop()

# 重設索引，讓第 0、1、2 筆資料可以對應單字卡順序。
filtered_df = filtered_df.reset_index(drop=True)


# =====================================================
# 二十一、使用 session_state 記住目前卡片位置
# =====================================================
# Streamlit 每次按按鈕都會重新執行整個程式。
# 如果不用 st.session_state，card_index 每次都會變回 0。
# 所以用 st.session_state.card_index 記住目前看到第幾張卡。

# filter_key 用來判斷篩選條件是否改變。
filter_key = f"{selected_grade}|{selected_semester}|{selected_lesson}|{selected_pos}|{keyword}"

# 第一次執行時建立 last_filter_key。
if "last_filter_key" not in st.session_state:
    st.session_state.last_filter_key = filter_key

# 如果篩選條件改變，就回到第一張單字卡。
if st.session_state.last_filter_key != filter_key:
    st.session_state.card_index = 0
    st.session_state.last_filter_key = filter_key

# 第一次執行時建立 card_index。
if "card_index" not in st.session_state:
    st.session_state.card_index = 0

# 如果目前索引超過篩選後資料筆數，就回到第一張。
if st.session_state.card_index >= len(filtered_df):
    st.session_state.card_index = 0


# =====================================================
# 二十二、取得目前單字資料
# =====================================================
current = filtered_df.iloc[st.session_state.card_index]

# 取出常用欄位，先用 clean_text 清理。
word = clean_text(current.get("word", ""))
meaning = clean_text(current.get("meaning", ""))
pos = clean_text(current.get("pos", ""))
pos_en = clean_text(current.get("pos_en", ""))
pos_zh = clean_text(current.get("pos_zh", ""))
pos_note = clean_text(current.get("pos_note", ""))

# base_form 是原形。如果空白，就用 word 當原形。
base_form = clean_text(current.get("base_form", word)) or word


# =====================================================
# 二十三、主畫面：左右欄版面
# =====================================================
# st.columns 可以把畫面分成多欄。
# [1.05, 1.6] 表示左欄稍窄、右欄較寬。
st.divider()
left, right = st.columns([1.05, 1.6], vertical_alignment="top")


# =====================================================
# 二十四、左欄：單字卡與上一個/下一個
# =====================================================
with left:
    # 用 HTML 做單字卡外觀。
    st.markdown(
        f"""
        <div class='word-card'>
            <div class='word-title'>{word}</div>
            <div class='meaning-title'>{meaning}</div>
            <div class='small-note'>{pos or pos_zh}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 單字發音按鈕。
    speak_button(word, "🔊 單字發音", f"word_audio_{st.session_state.card_index}_{word}")

    # 如果是動詞，且原形和目前單字不同，就另外提供原形發音。
    # 例如 am / are / is 的原形都是 be。
    if pos_en == "verb" and base_form and base_form != word:
        speak_button(base_form, "🔊 原形發音", f"base_audio_{st.session_state.card_index}_{base_form}")

    # 顯示目前第幾張。
    st.write(f"第 {st.session_state.card_index + 1} / {len(filtered_df)} 個")

    # 上一個 / 下一個按鈕並排顯示。
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⬅️ 上一個", use_container_width=True):
            # 使用 % 可以做到循環：第一張按上一個會跳到最後一張。
            st.session_state.card_index = (st.session_state.card_index - 1) % len(filtered_df)
            st.rerun()

    with c2:
        if st.button("下一個 ➡️", use_container_width=True):
            # 最後一張按下一個會跳回第一張。
            st.session_state.card_index = (st.session_state.card_index + 1) % len(filtered_df)
            st.rerun()


# =====================================================
# 二十五、右欄：基本資料、動詞資料、用法
# =====================================================
with right:
    # 基本資料表。
    section_title("基本資料")
    info_table([
        ("詞性", pos or pos_zh),
        ("詞性說明", pos_note),
        ("年級", current.get("grade", "")),
        ("課次", current.get("lesson", "")),
    ])

    # 如果是動詞，就顯示動詞資料。
    if pos_en == "verb":
        section_title("動詞資料")
        past = clean_text(current.get("past", ""))
        past_participle = clean_text(current.get("past_participle", ""))
        present_participle = clean_text(current.get("present_participle", ""))

        info_table([
            ("原形", base_form),
            ("過去式", past),
            ("過去分詞", past_participle),
            ("現在分詞", present_participle),
            ("及物／不及物", current.get("transitivity", "")),
        ])

    # 名詞複數資料。不是每個詞都有，所以有資料才顯示。
    plural = clean_text(current.get("plural", ""))
    plural_rule = clean_text(current.get("plural_rule", ""))
    if plural or plural_rule:
        section_title("名詞複數")
        info_table([
            ("複數形", plural),
            ("複數規則", plural_rule),
        ])

    # 常用介系詞和句型。
    required_prepositions = clean_text(current.get("required_prepositions", ""))
    usage_patterns = clean_text(current.get("usage_patterns", ""))
    if required_prepositions or usage_patterns:
        section_title("常用用法")
        info_table([
            ("搭配介系詞", required_prepositions),
            ("常用句型", usage_patterns),
        ], columns=1)


# =====================================================
# 二十六、例句區：兩欄排列 + 例句發音
# =====================================================
section_title("例句與發音")

# 收集目前單字的例句。
examples = []
for i in range(1, 6):
    ex = clean_text(current.get(f"example_{i}", ""))
    ex_zh = clean_text(current.get(f"example_zh_{i}", ""))
    if ex:
        examples.append((i, ex, ex_zh))

if not examples:
    st.write("目前尚未建立例句。")
else:
    # 每兩個例句一排。
    for idx in range(0, len(examples), 2):
        cols = st.columns(2)

        # zip(cols, examples[idx:idx + 2])：把欄位和例句配對。
        for col, item in zip(cols, examples[idx:idx + 2]):
            i, ex, ex_zh = item
            with col:
                st.markdown(
                    f"""
                    <div class='example-box'>
                        <div class='example-en'>{i}. {ex}</div>
                        <div class='example-zh'>{ex_zh}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # 每一句例句都有自己的發音按鈕。
                speak_button(ex, "🔊 例句發音", f"example_audio_{st.session_state.card_index}_{i}")


# =====================================================
# 二十七、補充資料
# =====================================================
section_title("補充")
info_table([
    ("標籤", current.get("tags", "")),
    ("補充說明", current.get("note", "")),
], columns=1)


# =====================================================
# 二十八、目前範圍單字清單
# =====================================================
# st.expander：可展開/收合的區塊。
with st.expander("查看目前範圍的單字清單"):
    list_cols = [
        "word", "meaning", "pos", "base_form", "past", "past_participle",
        "present_participle", "transitivity", "plural", "plural_rule",
        "required_prepositions", "usage_patterns", "grade", "semester", "lesson", "tags", "note"
    ]

    # 只顯示目前 DataFrame 裡真的存在的欄位。
    available_cols = [c for c in list_cols if c in filtered_df.columns]

    # st.dataframe：顯示互動式表格。
    # hide_index=True：隱藏左邊的索引欄。
    st.dataframe(filtered_df[available_cols], use_container_width=True, hide_index=True)


# =====================================================
# 二十九、頁尾提示
# =====================================================
st.caption("下一階段可加入：認識／不熟／忘記了、SQLite 學習紀錄、記憶曲線排程。")
