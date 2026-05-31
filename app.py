import asyncio
import hashlib
import re
from pathlib import Path

import pandas as pd
import streamlit as st

# =====================================================
# 女兒專用英文單字複習系統
# 第一階段強化版：表格化單字卡 + 單字/例句發音
# 固定讀取：words.csv
# =====================================================

st.set_page_config(
    page_title="女兒專用英文單字複習",
    page_icon="📘",
    layout="wide"
)

DATA_PATH = Path("words.csv")
AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

BASE_REQUIRED_COLUMNS = [
    "word", "meaning", "pos", "base_form", "past", "past_participle",
    "present_participle", "transitivity", "plural", "plural_rule",
    "grade", "semester", "lesson", "tags", "note"
]


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_pos_en(pos_text: str) -> str:
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
    return text


def normalize_pos_zh(pos_text: str) -> str:
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
    return clean_text(pos_text) or "未分類"


def default_pos_note(pos_en: str, pos_zh: str) -> str:
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


@st.cache_data
def load_words() -> pd.DataFrame:
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請把 words.csv 和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]

    missing = [c for c in BASE_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        st.error("words.csv 缺少欄位：" + "、".join(missing))
        return pd.DataFrame()

    for col in df.columns:
        df[col] = df[col].map(clean_text)

    # 相容舊版 words.csv：如果沒有新版欄位，就自動補上
    if "pos_en" not in df.columns:
        df["pos_en"] = df["pos"].map(normalize_pos_en)
    if "pos_zh" not in df.columns:
        df["pos_zh"] = df["pos"].map(normalize_pos_zh)
    if "pos_note" not in df.columns:
        df["pos_note"] = df.apply(lambda r: default_pos_note(r["pos_en"], r["pos_zh"]), axis=1)
    if "required_prepositions" not in df.columns:
        df["required_prepositions"] = ""
    if "usage_patterns" not in df.columns:
        df["usage_patterns"] = ""

    # 相容舊版單一例句欄位
    if "example_1" not in df.columns and "example" in df.columns:
        df["example_1"] = df["example"]
    if "example_zh_1" not in df.columns and "example_zh" in df.columns:
        df["example_zh_1"] = df["example_zh"]
    for i in range(1, 6):
        if f"example_{i}" not in df.columns:
            df[f"example_{i}"] = ""
        if f"example_zh_{i}" not in df.columns:
            df[f"example_zh_{i}"] = ""

    return df


def option_list(df: pd.DataFrame, col: str):
    values = sorted([v for v in df[col].dropna().unique().tolist() if clean_text(v)])
    return ["全部"] + values


def contains_any_column(df: pd.DataFrame, keyword: str, cols: list[str]) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    for col in cols:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(keyword, case=False, na=False, regex=False)
    return mask


def audio_filename(text: str) -> Path:
    key = hashlib.md5(text.encode("utf-8")).hexdigest()
    return AUDIO_DIR / f"{key}.mp3"


async def _make_audio_async(text: str, filename: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice="en-US-AriaNeural", rate="-10%")
    await communicate.save(str(filename))


def make_audio(text: str) -> Path | None:
    text = clean_text(text)
    if not text:
        return None
    filename = audio_filename(text)
    if filename.exists() and filename.stat().st_size > 0:
        return filename
    try:
        asyncio.run(_make_audio_async(text, filename))
        return filename
    except RuntimeError:
        # 某些環境已有 event loop，改用新 loop
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_make_audio_async(text, filename))
            return filename
        finally:
            loop.close()
    except ModuleNotFoundError:
        st.warning("尚未安裝 edge-tts，請在 requirements.txt 加上 edge-tts 後重新部署。")
        return None
    except Exception as e:
        st.warning(f"產生發音失敗：{e}")
        return None


def speak_button(text: str, label: str, key: str):
    if st.button(label, key=key, use_container_width=True):
        audio_path = make_audio(text)
        if audio_path and audio_path.exists():
            st.audio(audio_path.read_bytes(), format="audio/mp3")


def info_table(rows: list[tuple[str, str]], columns: int = 2):
    rows = [(a, clean_text(b)) for a, b in rows if clean_text(b)]
    if not rows:
        return

    # 兩欄表格：每列可放兩組「標題 / 內容」
    html_rows = []
    for i in range(0, len(rows), columns):
        chunk = rows[i:i + columns]
        cells = []
        for label, value in chunk:
            safe_label = str(label)
            safe_value = str(value).replace(";", "； ")
            cells.append(f"<td class='label'>{safe_label}</td><td>{safe_value}</td>")
        while len(chunk) < columns:
            cells.append("<td class='label'></td><td></td>")
            chunk.append(("", ""))
        html_rows.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        "<table class='info-table'>" + "".join(html_rows) + "</table>",
        unsafe_allow_html=True
    )


def section_title(text: str):
    st.markdown(f"<div class='section-title'>{text}</div>", unsafe_allow_html=True)


# =====================================================
# CSS：縮小內標題、讓單字卡更像資料表
# =====================================================
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
# 讀取資料
# =====================================================
words_df = load_words()

st.title("📘 女兒專用英文單字複習")
st.caption("第一階段強化版：表格化單字卡 + 單字與例句發音")

if words_df.empty:
    st.stop()

# =====================================================
# 側邊欄：範圍篩選
# =====================================================
st.sidebar.header("📚 選擇學習範圍")

filtered_df = words_df.copy()

selected_grade = st.sidebar.selectbox("年級", option_list(filtered_df, "grade"))
if selected_grade != "全部":
    filtered_df = filtered_df[filtered_df["grade"] == selected_grade]

