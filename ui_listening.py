"""
ui_listening.py
聽力測驗頁面。

第一版功能：
1. 聽單字，選出正確英文
2. 支援 5 / 10 / 20 / 任意題
3. 支援出題來源：目前範圍、今日複習、未學單字、學習中、錯題本
4. 答題後寫入 quiz_log
5. 答對 / 答錯會更新 progress
"""

from datetime import date
import hashlib
import random
import pandas as pd
import streamlit as st

from utils import safe_str
from data import filter_words
from database import update_progress, log_quiz_result, load_quiz_log, get_error_word_ids
from audio import get_audio_file, autoplay_audio, audio_button


def reset_listening_session():
    """重設本次聽力測驗狀態。"""
    st.session_state.listening_current = {}
    st.session_state.listening_answered = False
    st.session_state.listening_count_done = 0
    st.session_state.listening_count_correct = 0
    st.session_state.listening_finished = False


def get_listening_target_count() -> int:
    """取得聽力測驗目標題數。"""
    count_choice = st.session_state.get("listening_count_choice", "5 題")
    if count_choice == "5 題":
        return 5
    if count_choice == "10 題":
        return 10
    if count_choice == "20 題":
        return 20
    return int(st.session_state.get("listening_custom_count", 5))


def make_listening_options(row: pd.Series, source_df: pd.DataFrame) -> list[str]:
    """
    建立聽力測驗選項。
    優先使用 words.csv 的 word_option_1~3。
    如果不足，再從同一題庫抽其他單字補足。
    """
    correct = safe_str(row.get("word", ""))

    options = [correct]
    for col in ["word_option_1", "word_option_2", "word_option_3"]:
        value = safe_str(row.get(col, ""))
        if value and value not in options:
            options.append(value)

    # 若選項不足，從目前題庫補
    pool_words = source_df["word"].dropna().astype(str).tolist()
    random.shuffle(pool_words)

    for w in pool_words:
        if len(options) >= 4:
            break
        if w and w not in options:
            options.append(w)

    options = options[:4]
    random.shuffle(options)
    return options


def prepare_new_listening_question(source_df: pd.DataFrame):
    """建立新的聽力題。"""
    if source_df.empty:
        return {}

    pool = source_df[source_df["word"].astype(str).str.strip() != ""].copy()
    if pool.empty:
        return {}

    row = pool.sample(1).iloc[0]
    options = make_listening_options(row, pool)

    return {
        "quiz_type": "聽力測驗：聽單字選英文",
        "question": "請聽發音，選出正確的英文單字。",
        "correct_answer": safe_str(row.get("word", "")),
        "options": options,
        "word_row": row.to_dict(),
    }


