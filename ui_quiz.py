"""
ui_quiz.py
測驗模式畫面。
"""

from datetime import date
import hashlib
import pandas as pd
import streamlit as st

from utils import safe_str, normalize_answer
from data import filter_words
from audio import audio_button
from database import update_progress, log_quiz_result, load_quiz_log
from quiz import get_quiz_pool, prepare_new_quiz_question


def render_quiz_page(merged_df: pd.DataFrame, user_id: str, user_name: str, filter_state: dict):
    """測驗模式頁面。"""
    st.subheader("📝 測驗模式")

    today_str = date.today().isoformat()
    filtered_df = filter_words(merged_df, filter_state, today_str)

    quiz_col1, quiz_col2, quiz_col3 = st.columns([1, 1, 1])

    with quiz_col1:
        quiz_type = st.selectbox(
            "題型",
            ["英翻中選擇題", "中翻英選擇題", "動詞變化選擇題", "例句填空"],
            key="quiz_type"
        )

    with quiz_col2:
        quiz_source = st.selectbox(
            "出題來源",
            ["目前範圍", "今日複習", "未學單字", "學習中"],
            key="quiz_source"
        )

    with quiz_col3:
        st.write("")
        st.write("")
        new_question = st.button("產生新題目", use_container_width=True, key="new_quiz_question")

    if quiz_source == "目前範圍":
        quiz_source_df = filtered_df.copy()
    elif quiz_source == "今日複習":
        quiz_source_df = merged_df[
            (merged_df["next_review"].astype(str) == "") |
            (merged_df["next_review"].astype(str) <= today_str)
        ].copy()
    elif quiz_source == "未學單字":
        quiz_source_df = merged_df[merged_df["status"].astype(str).isin(["", "未學"])].copy()
    else:
        quiz_source_df = merged_df[merged_df["status"].astype(str).isin(["學習中", "熟悉"])].copy()

    quiz_pool = get_quiz_pool(quiz_source_df, quiz_type)
    st.info(f"目前題庫共有 {len(quiz_pool)} 個可出題單字。")

    quiz_signature = hashlib.md5(
        f"{user_id}|{quiz_type}|{quiz_source}|{filter_state['grade']}|{filter_state['semester']}|{filter_state['lesson']}|{filter_state['pos']}|{filter_state['keyword']}".encode("utf-8")
    ).hexdigest()

    if "last_quiz_signature" not in st.session_state:
        st.session_state.last_quiz_signature = quiz_signature

    if st.session_state.last_quiz_signature != quiz_signature:
        st.session_state.quiz_current = {}
        st.session_state.quiz_answered = False
        st.session_state.last_quiz_signature = quiz_signature

    if "quiz_current" not in st.session_state:
        st.session_state.quiz_current = {}

    if new_question or not st.session_state.quiz_current:
        st.session_state.quiz_current = prepare_new_quiz_question(quiz_source_df, quiz_type)
        st.session_state.quiz_answered = False

    current_quiz = st.session_state.get("quiz_current", {})

    if not current_quiz:
        st.warning("目前範圍沒有足夠資料可以產生這種題型。請確認 words.csv 已有測驗欄位，或換其他題型。")
        return

    st.divider()
    st.markdown("### 題目")
    st.markdown(f"**{current_quiz['question']}**")

    if current_quiz.get("hint"):
        st.caption(f"提示：{current_quiz['hint']}")

    q_word_row = pd.Series(current_quiz["word_row"])
    q_word = safe_str(q_word_row.get("word", ""))

    if q_word:
        audio_button(q_word, "🔊 播放題目單字", key=f"quiz_word_audio_{user_id}_{q_word_row.get('word_id','')}")

    user_answer = ""

    if current_quiz["quiz_type"] in ["英翻中選擇題", "中翻英選擇題", "動詞變化選擇題"]:
        options = current_quiz.get("options", [])
        if len(options) < 2:
            st.warning("這題選項不足，請檢查 words.csv 的誘答欄位。")
            if st.button("換一題", key="bad_question_next"):
                st.session_state.quiz_current = prepare_new_quiz_question(quiz_source_df, quiz_type)
                st.rerun()
            return

        user_answer = st.radio(
            "請選擇答案",
            options,
            key=f"quiz_choice_{user_id}_{current_quiz['question']}"
        )

    elif current_quiz["quiz_type"] == "例句填空":
        st.write("請依提示輸入完整答案：")
        user_answer = st.text_input(
            "答案",
            key=f"quiz_input_{user_id}_{current_quiz['question']}"
        )

    submit_col1, submit_col2 = st.columns([1, 1])

    with submit_col1:
        submit_answer = st.button("送出答案", use_container_width=True, key="submit_quiz_answer")

    with submit_col2:
        if st.button("跳過 / 換一題", use_container_width=True, key="skip_quiz_question"):
            st.session_state.quiz_current = prepare_new_quiz_question(quiz_source_df, quiz_type)
            st.session_state.quiz_answered = False
            st.rerun()

    if submit_answer:
        correct_answer = safe_str(current_quiz["correct_answer"])

        if current_quiz["quiz_type"] == "例句填空":
            is_correct = normalize_answer(user_answer) == normalize_answer(correct_answer)
        else:
            is_correct = safe_str(user_answer) == correct_answer

        log_quiz_result(
            user_id,
            q_word_row,
            current_quiz["quiz_type"],
            current_quiz["question"],
            correct_answer,
            user_answer,
            is_correct
        )

        if is_correct:
            update_progress(user_id, q_word_row, "good")
            st.success(f"答對了！正確答案：{correct_answer}")
        else:
            update_progress(user_id, q_word_row, "forgot")
            st.error(f"答錯了。你的答案：{user_answer}；正確答案：{correct_answer}")

        st.session_state.quiz_answered = True

    if st.session_state.get("quiz_answered", False):
        if st.button("下一題", use_container_width=True, key="next_quiz_after_answer"):
            st.session_state.quiz_current = prepare_new_quiz_question(quiz_source_df, quiz_type)
            st.session_state.quiz_answered = False
            st.rerun()

    st.divider()
    with st.expander("查看最近測驗紀錄"):
        quiz_log_df = load_quiz_log(user_id)
        if quiz_log_df.empty:
            st.info("目前還沒有測驗紀錄。")
        else:
            st.dataframe(quiz_log_df.head(30), use_container_width=True, hide_index=True)
