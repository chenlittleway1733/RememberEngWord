"""
國中英文單字智慧複習系統
主入口檔案：app.py

這個檔案是整個 Streamlit App 的入口。
重構後 app.py 只負責整合流程，不放大量細節程式碼。

檔案功能說明：
- config.py：全域設定，例如 words.csv、progress.db、使用者、發音聲音
- utils.py：共用工具函式，例如 safe_str、safe_int、normalize_answer
- data.py：讀取與篩選 words.csv
- database.py：SQLite 資料庫、學習紀錄、測驗紀錄、備份匯入
- audio.py：edge-tts 發音、自動播放、播放按鈕
- quiz.py：測驗出題邏輯，不放 UI
- ui_common.py：共用 UI、側邊欄、備份區、CSS
- ui_cards.py：單字卡學習畫面
- ui_quiz.py：測驗模式畫面
"""

from datetime import date
import streamlit as st

from config import APP_TITLE
from data import load_words, merge_words_with_progress
from database import (
    init_db,
    ensure_progress_for_words,
    ensure_quiz_log_table,
    load_users,
    load_progress,
)
from ui_common import (
    apply_global_styles,
    render_sidebar_user_selector,
    render_sidebar_quick_backup,
    render_sidebar_filters,
    render_sidebar_stats,
)
from ui_cards import render_vocab_card_page
from ui_quiz import render_quiz_page


# ============================================================
# 一、Streamlit 頁面設定
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📘",
    layout="wide"
)


# ============================================================
# 二、套用全域樣式
# ============================================================

apply_global_styles()


# ============================================================
# 三、讀取 words.csv
# ============================================================

words_df = load_words()
if words_df.empty:
    st.stop()


# ============================================================
# 四、初始化 SQLite 資料庫
# ============================================================

init_db()
ensure_quiz_log_table()
ensure_progress_for_words(words_df)


# ============================================================
# 五、側邊欄：使用者、快速備份
# ============================================================

users_df = load_users()
selected_user_id, selected_user_name = render_sidebar_user_selector(users_df)

render_sidebar_quick_backup(
    user_id=selected_user_id,
    user_name=selected_user_name
)


# ============================================================
# 六、讀取目前使用者學習紀錄，合併單字資料
# ============================================================

progress_df = load_progress(selected_user_id)
merged_df = merge_words_with_progress(words_df, progress_df)


# ============================================================
# 七、側邊欄：範圍篩選與學習統計
# ============================================================

filter_state = render_sidebar_filters(merged_df)

render_sidebar_stats(
    merged_df=merged_df,
    user_name=selected_user_name
)


# ============================================================
# 八、主畫面標題與統計
# ============================================================

st.markdown('<div class="main-title">📘 國中英文單字複習</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="small-caption">第三階段：單字卡學習 + 測驗模式 + SQLite 學習紀錄</div>',
    unsafe_allow_html=True
)

today_str = date.today().isoformat()
due_today = len(
    merged_df[
        (merged_df["next_review"].astype(str) == "") |
        (merged_df["next_review"].astype(str) <= today_str)
    ]
)
learning = len(merged_df[merged_df["status"].astype(str).isin(["學習中", "熟悉"])])
mastered = len(merged_df[merged_df["status"].astype(str) == "已掌握"])

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("今日可複習", due_today)
metric_col2.metric("學習中", learning)
metric_col3.metric("已掌握", mastered)


# ============================================================
# 九、主功能模式切換
# ============================================================

app_mode = st.radio(
    "功能模式",
    ["單字卡學習", "測驗模式"],
    horizontal=True,
    index=0,
    key="app_mode"
)


# ============================================================
# 十、呼叫對應畫面
# ============================================================

if app_mode == "單字卡學習":
    render_vocab_card_page(
        merged_df=merged_df,
        user_id=selected_user_id,
        user_name=selected_user_name,
        filter_state=filter_state
    )

elif app_mode == "測驗模式":
    render_quiz_page(
        merged_df=merged_df,
        user_id=selected_user_id,
        user_name=selected_user_name,
        filter_state=filter_state
    )
