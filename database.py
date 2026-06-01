"""
database.py
處理 SQLite 學習資料庫 progress.db。

負責：
1. 建立 users / progress / quiz_log
2. 舊版 progress.db 自動遷移
3. 讀取與更新學習進度
4. 記錄測驗結果
5. 匯入 / 匯出備份
"""

import sqlite3
import json
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd

from config import DB_PATH, USERS
from utils import safe_str, safe_int


def get_conn():
    """連線到 SQLite 資料庫。"""
    return sqlite3.connect(DB_PATH)


def init_db():
    """
    建立 users 與 progress 資料表。

    如果舊版 progress.db 沒有 user_id 欄位，會自動把舊資料轉到 daughter 帳號。
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            role TEXT DEFAULT 'learner',
            created_at TEXT
        )
        """
    )

    now = datetime.now().isoformat(timespec="seconds")
    for user_id, user_name in USERS.items():
        role = "test" if user_id == "test" else "learner"
        cur.execute(
            """
            INSERT OR IGNORE INTO users (user_id, user_name, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, user_name, role, now)
        )

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='progress'")
    progress_exists = cur.fetchone() is not None

    if progress_exists:
        cur.execute("PRAGMA table_info(progress)")
        existing_columns = [row[1] for row in cur.fetchall()]

        if "user_id" not in existing_columns:
            backup_table = f"progress_old_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            cur.execute(f"ALTER TABLE progress RENAME TO {backup_table}")
            create_progress_table(cur)

            cur.execute(f"PRAGMA table_info({backup_table})")
            old_columns = [row[1] for row in cur.fetchall()]

            def old_col(name, default_sql):
                return name if name in old_columns else default_sql

            cur.execute(
                f"""
                INSERT OR IGNORE INTO progress
                (user_id, word_id, word, grade, semester, lesson, status, mastery,
                 review_count, correct_count, wrong_count, streak_correct,
                 last_review, next_review, updated_at)
                SELECT
                    'daughter' AS user_id,
                    {old_col('word_id', "''")} AS word_id,
                    {old_col('word', "''")} AS word,
                    {old_col('grade', "''")} AS grade,
                    {old_col('semester', "''")} AS semester,
                    {old_col('lesson', "''")} AS lesson,
                    {old_col('status', "'未學'")} AS status,
                    {old_col('mastery', "0")} AS mastery,
                    {old_col('review_count', "0")} AS review_count,
                    {old_col('correct_count', "0")} AS correct_count,
                    {old_col('wrong_count', "0")} AS wrong_count,
                    {old_col('streak_correct', "0")} AS streak_correct,
                    {old_col('last_review', "NULL")} AS last_review,
                    {old_col('next_review', "NULL")} AS next_review,
                    {old_col('updated_at', "''")} AS updated_at
                FROM {backup_table}
                WHERE {old_col('word_id', "''")} != ''
                """
            )
    else:
        create_progress_table(cur)

    conn.commit()
    conn.close()


def create_progress_table(cur):
    """建立新版 progress 資料表。"""
    cur.execute(
        """
        CREATE TABLE progress (
            user_id TEXT NOT NULL,
            word_id TEXT NOT NULL,
            word TEXT,
            grade TEXT,
            semester TEXT,
            lesson TEXT,
            status TEXT DEFAULT '未學',
            mastery INTEGER DEFAULT 0,
            review_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak_correct INTEGER DEFAULT 0,
            last_review TEXT,
            next_review TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, word_id)
        )
        """
    )


def ensure_quiz_log_table():
    """建立 quiz_log 測驗紀錄表。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            word_id TEXT NOT NULL,
            word TEXT,
            quiz_type TEXT,
            question TEXT,
            correct_answer TEXT,
            user_answer TEXT,
            is_correct INTEGER,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_progress_for_words(df: pd.DataFrame):
    """確保每位使用者、每個單字都有一筆 progress 紀錄。"""
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")

    for user_id in USERS.keys():
        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT OR IGNORE INTO progress
                (user_id, word_id, word, grade, semester, lesson, status, mastery,
                 review_count, correct_count, wrong_count, streak_correct,
                 last_review, next_review, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '未學', 0, 0, 0, 0, 0, NULL, NULL, ?)
                """,
                (
                    user_id,
                    safe_str(row["word_id"]),
                    safe_str(row.get("word", "")),
                    safe_str(row.get("grade", "")),
                    safe_str(row.get("semester", "")),
                    safe_str(row.get("lesson", "")),
                    now,
                )
            )

    conn.commit()
    conn.close()


def load_users() -> pd.DataFrame:
    """讀取使用者資料。"""
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM users ORDER BY user_id", conn)
    conn.close()
    return df


def load_progress(user_id: str | None = None) -> pd.DataFrame:
    """讀取學習紀錄。"""
    conn = get_conn()

    if user_id:
        df = pd.read_sql_query(
            "SELECT * FROM progress WHERE user_id = ?",
            conn,
            params=(user_id,)
        )
    else:
        df = pd.read_sql_query("SELECT * FROM progress", conn)

    conn.close()
    return df


def get_progress(user_id: str, word_id: str) -> dict:
    """讀取某位使用者某個單字的學習紀錄。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM progress WHERE user_id = ? AND word_id = ?",
        (user_id, word_id)
    )
    row = cur.fetchone()
    columns = [desc[0] for desc in cur.description] if cur.description else []
    conn.close()

    if row is None:
        return {}

    return dict(zip(columns, row))


