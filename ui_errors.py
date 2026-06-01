"""
ui_errors.py
錯題本畫面。

功能：
1. 顯示目前使用者的錯題統計
2. 顯示答錯次數、最近錯誤答案、正確答案
3. 可依題型篩選
4. 可查看錯題明細
5. 可下載錯題本 CSV
"""

import pandas as pd
import streamlit as st

from database import load_error_summary, load_error_details
from utils import safe_str


def render_error_notebook_page(user_id: str, user_name: str):
    """錯題本主畫面。"""
    st.subheader("📒 錯題本")
    st.caption(f"目前使用者：{user_name}")

    error_df = load_error_summary(user_id)

    if error_df.empty:
        st.success("目前沒有錯題紀錄。可以先到測驗模式作答，答錯的題目會自動進入錯題本。")
        return

    # 統計摘要
    total_error_words = len(error_df)
    total_wrong_count = int(error_df["wrong_count"].sum())
    most_wrong = error_df.iloc[0]["word"] if total_error_words > 0 else ""

    m1, m2, m3 = st.columns(3)
    m1.metric("錯題單字數", total_error_words)
    m2.metric("總答錯次數", total_wrong_count)
    m3.metric("最常錯單字", most_wrong)

    st.divider()

    # 題型篩選
    quiz_types = ["全部"] + sorted([
        x for x in error_df["last_quiz_type"].dropna().astype(str).unique().tolist()
        if x
    ])
    selected_type = st.selectbox("依最近錯誤題型篩選", quiz_types)

    display_df = error_df.copy()
    if selected_type != "全部":
        display_df = display_df[display_df["last_quiz_type"].astype(str) == selected_type]

    # 欄位改成中文顯示
    show_df = display_df.rename(columns={
        "word": "單字",
        "wrong_count": "錯誤次數",
        "correct_count": "答對次數",
        "total_count": "總作答次數",
        "last_quiz_type": "最近錯誤題型",
        "last_question": "最近錯誤題目",
        "last_wrong_answer": "最近錯誤答案",
        "last_correct_answer": "正確答案",
        "last_wrong_at": "最近錯誤時間",
    })

    columns_to_show = [
        "單字",
        "錯誤次數",
        "答對次數",
        "總作答次數",
        "最近錯誤題型",
        "最近錯誤答案",
        "正確答案",
        "最近錯誤時間",
        "最近錯誤題目",
    ]
    columns_to_show = [c for c in columns_to_show if c in show_df.columns]

    st.markdown("### 錯題統計")
    st.dataframe(show_df[columns_to_show], use_container_width=True, hide_index=True)

    csv_bytes = show_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"下載 {user_name} 錯題本 CSV",
        data=csv_bytes,
        file_name=f"{user_id}_error_notebook.csv",
        mime="text/csv",
        key=f"download_error_notebook_{user_id}"
    )

    st.caption("完整備份 JSON 也會包含錯題本統計快照；還原時錯題本會依 quiz_log 自動重建。")

    st.divider()

    # 查看單一單字錯題明細
    st.markdown("### 查看錯題明細")

    word_options = ["全部錯題"] + display_df["word"].dropna().astype(str).tolist()
    selected_word = st.selectbox("選擇單字", word_options)

    if selected_word == "全部錯題":
        detail_df = load_error_details(user_id)
    else:
        selected_rows = display_df[display_df["word"].astype(str) == selected_word]
        if selected_rows.empty:
            detail_df = pd.DataFrame()
        else:
            word_id = safe_str(selected_rows.iloc[0]["word_id"])
            detail_df = load_error_details(user_id, word_id)

    if detail_df.empty:
        st.info("目前沒有可顯示的錯題明細。")
    else:
        detail_show_df = detail_df.rename(columns={
            "word": "單字",
            "quiz_type": "題型",
            "question": "題目",
            "user_answer": "錯誤答案",
            "correct_answer": "正確答案",
            "created_at": "答錯時間",
        })
        st.dataframe(detail_show_df, use_container_width=True, hide_index=True)

    st.divider()

    st.info("要加強錯題，可以到「測驗模式」將出題來源改成「錯題本」。")
