"""
utils.py
共用小工具函式。
"""

import pandas as pd


def safe_str(value) -> str:
    """把任何資料安全轉成字串，避免 None / NaN 造成錯誤。"""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def safe_int(value, default=0) -> int:
    """把任何資料安全轉成整數。"""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def normalize_answer(value: str) -> str:
    """測驗答案比對用：去空白、轉小寫。"""
    return safe_str(value).strip().lower()