def calculate_review_result(level: str, current_progress: dict) -> dict:
    """根據熟悉度按鈕計算新紀錄。"""
    today = date.today()

    mastery = safe_int(current_progress.get("mastery"), 0)
    review_count = safe_int(current_progress.get("review_count"), 0)
    correct_count = safe_int(current_progress.get("correct_count"), 0)
    wrong_count = safe_int(current_progress.get("wrong_count"), 0)
    streak_correct = safe_int(current_progress.get("streak_correct"), 0)

    review_count += 1

    if level == "forgot":
        mastery = max(0, mastery - 20)
        wrong_count += 1
        streak_correct = 0
        next_days = 1
        status = "學習中"
    elif level == "hard":
        mastery = min(100, mastery + 5)
        correct_count += 1
        streak_correct += 1
        next_days = 2
        status = "學習中"
    elif level == "good":
        mastery = min(100, mastery + 15)
        correct_count += 1
        streak_correct += 1
        next_days = 4
        status = "熟悉"
    elif level == "easy":
        mastery = min(100, mastery + 25)
        correct_count += 1
        streak_correct += 1
        if streak_correct >= 5:
            next_days = 30
            status = "已掌握"
        elif streak_correct >= 3:
            next_days = 14
            status = "熟悉"
        else:
            next_days = 7
            status = "熟悉"
    else:
        next_days = 1
        status = "學習中"

    next_review = today + timedelta(days=next_days)

    return {
        "status": status,
        "mastery": mastery,
        "review_count": review_count,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "streak_correct": streak_correct,
        "last_review": today.isoformat(),
        "next_review": next_review.isoformat(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def update_progress(user_id: str, word_row: pd.Series, level: str):
    """更新學習紀錄。"""
    word_id = safe_str(word_row["word_id"])
    current_progress = get_progress(user_id, word_id)
    result = calculate_review_result(level, current_progress)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE progress
        SET
            word = ?,
            grade = ?,
            semester = ?,
            lesson = ?,
            status = ?,
            mastery = ?,
            review_count = ?,
            correct_count = ?,
            wrong_count = ?,
            streak_correct = ?,
            last_review = ?,
            next_review = ?,
            updated_at = ?
        WHERE user_id = ? AND word_id = ?
        """,
        (
            safe_str(word_row.get("word", "")),
            safe_str(word_row.get("grade", "")),
            safe_str(word_row.get("semester", "")),
            safe_str(word_row.get("lesson", "")),
            result["status"],
            result["mastery"],
            result["review_count"],
            result["correct_count"],
            result["wrong_count"],
            result["streak_correct"],
            result["last_review"],
            result["next_review"],
            result["updated_at"],
            user_id,
            word_id,
        )
    )
    conn.commit()
    conn.close()


def log_quiz_result(user_id: str, word_row: pd.Series, quiz_type: str, question: str,
                    correct_answer: str, user_answer: str, is_correct: bool):
    """寫入一次測驗作答紀錄。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO quiz_log
        (user_id, word_id, word, quiz_type, question, correct_answer, user_answer, is_correct, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            safe_str(word_row.get("word_id", "")),
            safe_str(word_row.get("word", "")),
            quiz_type,
            question,
            correct_answer,
            user_answer,
            1 if is_correct else 0,
            datetime.now().isoformat(timespec="seconds"),
        )
    )
    conn.commit()
    conn.close()


def load_quiz_log(user_id: str | None = None) -> pd.DataFrame:
    """讀取測驗紀錄。"""
    conn = get_conn()
    if user_id:
        df = pd.read_sql_query(
            "SELECT * FROM quiz_log WHERE user_id = ? ORDER BY id DESC",
            conn,
            params=(user_id,)
        )
    else:
        df = pd.read_sql_query("SELECT * FROM quiz_log ORDER BY id DESC", conn)
    conn.close()
    return df


def import_user_quiz_log_from_csv(user_id: str, csv_df: pd.DataFrame) -> tuple[bool, str]:
    """
    匯入單一使用者的測驗紀錄 CSV。

    本功能固定使用「覆蓋目前使用者測驗紀錄」：
    1. 先刪除目前 user_id 的 quiz_log
    2. 再匯入上傳的 CSV
    3. 即使 CSV 裡有其他 user_id，也會強制改成目前選定 user_id

    這樣可以避免合併匯入造成重複測驗紀錄。
    """
    required_cols = [
        "word_id", "word", "quiz_type", "question",
        "correct_answer", "user_answer", "is_correct", "created_at"
    ]

    missing_cols = [col for col in required_cols if col not in csv_df.columns]
    if missing_cols:
        return False, f"CSV 缺少欄位：{', '.join(missing_cols)}"

    conn = get_conn()
    cur = conn.cursor()

    # 固定覆蓋目前使用者測驗紀錄
    cur.execute("DELETE FROM quiz_log WHERE user_id = ?", (user_id,))

    for _, row in csv_df.iterrows():
        word_id = safe_str(row.get("word_id", ""))
        if not word_id:
            continue

        cur.execute(
            """
            INSERT INTO quiz_log
            (user_id, word_id, word, quiz_type, question, correct_answer,
             user_answer, is_correct, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                word_id,
                safe_str(row.get("word", "")),
                safe_str(row.get("quiz_type", "")),
                safe_str(row.get("question", "")),
                safe_str(row.get("correct_answer", "")),
                safe_str(row.get("user_answer", "")),
                safe_int(row.get("is_correct", 0)),
                safe_str(row.get("created_at", "")) or datetime.now().isoformat(timespec="seconds"),
            )
        )

    conn.commit()
    conn.close()

    return True, f"已覆蓋匯入 {len(csv_df)} 筆測驗紀錄到目前帳號。"


def export_user_combined_backup(user_id: str, user_name: str) -> bytes:
    """
    匯出單一使用者的完整備份 JSON。
    內容包含：
    1. progress 學習紀錄
    2. quiz_log 測驗紀錄

    這個 JSON 適合用來「一次下載」與「一次上傳還原」。
    """
    progress_df = load_progress(user_id)
    quiz_log_df = load_quiz_log(user_id)

    backup_data = {
        "backup_type": "vocab_app_user_backup",
        "version": "1.0",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "user_id": user_id,
        "user_name": user_name,
        "progress": progress_df.to_dict(orient="records"),
        "quiz_log": quiz_log_df.to_dict(orient="records"),
    }

    return json.dumps(backup_data, ensure_ascii=False, indent=2).encode("utf-8")


def import_user_combined_backup(user_id: str, backup_data: dict) -> tuple[bool, str]:
    """
    匯入單一使用者完整備份 JSON。

    固定採用覆蓋模式：
    1. 覆蓋目前使用者 progress
    2. 覆蓋目前使用者 quiz_log

    即使 JSON 裡的 user_id 不同，也會強制匯入到目前選定的使用者。
    """
    if backup_data.get("backup_type") != "vocab_app_user_backup":
        return False, "這不是本系統的單一使用者備份 JSON。"

    progress_records = backup_data.get("progress", [])
    quiz_log_records = backup_data.get("quiz_log", [])

    if not isinstance(progress_records, list):
        return False, "JSON 中的 progress 格式不正確。"

    if not isinstance(quiz_log_records, list):
        return False, "JSON 中的 quiz_log 格式不正確。"

    progress_df = pd.DataFrame(progress_records)
    quiz_log_df = pd.DataFrame(quiz_log_records)

    # 匯入 progress
    if not progress_df.empty:
        ok, msg = import_user_progress_from_csv(user_id, progress_df, import_mode="replace")
        if not ok:
            return False, f"學習紀錄匯入失敗：{msg}"
    else:
        # 如果備份沒有 progress，也仍然清空目前 progress，符合覆蓋語意
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # 匯入 quiz_log
    if not quiz_log_df.empty:
        ok, msg = import_user_quiz_log_from_csv(user_id, quiz_log_df)
        if not ok:
            return False, f"測驗紀錄匯入失敗：{msg}"
    else:
        # 如果備份沒有 quiz_log，也清空目前 quiz_log
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM quiz_log WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    return True, f"已完成單一使用者完整還原：學習紀錄 {len(progress_records)} 筆，測驗紀錄 {len(quiz_log_records)} 筆。"


def import_user_progress_from_csv(user_id: str, csv_df: pd.DataFrame, import_mode: str = "replace") -> tuple[bool, str]:
    """匯入單一使用者的學習紀錄 CSV。"""
    required_cols = [
        "word_id", "word", "grade", "semester", "lesson", "status",
        "mastery", "review_count", "correct_count", "wrong_count",
        "streak_correct", "last_review", "next_review", "updated_at"
    ]

    missing_cols = [col for col in required_cols if col not in csv_df.columns]
    if missing_cols:
        return False, f"CSV 缺少欄位：{', '.join(missing_cols)}"

    conn = get_conn()
    cur = conn.cursor()

    if import_mode == "replace":
        cur.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))

    for _, row in csv_df.iterrows():
        word_id = safe_str(row.get("word_id", ""))
        if not word_id:
            continue

        cur.execute(
            """
            INSERT OR REPLACE INTO progress
            (user_id, word_id, word, grade, semester, lesson, status, mastery,
             review_count, correct_count, wrong_count, streak_correct,
             last_review, next_review, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                word_id,
                safe_str(row.get("word", "")),
                safe_str(row.get("grade", "")),
                safe_str(row.get("semester", "")),
                safe_str(row.get("lesson", "")),
                safe_str(row.get("status", "未學")) or "未學",
                safe_int(row.get("mastery", 0)),
                safe_int(row.get("review_count", 0)),
                safe_int(row.get("correct_count", 0)),
                safe_int(row.get("wrong_count", 0)),
                safe_int(row.get("streak_correct", 0)),
                safe_str(row.get("last_review", "")),
                safe_str(row.get("next_review", "")),
                safe_str(row.get("updated_at", "")) or datetime.now().isoformat(timespec="seconds"),
            )
        )

    conn.commit()
    conn.close()
    return True, f"已匯入 {len(csv_df)} 筆紀錄到目前帳號。"


def restore_full_db(uploaded_file) -> tuple[bool, str]:
    """還原完整 progress.db。"""
    try:
        uploaded_bytes = uploaded_file.getvalue()

        test_path = Path("progress_upload_test.db")
        test_path.write_bytes(uploaded_bytes)

        test_conn = sqlite3.connect(test_path)
        test_cur = test_conn.cursor()
        test_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [row[0] for row in test_cur.fetchall()]
        test_conn.close()
        test_path.unlink(missing_ok=True)

        if "progress" not in table_names:
            return False, "這個 db 檔沒有 progress 資料表，可能不是本程式的備份檔。"

        DB_PATH.write_bytes(uploaded_bytes)
        init_db()
        ensure_quiz_log_table()
        return True, "已還原完整 progress.db。請重新整理頁面確認資料。"

    except Exception as e:
        return False, f"還原失敗：{e}"
