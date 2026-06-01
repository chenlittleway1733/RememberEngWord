"""
data.py
處理 words.csv。

負責：
1. 讀取 words.csv
2. 檢查必要欄位
3. 建立 word_id
4. 依使用者選擇篩選單字
"""

import hashlib
import pandas as pd
import streamlit as st

from config import DATA_PATH
from utils import safe_str


def make_word_id(row: pd.Series) -> str:
    """
    建立單字唯一 ID。
    使用年級、學期、課次、單字組合，避免同一單字出現在不同課時混在一起。
    """
    parts = [
        safe_str(row.get("grade", "")),
        safe_str(row.get("semester", "")),
        safe_str(row.get("lesson", "")),
        safe_str(row.get("word", "")),
    ]
    raw_id = "|".join(parts)
    return hashlib.md5(raw_id.encode("utf-8")).hexdigest()


@st.cache_data
def load_words() -> pd.DataFrame:
    """讀取 words.csv，並補齊必要欄位。"""
    if not DATA_PATH.exists():
        st.error("找不到 words.csv，請確認 words.csv 和 app.py 放在同一個資料夾。")
        return pd.DataFrame()

    df = pd.read_csv(DATA_PATH)
    df = df.fillna("")

    required_columns = ["word", "meaning", "pos", "grade", "semester", "lesson"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        st.error(f"words.csv 缺少必要欄位：{', '.join(missing_columns)}")
        return pd.DataFrame()

    if "pos_en" not in df.columns:
        df["pos_en"] = df["pos"]

    if "pos_zh" not in df.columns:
        df["pos_zh"] = df["pos"]

    df["word_id"] = df.apply(make_word_id, axis=1)
    return df


def merge_words_with_progress(words_df: pd.DataFrame, progress_df: pd.DataFrame) -> pd.DataFrame:
    """把 words.csv 與目前使用者的 progress 資料合併。"""
    merged_df = words_df.merge(
        progress_df,
        on="word_id",
        how="left",
        suffixes=("", "_progress")
    )

    for col in [
        "status", "mastery", "review_count", "correct_count", "wrong_count",
        "streak_correct", "last_review", "next_review"
    ]:
        if col not in merged_df.columns:
            merged_df[col] = ""

    merged_df["status"] = merged_df["status"].replace("", "未學")
    merged_df["mastery"] = merged_df["mastery"].replace("", 0)
    merged_df["review_count"] = merged_df["review_count"].replace("", 0)
    merged_df["correct_count"] = merged_df["correct_count"].replace("", 0)
    merged_df["wrong_count"] = merged_df["wrong_count"].replace("", 0)
    merged_df["streak_correct"] = merged_df["streak_correct"].replace("", 0)

    return merged_df.fillna("")


def filter_words(df: pd.DataFrame, filter_state: dict, today_str: str) -> pd.DataFrame:
    """依側邊欄篩選條件與學習模式篩選單字。"""
    filtered_df = df.copy()

    selected_grade = filter_state.get("grade", "全部")
    selected_semester = filter_state.get("semester", "全部")
    selected_lesson = filter_state.get("lesson", "全部")
    selected_pos = filter_state.get("pos", "全部")
    keyword = filter_state.get("keyword", "")
    mode = filter_state.get("mode", "全部單字")

    if selected_grade != "全部":
        filtered_df = filtered_df[filtered_df["grade"] == selected_grade]

    if selected_semester != "全部":
        filtered_df = filtered_df[filtered_df["semester"] == selected_semester]

    if selected_lesson != "全部":
        filtered_df = filtered_df[filtered_df["lesson"] == selected_lesson]

    if selected_pos != "全部":
        filtered_df = filtered_df[filtered_df["pos_zh"] == selected_pos]

    if keyword.strip():
        keyword_lower = keyword.strip().lower()
        search_columns = [
            "word", "meaning", "pos", "pos_zh", "tags", "note",
            "required_prepositions", "usage_patterns",
            "example_1", "example_2", "example_3", "example_4", "example_5",
            "example_zh_1", "example_zh_2", "example_zh_3", "example_zh_4", "example_zh_5"
        ]
        search_columns = [col for col in search_columns if col in filtered_df.columns]

        mask = False
        for col in search_columns:
            mask = mask | filtered_df[col].astype(str).str.lower().str.contains(keyword_lower, na=False)

        filtered_df = filtered_df[mask]

    if mode == "今日複習":
        filtered_df = filtered_df[
            (filtered_df["next_review"].astype(str) == "") |
            (filtered_df["next_review"].astype(str) <= today_str)
        ]
    elif mode == "未學單字":
        filtered_df = filtered_df[filtered_df["status"].astype(str).isin(["", "未學"])]
    elif mode == "學習中":
        filtered_df = filtered_df[filtered_df["status"].astype(str).isin(["學習中", "熟悉"])]
    elif mode == "已掌握":
        filtered_df = filtered_df[filtered_df["status"].astype(str) == "已掌握"]

    return filtered_df