def render_listening_page(merged_df: pd.DataFrame, user_id: str, user_name: str, filter_state: dict):
    """聽力測驗頁面。"""
    st.subheader("🎧 聽力測驗")
    st.caption(f"目前使用者：{user_name}")

    today_str = date.today().isoformat()
    filtered_df = filter_words(merged_df, filter_state, today_str)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        listening_source = st.selectbox(
            "出題來源",
            ["目前範圍", "今日複習", "未學單字", "學習中", "錯題本"],
            key="listening_source"
        )

    with col2:
        listening_count_choice = st.selectbox(
            "出題數",
            ["5 題", "10 題", "20 題", "任意題"],
            key="listening_count_choice"
        )

    with col3:
        if listening_count_choice == "任意題":
            st.number_input(
                "自訂題數",
                min_value=1,
                max_value=100,
                value=5,
                step=1,
                key="listening_custom_count"
            )
        else:
            st.write("")
            st.write("")

    target_count = get_listening_target_count()

    control_col1, control_col2 = st.columns([1, 1])
    with control_col1:
        start_new = st.button(
            f"開始 / 重設聽力測驗（{target_count} 題）",
            use_container_width=True,
            key="start_listening_session"
        )
    with control_col2:
        new_question = st.button(
            "產生新聽力題",
            use_container_width=True,
            key="new_listening_question"
        )

    if start_new:
        reset_listening_session()

    # 初始化 session
    if "listening_count_done" not in st.session_state:
        st.session_state.listening_count_done = 0
    if "listening_count_correct" not in st.session_state:
        st.session_state.listening_count_correct = 0
    if "listening_finished" not in st.session_state:
        st.session_state.listening_finished = False
    if "listening_answered" not in st.session_state:
        st.session_state.listening_answered = False
    if "listening_current" not in st.session_state:
        st.session_state.listening_current = {}

    # 出題來源
    if listening_source == "目前範圍":
        source_df = filtered_df.copy()
    elif listening_source == "今日複習":
        source_df = merged_df[
            (merged_df["next_review"].astype(str) == "") |
            (merged_df["next_review"].astype(str) <= today_str)
        ].copy()
    elif listening_source == "未學單字":
        source_df = merged_df[merged_df["status"].astype(str).isin(["", "未學"])].copy()
    elif listening_source == "學習中":
        source_df = merged_df[merged_df["status"].astype(str).isin(["學習中", "熟悉"])].copy()
    elif listening_source == "錯題本":
        error_word_ids = get_error_word_ids(user_id)
        source_df = merged_df[merged_df["word_id"].astype(str).isin(error_word_ids)].copy()
    else:
        source_df = merged_df.copy()

    source_df = source_df[source_df["word"].astype(str).str.strip() != ""].copy()

    st.info(f"目前聽力題庫共有 {len(source_df)} 個可出題單字。")

    # 條件改變時重設
    signature = hashlib.md5(
        f"{user_id}|{listening_source}|{target_count}|{filter_state['grade']}|{filter_state['semester']}|{filter_state['lesson']}|{filter_state['pos']}|{filter_state['keyword']}".encode("utf-8")
    ).hexdigest()

    if "last_listening_signature" not in st.session_state:
        st.session_state.last_listening_signature = signature

    if st.session_state.last_listening_signature != signature:
        reset_listening_session()
        st.session_state.last_listening_signature = signature

    # 進度
    m1, m2 = st.columns(2)
    m1.metric("進度", f"{st.session_state.listening_count_done}/{target_count}")
    m2.metric("答對", st.session_state.listening_count_correct)

    if target_count > 0:
        st.progress(min(st.session_state.listening_count_done / target_count, 1.0))

    if st.session_state.listening_finished or st.session_state.listening_count_done >= target_count:
        st.session_state.listening_finished = True
        accuracy = round(st.session_state.listening_count_correct / target_count * 100, 1) if target_count else 0
        st.success(
            f"本次聽力測驗完成！共 {target_count} 題，答對 {st.session_state.listening_count_correct} 題，正確率 {accuracy}%"
        )

        if st.button("重新開始聽力測驗", use_container_width=True, key="restart_listening"):
            reset_listening_session()
            st.rerun()

        return

    if new_question or not st.session_state.listening_current:
        st.session_state.listening_current = prepare_new_listening_question(source_df)
        st.session_state.listening_answered = False

    current = st.session_state.get("listening_current", {})
    if not current:
        st.warning("目前範圍沒有足夠單字可以產生聽力題。")
        return

    row = pd.Series(current["word_row"])
    correct_answer = safe_str(current["correct_answer"])

    st.divider()
    st.markdown("### 題目")
    st.markdown(f"**第 {st.session_state.listening_count_done + 1} 題 / 共 {target_count} 題**")
    st.write("請先聽發音，再選出正確英文。")

    # 自動播放每題一次
    autoplay_key = f"{user_id}|{row.get('word_id', '')}|{st.session_state.listening_count_done}"
    if st.session_state.get("last_listening_autoplay_key", "") != autoplay_key:
        audio_path = get_audio_file(correct_answer)
        autoplay_audio(audio_path)
        st.session_state.last_listening_autoplay_key = autoplay_key

    audio_button(correct_answer, "🔊 再聽一次", key=f"listening_replay_{user_id}_{row.get('word_id','')}_{st.session_state.listening_count_done}")

    user_answer = st.radio(
        "請選擇你聽到的單字",
        current["options"],
        key=f"listening_choice_{user_id}_{row.get('word_id','')}_{st.session_state.listening_count_done}"
    )

    submit_col1, submit_col2 = st.columns([1, 1])

    with submit_col1:
        submit = st.button(
            "送出答案",
            use_container_width=True,
            key=f"submit_listening_{st.session_state.listening_count_done}"
        )

    with submit_col2:
        if st.button(
            "跳過 / 換一題",
            use_container_width=True,
            key=f"skip_listening_{st.session_state.listening_count_done}"
        ):
            st.session_state.listening_current = prepare_new_listening_question(source_df)
            st.session_state.listening_answered = False
            st.rerun()

    if submit and not st.session_state.listening_answered:
        is_correct = safe_str(user_answer) == correct_answer

        log_quiz_result(
            user_id,
            row,
            current["quiz_type"],
            current["question"],
            correct_answer,
            user_answer,
            is_correct
        )

        if is_correct:
            update_progress(user_id, row, "good")
            st.session_state.listening_count_correct += 1
            st.success(f"答對了！正確答案：{correct_answer}")
        else:
            update_progress(user_id, row, "forgot")
            st.error(f"答錯了。你選的是：{user_answer}；正確答案：{correct_answer}")

        st.session_state.listening_count_done += 1
        st.session_state.listening_answered = True

        if st.session_state.listening_count_done >= target_count:
            st.session_state.listening_finished = True

    if st.session_state.get("listening_answered", False):
        if st.session_state.listening_finished:
            if st.button("查看本次聽力結果", use_container_width=True, key="show_listening_result"):
                st.rerun()
        else:
            if st.button("下一題", use_container_width=True, key=f"next_listening_{st.session_state.listening_count_done}"):
                st.session_state.listening_current = prepare_new_listening_question(source_df)
                st.session_state.listening_answered = False
                st.rerun()

    st.divider()
    with st.expander("查看最近聽力測驗紀錄"):
        quiz_df = load_quiz_log(user_id)
        if quiz_df.empty:
            st.info("目前沒有測驗紀錄。")
        else:
            listen_df = quiz_df[quiz_df["quiz_type"].astype(str).str.contains("聽力測驗", na=False)]
            if listen_df.empty:
                st.info("目前沒有聽力測驗紀錄。")
            else:
                st.dataframe(listen_df.head(30), use_container_width=True, hide_index=True)
