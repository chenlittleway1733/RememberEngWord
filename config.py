"""
config.py
全域設定檔。

這裡集中放：
1. 檔案路徑
2. 使用者清單
3. 發音設定
4. App 標題
"""

from pathlib import Path

APP_TITLE = "國中英文單字複習"

# 單字資料表固定使用 words.csv
DATA_PATH = Path("words.csv")

# SQLite 學習紀錄資料庫
DB_PATH = Path("progress.db")

# 發音快取資料夾
AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

# edge-tts 英文語音
VOICE = "en-US-JennyNeural"

# 使用者清單
USERS = {
    "daughter": "女兒",
    "son": "兒子",
    "test": "測試帳",
}