selected_semester = st.sidebar.selectbox("學期", option_list(filtered_df, "semester"))
if selected_semester != "全部":
    filtered_df = filtered_df[filtered_df["semester"] == selected_semester]

selected_lesson = st.sidebar.selectbox("課次", option_list(filtered_df, "lesson"))
if selected_lesson != "全部":
    filtered_df = filtered_df[filtered_df["lesson"] == selected_lesson]

selected_pos = st.sidebar.selectbox("詞性", option_list(filtered_df, "pos_zh"))
if selected_pos != "全部":
    filtered_df = filtered_df[filtered_df["pos_zh"] == selected_pos]

keyword = st.sidebar.text_input("搜尋單字、中文、例句、用法或標籤")
if keyword.strip():
    kw = keyword.strip()
    search_cols = [
        "word", "meaning", "pos", "pos_zh", "pos_note", "base_form",
        "past", "past_participle", "present_participle", "transitivity",
        "plural", "plural_rule", "required_prepositions", "usage_patterns",
        "example_1", "example_zh_1", "example_2", "example_zh_2",
        "example_3", "example_zh_3", "example_4", "example_zh_4",
        "example_5", "example_zh_5", "tags", "note"
    ]
    filtered_df = filtered_df[contains_any_column(filtered_df, kw, search_cols)]

# =====================================================
# 主畫面：摘要與單字卡
# =====================================================
st.markdown(
    f"目前範圍：**{selected_grade}** / **{selected_semester}** / **{selected_lesson}** / **{selected_pos}**　　"
    f"共 **{len(filtered_df)}** 個單字"
)

if filtered_df.empty:
    st.warning("這個範圍目前沒有單字，請調整篩選條件。")
    st.stop()

filtered_df = filtered_df.reset_index(drop=True)
filter_key = f"{selected_grade}|{selected_semester}|{selected_lesson}|{selected_pos}|{keyword}"
if "last_filter_key" not in st.session_state:
    st.session_state.last_filter_key = filter_key
if st.session_state.last_filter_key != filter_key:
    st.session_state.card_index = 0
    st.session_state.last_filter_key = filter_key
if "card_index" not in st.session_state:
    st.session_state.card_index = 0
if st.session_state.card_index >= len(filtered_df):
    st.session_state.card_index = 0

current = filtered_df.iloc[st.session_state.card_index]

word = clean_text(current.get("word", ""))
meaning = clean_text(current.get("meaning", ""))
pos = clean_text(current.get("pos", ""))
pos_en = clean_text(current.get("pos_en", ""))
pos_zh = clean_text(current.get("pos_zh", ""))
pos_note = clean_text(current.get("pos_note", ""))
base_form = clean_text(current.get("base_form", word)) or word

st.divider()
left, right = st.columns([1.05, 1.6], vertical_alignment="top")

with left:
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
    speak_button(word, "🔊 單字發音", f"word_audio_{st.session_state.card_index}_{word}")

    if pos_en == "verb" and base_form and base_form != word:
        speak_button(base_form, "🔊 原形發音", f"base_audio_{st.session_state.card_index}_{base_form}")

    st.write(f"第 {st.session_state.card_index + 1} / {len(filtered_df)} 個")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⬅️ 上一個", use_container_width=True):
            st.session_state.card_index = (st.session_state.card_index - 1) % len(filtered_df)
            st.rerun()
    with c2:
        if st.button("下一個 ➡️", use_container_width=True):
            st.session_state.card_index = (st.session_state.card_index + 1) % len(filtered_df)
            st.rerun()

with right:
    section_title("基本資料")
    info_table([
        ("詞性", pos or pos_zh),
        ("詞性說明", pos_note),
        ("年級", current.get("grade", "")),
        ("課次", current.get("lesson", "")),
    ])

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

    plural = clean_text(current.get("plural", ""))
    plural_rule = clean_text(current.get("plural_rule", ""))
    if plural or plural_rule:
        section_title("名詞複數")
        info_table([
            ("複數形", plural),
            ("複數規則", plural_rule),
        ])

    required_prepositions = clean_text(current.get("required_prepositions", ""))
    usage_patterns = clean_text(current.get("usage_patterns", ""))
    if required_prepositions or usage_patterns:
        section_title("常用用法")
        info_table([
            ("搭配介系詞", required_prepositions),
            ("常用句型", usage_patterns),
        ], columns=1)

# 例句區：用兩欄排版，減少右方空白
section_title("例句與發音")
examples = []
for i in range(1, 6):
    ex = clean_text(current.get(f"example_{i}", ""))
    ex_zh = clean_text(current.get(f"example_zh_{i}", ""))
    if ex:
        examples.append((i, ex, ex_zh))

if not examples:
    st.write("目前尚未建立例句。")
else:
    for idx in range(0, len(examples), 2):
        cols = st.columns(2)
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
                speak_button(ex, "🔊 例句發音", f"example_audio_{st.session_state.card_index}_{i}")

section_title("補充")
info_table([
    ("標籤", current.get("tags", "")),
    ("補充說明", current.get("note", "")),
], columns=1)

with st.expander("查看目前範圍的單字清單"):
    list_cols = [
        "word", "meaning", "pos", "base_form", "past", "past_participle",
        "present_participle", "transitivity", "plural", "plural_rule",
        "required_prepositions", "usage_patterns", "grade", "semester", "lesson", "tags", "note"
    ]
    available_cols = [c for c in list_cols if c in filtered_df.columns]
    st.dataframe(filtered_df[available_cols], use_container_width=True, hide_index=True)

st.caption("下一階段可加入：認識／不熟／忘記了、SQLite 學習紀錄、記憶曲線排程。")
