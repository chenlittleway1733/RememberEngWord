"""
google_backup.py
Google Sheets 雲端資料庫備份功能。

新版設計：
不再把所有資料塞進單一 backup_json 儲存格。
改成將資料展開到 Google Sheets 多個工作表：

1. progress      每個帳號、每個單字目前狀態
2. quiz_log      每次測驗紀錄
3. memory_log    每次升級 / 降級 / 連續答對歷程
4. backup_meta   每個帳號最後同步摘要

仍然保留本機完整 JSON 下載 / 上傳功能。
Google Sheets 主要作為可讀、可還原的雲端資料庫。
"""

import requests
import streamlit as st


def get_google_backup_config() -> tuple[str, str]:
    """讀取 Streamlit Secrets 中的 Google Apps Script 設定。"""
    script_url = st.secrets.get("GOOGLE_SCRIPT_URL", "")
    token = st.secrets.get("GOOGLE_BACKUP_TOKEN", "")
    return script_url, token


def is_google_backup_configured() -> bool:
    """判斷是否已設定 Google Sheets 雲端備份。"""
    script_url, token = get_google_backup_config()
    return bool(script_url and token)


def _post_to_google(payload: dict) -> tuple[bool, str, dict]:
    """送出 POST 到 Google Apps Script Web App。"""
    script_url, token = get_google_backup_config()

    if not script_url or not token:
        return False, "尚未設定 GOOGLE_SCRIPT_URL 或 GOOGLE_BACKUP_TOKEN。", {}

    payload = dict(payload)
    payload["token"] = token

    try:
        resp = requests.post(script_url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if data.get("ok"):
            return True, data.get("message", "Google Sheets 操作成功。"), data

        return False, data.get("message", "Google Sheets 回傳失敗。"), data

    except Exception as e:
        return False, f"連線 Google Sheets 失敗：{e}", {}


def save_user_tables_to_google(
    user_id: str,
    user_name: str,
    progress_records: list[dict],
    quiz_log_records: list[dict],
    memory_log_records: list[dict],
) -> tuple[bool, str, dict]:
    """
    將單一使用者資料分表寫入 Google Sheets。

    寫入方式：
    1. 先刪除該 user_id 舊資料
    2. 再寫入新的 progress / quiz_log / memory_log
    3. 更新 backup_meta
    """
    payload = {
        "action": "save_tables",
        "user_id": user_id,
        "user_name": user_name,
        "progress": progress_records,
        "quiz_log": quiz_log_records,
        "memory_log": memory_log_records,
    }

    return _post_to_google(payload)


def load_user_tables_from_google(user_id: str) -> tuple[bool, str, dict]:
    """
    從 Google Sheets 讀取單一使用者分表資料。

    回傳格式：
    {
        "backup_type": "vocab_app_google_tables",
        "version": "2.0",
        "user_id": "...",
        "user_name": "...",
        "progress": [...],
        "quiz_log": [...],
        "memory_log": [...]
    }
    """
    payload = {
        "action": "load_tables",
        "user_id": user_id,
    }

    return _post_to_google(payload)
