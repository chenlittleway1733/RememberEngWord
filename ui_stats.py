"""
ui_stats.py
統計報表頁面。

功能：
1. 顯示目前使用者整體學習進度
2. 顯示測驗答題統計
3. 顯示各題型正確率
4. 顯示最常錯單字
5. 顯示最近測驗紀錄
"""

from datetime import date
import pandas as pd
import streamlit as st

from database import load_quiz_log, load_error_summary
from utils import safe_int


def render_stats_page(user_id: str, user_name: str, merged_df: pd.DataFrame):
    """統計報表主畫面。"""
    st.subheader("📊 統計報表")
    st.caption(f"目前使用者：{user_name}")

    if merged_df.empty:
        st.warning("目前沒有單字資料。")
        return

    today_str = date.today().isoformat()

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

    mastery_series = pd.to_numeric(merged_df["mastery"], errors="coerce").fillna(0)
    avg_mastery = round(float(mastery_series.mean()), 1) if total_words else 0

    st.markdown("### 學習總覽")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("全部單字", total_words)
    c2.metric("今日可複習", due_today)
    c3.metric("未學", not_started)
    c4.metric("學習中 / 熟悉", learning)
    c5.metric("已掌握", mastered)

    st.progress(min(mastered / total_words, 1.0) if total_words else 0)
    st.caption(f"已掌握比例：{round(mastered / total_words * 100, 1) if total_words else 0}%｜平均熟練度：{avg_mastery}/100")

    st.divider()

    st.markdown("### 學習狀態分布")
    status_df = (
        merged_df["status"]
        .replace("", "未學")
        .fillna("未學")
        .value_counts()
        .reset_index()
    )
    status_df.columns = ["狀態", "單字數"]
    st.dataframe(status_df, use_container_width=True, hide_index=True)
    st.bar_chart(status_df.set_index("狀態"))

    st.divider()

    quiz_df = load_quiz_log(user_id)

    st.markdown("### 測驗總覽")
    if quiz_df.empty:
        st.info("目前還沒有測驗紀錄。")
    else:
        quiz_df["is_correct"] = pd.to_numeric(quiz_df["is_correct"], errors="coerce").fillna(0).astype(int)
        total_quiz = len(quiz_df)
        correct_quiz = int(quiz_df["is_correct"].sum())
        wrong_quiz = total_quiz - correct_quiz
        accuracy = round(correct_quiz / total_quiz * 100, 1) if total_quiz else 0

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("測驗總題數", total_quiz)
        q2.metric("答對", correct_quiz)
        q3.metric("答錯", wrong_quiz)
        q4.metric("正確率", f"{accuracy}%")

        st.progress(min(accuracy / 100, 1.0))

        st.markdown("#### 各題型正確率")
        type_stats = (
            quiz_df
            .groupby("quiz_type")
            .agg(
                作答次數=("id", "count"),
                答對次數=("is_correct", "sum")
            )
            .reset_index()
        )
        type_stats["答錯次數"] = type_stats["作答次數"] - type_stats["答對次數"]
        type_stats["正確率"] = (type_stats["答對次數"] / type_stats["作答次數"] * 100).round(1)
        type_stats = type_stats.rename(columns={"quiz_type": "題型"})
        st.dataframe(type_stats, use_container_width=True, hide_index=True)

        chart_df = type_stats[["題型", "正確率"]].set_index("題型")
        st.bar_chart(chart_df)

    st.divider()

    st.markdown("### 最常錯單字")
    error_df = load_error_summary(user_id)

    if error_df.empty:
        st.success("目前沒有錯題紀錄。")
    else:
        top_error_df = error_df.head(10).rename(columns={
            "word": "單字",
            "wrong_count": "錯誤次數",
            "correct_count": "答對次數",
            "total_count": "總作答次數",
            "last_quiz_type": "最近錯誤題型",
            "last_wrong_answer": "最近錯誤答案",
            "last_correct_answer": "正確答案",
            "last_wrong_at": "最近錯誤時間",
        })

        show_cols = [
            "單字",
            "錯誤次數",
            "答對次數",
            "總作答次數",
            "最近錯誤題型",
            "最近錯誤答案",
            "正確答案",
            "最近錯誤時間",
        ]
        show_cols = [c for c in show_cols if c in top_error_df.columns]
        st.dataframe(top_error_df[show_cols], use_container_width=True, hide_index=True)

        chart_error = top_error_df[["單字", "錯誤次數"]].set_index("單字")
        st.bar_chart(chart_error)

    st.divider()

    st.markdown("### 最近測驗紀錄")
    if quiz_df.empty:
        st.info("尚無測驗紀錄。")
    else:
        recent_df = quiz_df.head(30).rename(columns={
            "word": "單字",
            "quiz_type": "題型",
            "question": "題目",
            "correct_answer": "正確答案",
            "user_answer": "作答",
            "is_correct": "是否答對",
            "created_at": "作答時間",
        })
        recent_df["是否答對"] = recent_df["是否答對"].map({1: "答對", 0: "答錯"})
        show_cols = ["作答時間", "單字", "題型", "是否答對", "作答", "正確答案", "題目"]
        show_cols = [c for c in show_cols if c in recent_df.columns]
        st.dataframe(recent_df[show_cols], use_container_width=True, hide_index=True)

        csv_bytes = recent_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"下載 {user_name} 最近測驗紀錄 CSV",
            data=csv_bytes,
            file_name=f"{user_id}_recent_quiz_stats.csv",
            mime="text/csv",
            key=f"download_recent_quiz_stats_{user_id}"
        )
