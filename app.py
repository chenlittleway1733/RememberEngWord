import streamlit as st
import pandas as pd
from pathlib import Path

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="國中英文單字複習",
    page_icon="📘",
    layout="centered"
)

DATA_PATH = Path("words.csv")


# =========================
# 讀取單字資料
# =========================
@st.cache_data
def load_words():
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請確認檔案和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH)

    # 避免空白值顯示成 NaN
    df = df.fillna("")

    required_columns = [
        "word", "meaning", "pos", "past", "past_participle",
        "example", "example_zh", "grade", "semester",
        "lesson", "tags", "note"
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        st.error(f"words.csv 缺少欄位：{', '.join(missing_columns)}")
        return pd.DataFrame()

    return df


words_df = load_words()

st.title("📘 國中英文單字複習")
st.caption("第一版：單字表 + 單字卡學習")

if words_df.empty:
    st.stop()


# =========================
# 側邊欄：範圍篩選
# =========================
st.sidebar.header("📚 選擇學習範圍")

grade_options = ["全部"] + sorted(words_df["grade"].unique().tolist())
selected_grade = st.sidebar.selectbox("年級", grade_options)

filtered_df = words_df.copy()

if selected_grade != "全部":
    filtered_df = filtered_df[filtered_df["grade"] == selected_grade]

semester_options = ["全部"] + sorted(filtered_df["semester"].unique().tolist())
selected_semester = st.sidebar.selectbox("學期", semester_options)

if selected_semester != "全部":
    filtered_df = filtered_df[filtered_df["semester"] == selected_semester]

lesson_options = ["全部"] + sorted(filtered_df["lesson"].unique().tolist())
selected_lesson = st.sidebar.selectbox("課次", lesson_options)

if selected_lesson != "全部":
    filtered_df = filtered_df[filtered_df["lesson"] == selected_lesson]

tag_keyword = st.sidebar.text_input("標籤關鍵字，例如：不規則動詞")

if tag_keyword.strip():
    filtered_df = filtered_df[
        filtered_df["tags"].str.contains(tag_keyword.strip(), case=False, na=False)
    ]


# =========================
# 主畫面：篩選結果
# =========================
st.subheader("目前學習範圍")

st.write(
    f"年級：**{selected_grade}**　"
    f"學期：**{selected_semester}**　"
    f"課次：**{selected_lesson}**"
)

st.info(f"目前共有 {len(filtered_df)} 個單字")

if filtered_df.empty:
    st.warning("這個範圍目前沒有單字，請調整篩選條件。")
    st.stop()


# =========================
# 單字卡索引
# =========================
if "card_index" not in st.session_state:
    st.session_state.card_index = 0

# 如果篩選後單字數變少，避免索引超出範圍
if st.session_state.card_index >= len(filtered_df):
    st.session_state.card_index = 0

filtered_df = filtered_df.reset_index(drop=True)
current_word = filtered_df.iloc[st.session_state.card_index]


# =========================
# 單字卡
# =========================
st.divider()

st.subheader("🃏 單字卡")

st.markdown(
    f"""
    <div style="
        border: 1px solid #ddd;
        border-radius: 16px;
        padding: 24px;
        margin-top: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        background-color: #ffffff;
    ">
        <h1 style="text-align:center; color:#2c3e50;">
            {current_word['word']}
        </h1>
        <h3 style="text-align:center; color:#555;">
            {current_word['meaning']}
        </h3>
    </div>
    """,
    unsafe_allow_html=True
)

st.write(f"**詞性：** {current_word['pos']}")

if current_word["pos"] == "verb":
    st.write(
        f"**三態：** "
        f"{current_word['word']} / "
        f"{current_word['past']} / "
        f"{current_word['past_participle']}"
    )

if current_word["example"]:
    st.write("**例句：**")
    st.write(current_word["example"])

if current_word["example_zh"]:
    st.write("**例句中文：**")
    st.write(current_word["example_zh"])

if current_word["tags"]:
    st.write(f"**標籤：** {current_word['tags']}")

if current_word["note"]:
    st.write(f"**補充說明：** {current_word['note']}")


# =========================
# 上一張 / 下一張
# =========================
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("⬅️ 上一個"):
        st.session_state.card_index -= 1
        if st.session_state.card_index < 0:
            st.session_state.card_index = len(filtered_df) - 1
        st.rerun()

with col2:
    st.write(
        f"第 {st.session_state.card_index + 1} / {len(filtered_df)} 個"
    )

with col3:
    if st.button("下一個 ➡️"):
        st.session_state.card_index += 1
        if st.session_state.card_index >= len(filtered_df):
            st.session_state.card_index = 0
        st.rerun()


# =========================
# 單字清單
# =========================
with st.expander("查看目前範圍的單字清單"):
    st.dataframe(
        filtered_df[
            [
                "word", "meaning", "pos", "past",
                "past_participle", "grade",
                "semester", "lesson", "tags"
            ]
        ],
        use_container_width=True
    )
