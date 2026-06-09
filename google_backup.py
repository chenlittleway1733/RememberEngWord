"""
google_backup.py
Google Sheets 雲端備份功能。

本檔案負責透過 Google Apps Script Web App 讀寫完整備份 JSON。

需要在 Streamlit Secrets 設定：
GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/xxxx/exec"
GOOGLE_BACKUP_TOKEN = "你的token"
"""

import json
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


def save_user_backup_to_google(user_id: str, user_name: str, backup_json_text: str) -> tuple[bool, str, dict]:
    """將單一使用者完整備份 JSON 上傳到 Google Sheets。"""
    script_url, token = get_google_backup_config()

    if not script_url or not token:
        return False, "尚未設定 GOOGLE_SCRIPT_URL 或 GOOGLE_BACKUP_TOKEN。", {}

    payload = {
        "token": token,
        "action": "save_backup",
        "user_id": user_id,
        "user_name": user_name,
        "backup_json": backup_json_text,
    }

    try:
        resp = requests.post(script_url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get("ok"):
            return True, data.get("message", "已上傳到 Google Sheets。"), data

        return False, data.get("message", "Google Sheets 回傳失敗。"), data

    except Exception as e:
        return False, f"上傳 Google Sheets 失敗：{e}", {}


def load_user_backup_from_google(user_id: str) -> tuple[bool, str, dict]:
    """從 Google Sheets 讀取單一使用者完整備份 JSON。"""
    script_url, token = get_google_backup_config()

    if not script_url or not token:
        return False, "尚未設定 GOOGLE_SCRIPT_URL 或 GOOGLE_BACKUP_TOKEN。", {}

    payload = {
        "token": token,
        "action": "load_backup",
        "user_id": user_id,
    }

    try:
        resp = requests.post(script_url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            return False, data.get("message", "Google Sheets 找不到備份。"), {}

        backup_json = data.get("backup_json", "")

        if not backup_json:
            return False, "Google Sheets 中的 backup_json 是空的。", {}

        if isinstance(backup_json, dict):
            backup_data = backup_json
        else:
            backup_data = json.loads(backup_json)

        if backup_data.get("backup_type") != "vocab_app_user_backup":
            return False, "讀到的 JSON 不是本系統完整備份格式。", {}

        return True, data.get("message", "已從 Google Sheets 讀取備份。"), backup_data

    except json.JSONDecodeError:
        return False, "Google Sheets 中的 backup_json 格式錯誤，無法解析 JSON。", {}
    except Exception as e:
        return False, f"讀取 Google Sheets 備份失敗：{e}", {}
