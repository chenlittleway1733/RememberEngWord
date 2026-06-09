"""
ui_quiz.py
測驗模式畫面。

本版新增：
1. 可設定本次測驗出題數：5 題、10 題、20 題、任意題
2. 顯示本次測驗進度
3. 顯示本次測驗答對數
4. 達到出題數後顯示完成結果
"""

from datetime import date
import hashlib
import pandas as pd
import streamlit as st

from utils import safe_str, normalize_answer
from data import filter_words
from audio import audio_button
from database import update_progress, log_quiz_result, load_quiz_log, get_error_word_ids
from quiz import get_quiz_pool, prepare_new_quiz_question


def reset_quiz_session():
    """
    重設本次測驗狀態。
    """
    st.session_state.quiz_current = {}
    st.session_state.quiz_answered = False
    st.session_state.quiz_count_done = 0
    st.session_state.quiz_count_correct = 0
    st.session_state.quiz_finished = False


def get_quiz_target_count() -> int:
    """
    取得本次測驗目標題數。
    """
    count_choice = st.session_state.get("quiz_count_choice", "5 題")

    if count_choice == "5 題":
        return 5
    if count_choice == "10 題":
        return 10
    if count_choice == "20 題":
        return 20

    return int(st.session_state.get("quiz_custom_count", 5))


