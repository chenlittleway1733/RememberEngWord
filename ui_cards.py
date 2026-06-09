"""
ui_cards.py
單字卡學習畫面。
"""

from datetime import date
import hashlib
import html
import pandas as pd
import streamlit as st

from utils import safe_str
from data import filter_words
from database import get_progress
from audio import get_audio_file, autoplay_audio, audio_button
from ui_common import show_info_table, show_table_in_card, open_card, render_backup_section


def show_verb_rows_with_audio(current_word: pd.Series, selected_user_id: str, current_word_id: str):
    """動詞資料：原形、過去式、過去分詞、現在分詞右側各有發音按鈕。"""
    open_card("動詞資料", icon="🟢", css_class="soft-card-green")

    base_form = safe_str(current_word.get("base_form", ""))
    if not base_form:
        base_form = safe_str(current_word.get("word", ""))

    rows = [
        ("原形", base_form, "base"),
        ("過去式", safe_str(current_word.get("past", "")), "past"),
        ("過去分詞", safe_str(current_word.get("past_participle", "")), "pp"),
        ("現在分詞", safe_str(current_word.get("present_participle", "")), "ing"),
    ]

    h1, h2, h3 = st.columns([0.28, 0.52, 0.20])
    h1.markdown("**項目**")
    h2.markdown("**內容**")
    h3.markdown("**發音**")

    for label, value, audio_key in rows:
        if not safe_str(value):
            continue
        c1, c2, c3 = st.columns([0.28, 0.52, 0.20])
        c1.write(label)
        c2.markdown(f"**{value}**")
        with c3:
            audio_button(value, "🔊", key=f"verb_audio_{selected_user_id}_{current_word_id}_{audio_key}")

    transitivity = safe_str(current_word.get("transitivity", ""))
    if transitivity:
        show_info_table([("及物 / 不及物", transitivity)])


