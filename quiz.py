"""
quiz.py
處理測驗出題邏輯。

這裡只處理：
1. 哪些單字可以出題
2. 如何從 words.csv 產生題目
3. 如何產生選項
4. 如何比對答案

不要把 Streamlit 畫面放在這裡。
"""

import random
import hashlib
import pandas as pd

from utils import safe_str


def make_choice_options(correct_answer: str, distractors: list[str]) -> list[str]:
    """產生選擇題選項，包含正確答案與誘答，並隨機排序。"""
    options = []
    correct_answer = safe_str(correct_answer)
    if correct_answer:
        options.append(correct_answer)

    for item in distractors:
        item = safe_str(item)
        if item and item not in options:
            options.append(item)

    options = options[:4]
    random.shuffle(options)
    return options


def get_quiz_pool(source_df: pd.DataFrame, quiz_type: str) -> pd.DataFrame:
    """依題型過濾可出題單字。"""
    df = source_df.copy()

    if quiz_type in ["英翻中選擇題", "中翻英選擇題"]:
        return df[df["word"].astype(str).str.strip() != ""]

    if quiz_type == "動詞變化選擇題":
        pos_text = (
            df.get("pos", "").astype(str).str.lower() +
            df.get("pos_en", "").astype(str).str.lower() +
            df.get("pos_zh", "").astype(str)
        )
        return df[
            (pos_text.str.contains("verb") | pos_text.str.contains("動詞")) &
            (
                (df.get("past", "").astype(str).str.strip() != "") |
                (df.get("past_participle", "").astype(str).str.strip() != "") |
                (df.get("present_participle", "").astype(str).str.strip() != "")
            )
        ]

    if quiz_type == "例句填空":
        cloze_cols = [f"cloze_{i}" for i in range(1, 6) if f"cloze_{i}" in df.columns]
        if not cloze_cols:
            return df.iloc[0:0]

        mask = False
        for col in cloze_cols:
            mask = mask | (df[col].astype(str).str.strip() != "")
        return df[mask]

    return df


def build_quiz_question(word_row: pd.Series, quiz_type: str) -> dict:
    """從 words.csv 欄位建立一道題目。"""
    word = safe_str(word_row.get("word", ""))
    meaning = safe_str(word_row.get("meaning", ""))

    if quiz_type == "英翻中選擇題":
        distractors = [
            word_row.get("meaning_option_1", ""),
            word_row.get("meaning_option_2", ""),
            word_row.get("meaning_option_3", ""),
        ]
        return {
            "quiz_type": quiz_type,
            "question": f"「{word}」的中文意思是？",
            "correct_answer": meaning,
            "options": make_choice_options(meaning, distractors),
            "hint": "",
        }

    if quiz_type == "中翻英選擇題":
        context = safe_str(word_row.get("word_question_context", ""))
        if context:
            question = f"請選出正確英文：{context}"
        else:
            question = f"「{meaning}」的英文是？"

        distractors = [
            word_row.get("word_option_1", ""),
            word_row.get("word_option_2", ""),
            word_row.get("word_option_3", ""),
        ]
        return {
            "quiz_type": quiz_type,
            "question": question,
            "correct_answer": word,
            "options": make_choice_options(word, distractors),
            "hint": "",
        }

    if quiz_type == "動詞變化選擇題":
        candidates = []

        if safe_str(word_row.get("past", "")):
            candidates.append((
                "過去式",
                safe_str(word_row.get("past", "")),
                [
                    word_row.get("past_option_1", ""),
                    word_row.get("past_option_2", ""),
                    word_row.get("past_option_3", ""),
                ]
            ))

        if safe_str(word_row.get("past_participle", "")):
            candidates.append((
                "過去分詞",
                safe_str(word_row.get("past_participle", "")),
                [
                    word_row.get("past_participle_option_1", ""),
                    word_row.get("past_participle_option_2", ""),
                    word_row.get("past_participle_option_3", ""),
                ]
            ))

        if safe_str(word_row.get("present_participle", "")):
            candidates.append((
                "現在分詞",
                safe_str(word_row.get("present_participle", "")),
                [
                    word_row.get("present_participle_option_1", ""),
                    word_row.get("present_participle_option_2", ""),
                    word_row.get("present_participle_option_3", ""),
                ]
            ))

        if safe_str(word_row.get("verb_change_type", "")):
            candidates.append((
                "變化規則",
                safe_str(word_row.get("verb_change_type", "")),
                [
                    word_row.get("verb_change_option_1", ""),
                    word_row.get("verb_change_option_2", ""),
                    word_row.get("verb_change_option_3", ""),
                ]
            ))

        if not candidates:
            return {}

        item_name, correct, distractors = random.choice(candidates)
        base_form = safe_str(word_row.get("base_form", "")) or word

        if item_name == "變化規則":
            question = f"「{word}」的動詞變化屬於哪一種？"
            hint = safe_str(word_row.get("verb_change_note", ""))
        else:
            question = f"「{base_form}」的{item_name}是？"
            hint = safe_str(word_row.get("verb_change_note", ""))

        return {
            "quiz_type": quiz_type,
            "question": question,
            "correct_answer": correct,
            "options": make_choice_options(correct, distractors),
            "hint": hint,
        }

    if quiz_type == "例句填空":
        available = []
        for i in range(1, 6):
            c = safe_str(word_row.get(f"cloze_{i}", ""))
            a = safe_str(word_row.get(f"cloze_answer_{i}", ""))
            h = safe_str(word_row.get(f"cloze_hint_{i}", ""))
            if c and a:
                available.append((c, a, h))

        if not available:
            return {}

        cloze, answer, hint = random.choice(available)
        return {
            "quiz_type": quiz_type,
            "question": cloze,
            "correct_answer": answer,
            "options": [],
            "hint": hint,
        }

    return {}


def prepare_new_quiz_question(source_df: pd.DataFrame, quiz_type: str):
    """建立新測驗題。"""
    pool = get_quiz_pool(source_df, quiz_type)
    if pool.empty:
        return {}

    word_row = pool.sample(1).iloc[0]
    question = build_quiz_question(word_row, quiz_type)

    if not question:
        return {}

    question["word_row"] = word_row.to_dict()
    return question