def render_quiz_page(merged_df: pd.DataFrame, user_id: str, user_name: str, filter_state: dict):
    """測驗模式頁面。"""
    st.subheader("📝 測驗模式")

    today_str = date.today().isoformat()
    filtered_df = filter_words(merged_df, filter_state, today_str)

    quiz_col1, quiz_col2, quiz_col3, quiz_col4 = st.columns([1, 1, 1, 1])

    with quiz_col1:
        quiz_type = st.selectbox(
            "題型",
            ["英翻中選擇題", "中翻英選擇題", "動詞變化選擇題", "例句填空"],
            key="quiz_type"
        )

    with quiz_col2:
        quiz_source = st.selectbox(
            "出題來源",
            ["目前範圍", "今日複習", "忘記了", "不熟", "認識", "很熟", "錯題本"],
            key="quiz_source"
        )

    with quiz_col3:
        quiz_count_choice = st.selectbox(
            "出題數",
            ["5 題", "10 題", "20 題", "任意題"],
            key="quiz_count_choice"
        )

    with quiz_col4:
        if quiz_count_choice == "任意題":
            st.number_input(
                "自訂題數",
                min_value=1,
                max_value=100,
                value=5,
                step=1,
                key="quiz_custom_count"
            )
        else:
            st.write("")
            st.write("")

    target_count = get_quiz_target_count()

    control_col1, control_col2 = st.columns([1, 1])

    with control_col1:
        start_new_session = st.button(
            f"開始 / 重設本次測驗（{target_count} 題）",
            use_container_width=True,
            key="start_quiz_session"
        )

    with control_col2:
        new_question = st.button(
            "產生新題目",
            use_container_width=True,
            key="new_quiz_question"
        )

    if start_new_session:
        reset_quiz_session()

    # 初始化本次測驗狀態
    if "quiz_count_done" not in st.session_state:
        st.session_state.quiz_count_done = 0
    if "quiz_count_correct" not in st.session_state:
        st.session_state.quiz_count_correct = 0
    if "quiz_finished" not in st.session_state:
        st.session_state.quiz_finished = False
    if "quiz_answered" not in st.session_state:
        st.session_state.quiz_answered = False

    # 依出題來源決定題庫
    if quiz_source == "目前範圍":
        quiz_source_df = filtered_df.copy()
    elif quiz_source == "今日複習":
        quiz_source_df = merged_df[
            (merged_df["next_review"].astype(str) == "") |
            (merged_df["next_review"].astype(str) <= today_str)
        ].copy()
    elif quiz_source in ["忘記了", "不熟", "認識", "很熟"]:
        quiz_source_df = merged_df[merged_df["status"].astype(str) == quiz_source].copy()
    elif quiz_source == "錯題本":
        error_word_ids = get_error_word_ids(user_id)
        quiz_source_df = merged_df[merged_df["word_id"].astype(str).isin(error_word_ids)].copy()
    else:
        quiz_source_df = merged_df.copy()

    quiz_pool = get_quiz_pool(quiz_source_df, quiz_type)
    st.info(f"目前題庫共有 {len(quiz_pool)} 個可出題單字。")

    # 題型、來源、範圍、題數變更時，重設本次測驗
    quiz_signature = hashlib.md5(
        f"{user_id}|{quiz_type}|{quiz_source}|{target_count}|{filter_state['grade']}|{filter_state['semester']}|{filter_state['lesson']}|{filter_state['pos']}|{filter_state['keyword']}".encode("utf-8")
    ).hexdigest()

    if "last_quiz_signature" not in st.session_state:
        st.session_state.last_quiz_signature = quiz_signature

    if st.session_state.last_quiz_signature != quiz_signature:
        reset_quiz_session()
        st.session_state.last_quiz_signature = quiz_signature

    if "quiz_current" not in st.session_state:
        st.session_state.quiz_current = {}

    # 進度顯示
    progress_text = f"本次進度：{st.session_state.quiz_count_done} / {target_count} 題"
    correct_text = f"本次答對：{st.session_state.quiz_count_correct} 題"

    prog_col1, prog_col2, prog_col3 = st.columns([1, 1, 2])
    prog_col1.metric("進度", f"{st.session_state.quiz_count_done}/{target_count}")
    prog_col2.metric("答對", st.session_state.quiz_count_correct)

    if target_count > 0:
        st.progress(min(st.session_state.quiz_count_done / target_count, 1.0))

    # 若已完成本次測驗
    if st.session_state.quiz_finished or st.session_state.quiz_count_done >= target_count:
        st.session_state.quiz_finished = True
        accuracy = 0
        if target_count > 0:
            accuracy = round(st.session_state.quiz_count_correct / target_count * 100, 1)

        st.success(
            f"本次測驗完成！共 {target_count} 題，答對 {st.session_state.quiz_count_correct} 題，正確率 {accuracy}%"
        )

        if st.button("重新開始一回合", use_container_width=True, key="restart_quiz_after_finish"):
            reset_quiz_session()
            st.rerun()

        with st.expander("查看最近測驗紀錄"):
            quiz_log_df = load_quiz_log(user_id)
            if quiz_log_df.empty:
                st.info("目前還沒有測驗紀錄。")
            else:
                st.dataframe(quiz_log_df.head(30), use_container_width=True, hide_index=True)

        return

    # 需要產生題目時
    if new_question or not st.session_state.quiz_current:
        st.session_state.quiz_current = prepare_new_quiz_question(quiz_source_df, quiz_type)
        st.session_state.quiz_answered = False

    current_quiz = st.session_state.get("quiz_current", {})

    if not current_quiz:
        st.warning("目前範圍沒有足夠資料可以產生這種題型。請確認 words.csv 已有測驗欄位，或換其他題型。")
        return

    st.divider()
    st.markdown("### 題目")
    st.markdown(f"**第 {st.session_state.quiz_count_done + 1} 題 / 共 {target_count} 題**")
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
            key=f"quiz_choice_{user_id}_{current_quiz['question']}_{st.session_state.quiz_count_done}"
        )

    elif current_quiz["quiz_type"] == "例句填空":
        st.write("請依提示輸入完整答案：")
        user_answer = st.text_input(
            "答案",
            key=f"quiz_input_{user_id}_{current_quiz['question']}_{st.session_state.quiz_count_done}"
        )

    submit_col1, submit_col2 = st.columns([1, 1])

    with submit_col1:
        submit_answer = st.button(
            "送出答案",
            use_container_width=True,
            key=f"submit_quiz_answer_{st.session_state.quiz_count_done}"
        )

    with submit_col2:
        if st.button("跳過 / 換一題", use_container_width=True, key=f"skip_quiz_question_{st.session_state.quiz_count_done}"):
            st.session_state.quiz_current = prepare_new_quiz_question(quiz_source_df, quiz_type)
            st.session_state.quiz_answered = False
            st.rerun()

    if submit_answer and not st.session_state.quiz_answered:
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
            progress_result = update_progress(user_id, q_word_row, "good", source="quiz")
            st.session_state.quiz_count_correct += 1

            if progress_result.get("change_direction") == "up":
                st.success(f"答對了！正確答案：{correct_answer}\n\n{progress_result.get('note', '')}")
            else:
                st.info(f"答對了！正確答案：{correct_answer}\n\n{progress_result.get('note', '')}")

        else:
            progress_result = update_progress(user_id, q_word_row, "forgot", source="quiz")
            if progress_result.get("change_direction") == "down":
                st.warning(f"答錯了。你的答案：{user_answer}；正確答案：{correct_answer}\n\n{progress_result.get('note', '')}")
            else:
                st.error(f"答錯了。你的答案：{user_answer}；正確答案：{correct_answer}\n\n{progress_result.get('note', '')}")

        st.session_state.quiz_count_done += 1
        st.session_state.quiz_answered = True

        if st.session_state.quiz_count_done >= target_count:
            st.session_state.quiz_finished = True

    if st.session_state.get("quiz_answered", False):
        if st.session_state.quiz_finished:
            if st.button("查看本次結果", use_container_width=True, key="show_finish_result"):
                st.rerun()
        else:
            if st.button("下一題", use_container_width=True, key=f"next_quiz_after_answer_{st.session_state.quiz_count_done}"):
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