def render_examples(current_word: pd.Series, selected_user_id: str, current_word_id: str):
    """
    顯示例句。

    新版設計：
    1. 英文例句先顯示。
    2. 中文翻譯預設隱藏。
    3. 每一個例句都有「顯示中文 / 隱藏中文」按鈕。
    4. 保留例句播放按鈕。
    """
    st.divider()
    st.markdown('<div class="section-title">例句</div>', unsafe_allow_html=True)

    examples = []
    for i in range(1, 6):
        en_col = f"example_{i}"
        zh_col = f"example_zh_{i}"
        en_text = safe_str(current_word.get(en_col, ""))
        zh_text = safe_str(current_word.get(zh_col, ""))
        if en_text:
            examples.append((i, en_text, zh_text))

    if not examples:
        old_en = safe_str(current_word.get("example", ""))
        old_zh = safe_str(current_word.get("example_zh", ""))
        if old_en:
            examples.append((1, old_en, old_zh))

    if examples:
        first_example_text = examples[0][1]
        if "last_autoplay_example_id" not in st.session_state:
            st.session_state.last_autoplay_example_id = ""

        example_autoplay_id = f"{selected_user_id}|{current_word_id}|{first_example_text}"
        if st.session_state.last_autoplay_example_id != example_autoplay_id:
            example_audio = get_audio_file(first_example_text)
            autoplay_audio(example_audio)
            st.session_state.last_autoplay_example_id = example_autoplay_id

    example_cols = st.columns(2)

    for idx, (num, en_text, zh_text) in enumerate(examples):
        show_key = f"show_zh_{selected_user_id}_{current_word_id}_{num}"

        if show_key not in st.session_state:
            st.session_state[show_key] = False

        with example_cols[idx % 2]:
            # 先顯示英文例句；中文先不顯示
            example_html = f"""
            <div class="example-card">
                <div class="example-en">{num}. {html.escape(en_text)}</div>
            </div>
            """
            st.markdown(example_html, unsafe_allow_html=True)

            # 播放例句
            audio_button(
                en_text,
                f"🔊 播放例句 {num}",
                key=f"example_audio_{selected_user_id}_{current_word_id}_{num}"
            )

            # 顯示 / 隱藏中文按鈕
            if zh_text:
                button_label = "🙈 隱藏中文" if st.session_state[show_key] else "👀 顯示中文"

                if st.button(
                    button_label,
                    key=f"toggle_zh_{selected_user_id}_{current_word_id}_{num}",
                    use_container_width=True
                ):
                    st.session_state[show_key] = not st.session_state[show_key]
                    st.rerun()

                if st.session_state[show_key]:
                    st.markdown(
                        f"""
                        <div class="example-card">
                            <div class="example-zh">{html.escape(zh_text)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

def render_vocab_card_page(merged_df: pd.DataFrame, user_id: str, user_name: str, filter_state: dict):
    """單字卡學習頁面。"""
    today_str = date.today().isoformat()
    filtered_df = filter_words(merged_df, filter_state, today_str)

    st.caption(
        f"使用者：{user_name}　｜　目前範圍：{filter_state['grade']} / {filter_state['semester']} / "
        f"{filter_state['lesson']} / {filter_state['pos']}　｜　模式：{filter_state['mode']}"
    )

    if filtered_df.empty:
        st.warning("目前範圍沒有單字，請調整左側篩選條件。")
        return

    filter_signature = hashlib.md5(
        "|".join([
            user_id,
            filter_state["mode"],
            filter_state["grade"],
            filter_state["semester"],
            filter_state["lesson"],
            filter_state["pos"],
            filter_state["keyword"],
        ]).encode("utf-8")
    ).hexdigest()

    if "last_filter_signature" not in st.session_state:
        st.session_state.last_filter_signature = filter_signature

    if st.session_state.last_filter_signature != filter_signature:
        st.session_state.card_index = 0
        st.session_state.last_filter_signature = filter_signature

    if "card_index" not in st.session_state:
        st.session_state.card_index = 0

    if st.session_state.card_index >= len(filtered_df):
        st.session_state.card_index = 0

    filtered_df = filtered_df.reset_index(drop=True)
    current_word = filtered_df.iloc[st.session_state.card_index]
    current_word_id = safe_str(current_word["word_id"])
    current_progress = get_progress(user_id, current_word_id)

    # 自動播放單字
    if "last_autoplay_word_id" not in st.session_state:
        st.session_state.last_autoplay_word_id = ""

    autoplay_key = f"{user_id}|{current_word_id}"
    if st.session_state.last_autoplay_word_id != autoplay_key:
        word_audio = get_audio_file(safe_str(current_word["word"]))
        autoplay_audio(word_audio)
        st.session_state.last_autoplay_word_id = autoplay_key

    left_col, right_col = st.columns([0.92, 1.35], gap="large")

    with left_col:
        st.markdown('<div class="word-card">', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="word-text">{html.escape(safe_str(current_word["word"]))}</div>
            <div class="meaning-text">{html.escape(safe_str(current_word["meaning"]))}</div>
            """,
            unsafe_allow_html=True
        )
        st.write("")

        # 詞性說明上移到「重聽單字」按鈕上方
        st.write(f"**詞性：** {safe_str(current_word.get('pos', ''))}")
        if safe_str(current_word.get("pos_note", "")):
            st.caption(safe_str(current_word.get("pos_note", "")))

        # 單字發音
        audio_button(safe_str(current_word["word"]), "🔊 重聽單字", key=f"word_audio_{user_id}_{current_word_id}")

        # 上一個 / 下一個按鈕移到「重聽單字」下方
        nav1, nav2, nav3 = st.columns([1, 1.2, 1])

        with nav1:
            if st.button("⬅️ 上一個", use_container_width=True):
                st.session_state.card_index -= 1
                if st.session_state.card_index < 0:
                    st.session_state.card_index = len(filtered_df) - 1
                st.rerun()

        with nav2:
            st.write(f"第 {st.session_state.card_index + 1} / {len(filtered_df)} 個")

        with nav3:
            if st.button("下一個 ➡️", use_container_width=True):
                st.session_state.card_index += 1
                if st.session_state.card_index >= len(filtered_df):
                    st.session_state.card_index = 0
                st.rerun()

        st.divider()

        progress_rows = [
            ("使用者", user_name),
            ("狀態", safe_str(current_progress.get("status", "忘記了"))),
            ("熟練度", f"{safe_str(current_progress.get('mastery', 0))} / 100"),
            ("複習次數", safe_str(current_progress.get("review_count", 0))),
            ("答對次數", safe_str(current_progress.get("correct_count", 0))),
            ("答錯次數", safe_str(current_progress.get("wrong_count", 0))),
            ("連續答對", safe_str(current_progress.get("streak_correct", 0))),
            ("上次複習", safe_str(current_progress.get("last_review", ""))),
            ("下次複習", safe_str(current_progress.get("next_review", ""))),
        ]
        show_table_in_card("學習狀態", progress_rows, icon="📈", css_class="soft-card")

        current_level = safe_str(current_progress.get("status", "忘記了")) or "忘記了"
        streak_now = safe_str(current_progress.get("streak_correct", 0))

        st.markdown('<div class="section-title">單字等級挑戰</div>', unsafe_allow_html=True)
        show_table_in_card(
            "目前等級",
            [
                ("等級", current_level),
                ("升級方式", "到測驗模式挑戰，連續答對 2 次可升級 1 級"),
                ("降級規則", "測驗答錯會降級 1 級"),
                ("連續答對", f"{streak_now} / 2"),
                ("提醒", "很熟的單字仍會低頻出現，不會完全消失"),
            ],
            icon="🏅",
            css_class="soft-card-green"
        )

        st.markdown('</div>', unsafe_allow_html=True)

    with right_col:
        basic_rows = [
            ("年級", safe_str(current_word.get("grade", ""))),
            ("學期", safe_str(current_word.get("semester", ""))),
            ("課次", safe_str(current_word.get("lesson", ""))),
            ("標籤", safe_str(current_word.get("tags", ""))),
            ("補充說明", safe_str(current_word.get("note", ""))),
        ]
        show_table_in_card("基本資料", basic_rows, icon="🔵", css_class="soft-card")

        pos_en = safe_str(current_word.get("pos_en", "")).lower()
        pos = safe_str(current_word.get("pos", "")).lower()
        is_verb = ("verb" in pos_en) or ("verb" in pos) or ("動詞" in safe_str(current_word.get("pos_zh", "")))

        if is_verb:
            show_verb_rows_with_audio(current_word, user_id, current_word_id)

        plural = safe_str(current_word.get("plural", ""))
        plural_rule = safe_str(current_word.get("plural_rule", ""))

        if plural or plural_rule:
            noun_rows = [
                ("複數形", plural),
                ("複數規則", plural_rule),
            ]
            show_table_in_card("名詞 / 數字用法", noun_rows, icon="🟠", css_class="soft-card-orange")

        required_prepositions = safe_str(current_word.get("required_prepositions", ""))
        usage_patterns = safe_str(current_word.get("usage_patterns", ""))

        if required_prepositions or usage_patterns:
            usage_rows = [
                ("常搭配介系詞", required_prepositions),
                ("常用句型 / 用法", usage_patterns),
            ]
            show_table_in_card("常用用法", usage_rows, icon="🟣", css_class="soft-card-purple")

    render_examples(current_word, user_id, current_word_id)

    st.divider()
    with st.expander("查看目前範圍的單字與學習狀態"):
        display_columns = [
            "word", "meaning", "pos", "grade", "semester", "lesson",
            "status", "mastery", "review_count", "correct_count", "wrong_count",
            "last_review", "next_review"
        ]
        display_columns = [col for col in display_columns if col in filtered_df.columns]
        st.dataframe(filtered_df[display_columns], use_container_width=True, hide_index=True)

    render_backup_section(user_id, user_name)
