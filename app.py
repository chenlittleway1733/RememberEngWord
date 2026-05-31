import streamlit as st
import pandas as pd
from pathlib import Path

# =====================================================
# 女兒專用英文單字複習系統
# 第一階段：單字表 + 單字卡學習
# 對應資料檔：words.csv
# =====================================================

st.set_page_config(
    page_title="女兒專用英文單字複習",
    page_icon="📘",
    layout="centered"
)

DATA_PATH = Path("words.csv")

REQUIRED_COLUMNS = [
    "word", "meaning", "pos", "pos_en", "pos_zh", "pos_note",
    "base_form", "past", "past_participle", "present_participle",
    "transitivity", "plural", "plural_rule",
    "required_prepositions", "usage_patterns",
    "example_1", "example_zh_1",
    "grade", "semester", "lesson", "tags", "note"
]


def clean_text(value) -> str:
    """把 NaN、None 清成空字串，避免畫面出現 nan。"""
    if pd.isna(value):
        return ""
    return str(value).strip()


@st.cache_data
def load_words() -> pd.DataFrame:
    """讀取 words.csv，並檢查必要欄位。"""
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請把 words.csv 和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        st.error("words.csv 缺少欄位：" + "、".join(missing))
        return pd.DataFrame()

    # 清掉每個欄位前後空白
    for col in df.columns:
        df[col] = df[col].map(clean_text)

    return df


def option_list(df: pd.DataFrame, col: str):
    values = sorted([v for v in df[col].dropna().unique().tolist() if str(v).strip()])
    return ["全部"] + values


def show_if_exists(label: str, value: str):
    value = clean_text(value)
    if value:
        st.write(f"**{label}：** {value}")


def contains_any_column(df: pd.DataFrame, keyword: str, cols: list[str]) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    for col in cols:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(keyword, case=False, na=False)
    return mask


# =====================================================
# 讀取資料
# =====================================================
words_df = load_words()

st.title("📘 女兒專用英文單字複習")
st.caption("第一階段：單字表 + 單字卡學習")

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
        "word", "meaning", "pos", "pos_zh", "pos_note",
        "base_form", "past", "past_participle", "present_participle",
        "transitivity", "plural", "plural_rule",
        "required_prepositions", "usage_patterns",
        "example_1", "example_zh_1", "example_2", "example_zh_2",
        "example_3", "example_zh_3", "example_4", "example_zh_4",
        "example_5", "example_zh_5", "tags", "note"
    ]
    filtered_df = filtered_df[contains_any_column(filtered_df, kw, search_cols)]

# =====================================================
# 主畫面：範圍摘要
# =====================================================
st.subheader("目前學習範圍")
st.write(
    f"年級：**{selected_grade}**　"
    f"學期：**{selected_semester}**　"
    f"課次：**{selected_lesson}**　"
    f"詞性：**{selected_pos}**"
)
st.info(f"目前共有 {len(filtered_df)} 個單字")

if filtered_df.empty:
    st.warning("這個範圍目前沒有單字，請調整篩選條件。")
    st.stop()

# =====================================================
# 單字卡索引
# =====================================================
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

# =====================================================
# 單字卡
# =====================================================
st.divider()
st.subheader("🃏 單字卡")

word = clean_text(current["word"])
meaning = clean_text(current["meaning"])
pos = clean_text(current["pos"])
pos_en = clean_text(current["pos_en"])
pos_zh = clean_text(current["pos_zh"])
pos_note = clean_text(current["pos_note"])

st.markdown(
    f"""
    <div style="
        border: 1px solid #dddddd;
        border-radius: 18px;
        padding: 26px;
        margin-top: 12px;
        margin-bottom: 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        background-color: #ffffff;
    ">
        <h1 style="text-align:center; color:#2c3e50; margin-bottom: 6px;">
            {word}
        </h1>
        <h3 style="text-align:center; color:#555555; margin-top: 0;">
            {meaning}
        </h3>
    </div>
    """,
    unsafe_allow_html=True
)

st.write(f"**詞性：** {pos}")
if pos_note:
    st.caption(f"📌 {pos_note}")

# 動詞：顯示三態、現在分詞、及物/不及物、介系詞
if pos_en == "verb":
    st.markdown("### 動詞資料")
    show_if_exists("原形", current.get("base_form", ""))
    past = clean_text(current.get("past", ""))
    past_participle = clean_text(current.get("past_participle", ""))
    present_participle = clean_text(current.get("present_participle", ""))

    if past or past_participle or present_participle:
        st.write(
            f"**三態與現在分詞：** {clean_text(current.get('base_form', word))} / "
            f"{past or '—'} / {past_participle or '—'} / 現在分詞：{present_participle or '—'}"
        )
    show_if_exists("及物／不及物", current.get("transitivity", ""))

# 名詞或數字可當名詞：顯示複數
plural = clean_text(current.get("plural", ""))
plural_rule = clean_text(current.get("plural_rule", ""))
if plural or plural_rule:
    st.markdown("### 名詞複數")
    show_if_exists("複數形", plural)
    show_if_exists("複數規則", plural_rule)

# 常用搭配與句型
required_prepositions = clean_text(current.get("required_prepositions", ""))
usage_patterns = clean_text(current.get("usage_patterns", ""))
if required_prepositions or usage_patterns:
    st.markdown("### 常用用法")
    show_if_exists("常搭配介系詞", required_prepositions)
    show_if_exists("常用句型／用法", usage_patterns)

# 例句
st.markdown("### 例句")
example_count = 0
for i in range(1, 6):
    ex = clean_text(current.get(f"example_{i}", ""))
    ex_zh = clean_text(current.get(f"example_zh_{i}", ""))
    if ex:
        example_count += 1
        st.markdown(f"{example_count}. **{ex}**")
        if ex_zh:
            st.caption(ex_zh)

if example_count == 0:
    st.write("目前尚未建立例句。")

# 標籤與補充
st.markdown("### 補充")
show_if_exists("標籤", current.get("tags", ""))
show_if_exists("補充說明", current.get("note", ""))

# =====================================================
# 上一個 / 下一個
# =====================================================
st.divider()
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("⬅️ 上一個", use_container_width=True):
        st.session_state.card_index = (st.session_state.card_index - 1) % len(filtered_df)
        st.rerun()

with col2:
    st.markdown(
        f"<p style='text-align:center;'>第 {st.session_state.card_index + 1} / {len(filtered_df)} 個</p>",
        unsafe_allow_html=True
    )

with col3:
    if st.button("下一個 ➡️", use_container_width=True):
        st.session_state.card_index = (st.session_state.card_index + 1) % len(filtered_df)
        st.rerun()

# =====================================================
# 單字清單
# =====================================================
with st.expander("查看目前範圍的單字清單"):
    list_cols = [
        "word", "meaning", "pos", "base_form", "past", "past_participle",
        "present_participle", "transitivity", "plural", "plural_rule",
        "required_prepositions", "usage_patterns", "grade", "semester", "lesson", "tags", "note"
    ]
    available_cols = [c for c in list_cols if c in filtered_df.columns]
    st.dataframe(filtered_df[available_cols], use_container_width=True, hide_index=True)

st.caption("下一階段可加入：認識／不熟／忘記了、SQLite 學習紀錄、記憶曲線排程。")
