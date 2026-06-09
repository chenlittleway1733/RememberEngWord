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

# ============================================================
# 單字等級挑戰規則
# ============================================================
LEVELS = ["忘記了", "不熟", "認識", "很熟"]

# 舊版狀態轉換成新版四級
STATUS_ALIASES = {
    "": "忘記了",
    "未學": "忘記了",
    "學習中": "不熟",
    "熟悉": "認識",
    "已掌握": "很熟",
    "忘記了": "忘記了",
    "不熟": "不熟",
    "認識": "認識",
    "很熟": "很熟",
}

LEVEL_MASTERY = {
    "忘記了": 0,
    "不熟": 35,
    "認識": 70,
    "很熟": 100,
}

LEVEL_NEXT_DAYS = {
    "忘記了": 1,
    "不熟": 2,
    "認識": 5,
    "很熟": 14,
}


def normalize_status(status: str) -> str:
    """把舊版或空白狀態轉成新版四級狀態。"""
    return STATUS_ALIASES.get(safe_str(status), "忘記了")


def level_index(status: str) -> int:
    """取得等級索引。"""
    return LEVELS.index(normalize_status(status))


def upgrade_status(status: str) -> str:
    """升級一級；很熟維持很熟。"""
    idx = min(level_index(status) + 1, len(LEVELS) - 1)
    return LEVELS[idx]


def downgrade_status(status: str) -> str:
    """降級一級；忘記了維持忘記了。"""
    idx = max(level_index(status) - 1, 0)
    return LEVELS[idx]


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

    ensure_memory_log_table()
    normalize_existing_progress_statuses()


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
            status TEXT DEFAULT '忘記了',
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


def ensure_memory_log_table():
    """
    建立 memory_log 記憶曲線歷程表。

    這張表會記錄每次測驗造成的單字等級變化：
    - 答錯：降級一級
    - 連續答對 2 次：升級一級
    - 很熟仍會低頻出現，不會完全消失
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            word_id TEXT NOT NULL,
            word TEXT,
            source TEXT,
            event_type TEXT,
            is_correct INTEGER,
            old_status TEXT,
            new_status TEXT,
            old_streak_correct INTEGER,
            new_streak_correct INTEGER,
            status_changed INTEGER,
            change_direction TEXT,
            note TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def normalize_existing_progress_statuses():
    """將既有 progress 的舊版狀態轉成新版四級狀態。"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE progress
        SET status = CASE
            WHEN status IS NULL OR status = '' OR status = '未學' THEN '忘記了'
            WHEN status = '學習中' THEN '不熟'
            WHEN status = '熟悉' THEN '認識'
            WHEN status = '已掌握' THEN '很熟'
            ELSE status
        END
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
                VALUES (?, ?, ?, ?, ?, ?, '忘記了', 0, 0, 0, 0, 0, NULL, NULL, ?)
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
    """
    根據測驗結果計算新等級。

    等級規則：
    1. 等級固定為：忘記了 → 不熟 → 認識 → 很熟
    2. 答錯：立刻降級一級
    3. 答對：連續答對 2 次才升級一級
    4. 很熟仍會出題，只是低頻出現
    """
    today = date.today()

    old_status = normalize_status(current_progress.get("status", "忘記了"))
    review_count = safe_int(current_progress.get("review_count"), 0) + 1
    correct_count = safe_int(current_progress.get("correct_count"), 0)
    wrong_count = safe_int(current_progress.get("wrong_count"), 0)
    old_streak_correct = safe_int(current_progress.get("streak_correct"), 0)
    new_streak_correct = old_streak_correct

    is_correct = level not in ["forgot", "wrong", "incorrect"]

    change_direction = "none"
    event_type = "測驗答對" if is_correct else "測驗答錯"

    if is_correct:
        correct_count += 1
        new_streak_correct = old_streak_correct + 1

        if new_streak_correct >= 2:
            new_status = upgrade_status(old_status)
            new_streak_correct = 0

            if new_status != old_status:
                change_direction = "up"
                note = f"🎉 連續答對 2 次，等級由「{old_status}」升為「{new_status}」。"
            else:
                note = f"✅ 已經是「{old_status}」，答對後維持最高等級。"
        else:
            new_status = old_status
            note = f"✅ 答對！連續答對 {new_streak_correct}/2 次，再答對一次可升級。"

    else:
        wrong_count += 1
        new_streak_correct = 0
        new_status = downgrade_status(old_status)

        if new_status != old_status:
            change_direction = "down"
            note = f"⚠️ 答錯，等級由「{old_status}」降為「{new_status}」。"
        else:
            note = f"⚠️ 答錯，目前已是「{old_status}」，維持最低等級。"

    status_changed = 1 if new_status != old_status else 0
    next_days = LEVEL_NEXT_DAYS.get(new_status, 1)
    next_review = today + timedelta(days=next_days)

    return {
        "old_status": old_status,
        "status": new_status,
        "mastery": LEVEL_MASTERY.get(new_status, 0),
        "review_count": review_count,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "old_streak_correct": old_streak_correct,
        "streak_correct": new_streak_correct,
        "last_review": today.isoformat(),
        "next_review": next_review.isoformat(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "is_correct": 1 if is_correct else 0,
        "event_type": event_type,
        "status_changed": status_changed,
        "change_direction": change_direction,
        "note": note,
    }


def log_memory_event(user_id: str, word_row: pd.Series, result: dict, source: str = "quiz"):
    """寫入一次單字記憶曲線歷程。"""
    ensure_memory_log_table()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO memory_log
        (user_id, word_id, word, source, event_type, is_correct,
         old_status, new_status, old_streak_correct, new_streak_correct,
         status_changed, change_direction, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            safe_str(word_row.get("word_id", "")),
            safe_str(word_row.get("word", "")),
            source,
            result.get("event_type", ""),
            safe_int(result.get("is_correct", 0)),
            result.get("old_status", ""),
            result.get("status", ""),
            safe_int(result.get("old_streak_correct", 0)),
            safe_int(result.get("streak_correct", 0)),
            safe_int(result.get("status_changed", 0)),
            result.get("change_direction", "none"),
            result.get("note", ""),
            result.get("updated_at", datetime.now().isoformat(timespec="seconds")),
        )
    )
    conn.commit()
    conn.close()


def update_progress(user_id: str, word_row: pd.Series, level: str, source: str = "quiz") -> dict:
    """
    更新學習紀錄，並回傳本次升級 / 降級訊息。

    level:
    - good：測驗答對
    - forgot：測驗答錯
    """
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

    log_memory_event(user_id, word_row, result, source=source)

    return result

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


def load_error_summary(user_id: str) -> pd.DataFrame:
    """
    讀取目前使用者的錯題統計。

    統計方式：
    - wrong_count：答錯次數
    - total_count：總作答次數
    - correct_count：答對次數
    - last_wrong_at：最近答錯時間
    - last_wrong_answer：最近一次錯誤答案
    - last_correct_answer：最近一次正確答案
    - last_question：最近一次錯誤題目

    錯題本會依 wrong_count 由多到少排序。
    """
    conn = get_conn()

    query = """
    WITH wrong_latest AS (
        SELECT
            user_id,
            word_id,
            MAX(id) AS last_wrong_id
        FROM quiz_log
        WHERE user_id = ? AND is_correct = 0
        GROUP BY user_id, word_id
    )
    SELECT
        q.word_id,
        q.word,
        SUM(CASE WHEN q.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
        SUM(CASE WHEN q.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
        COUNT(*) AS total_count,
        wlq.quiz_type AS last_quiz_type,
        wlq.question AS last_question,
        wlq.user_answer AS last_wrong_answer,
        wlq.correct_answer AS last_correct_answer,
        wlq.created_at AS last_wrong_at
    FROM quiz_log q
    JOIN wrong_latest w
        ON q.user_id = w.user_id AND q.word_id = w.word_id
    JOIN quiz_log wlq
        ON wlq.id = w.last_wrong_id
    WHERE q.user_id = ?
    GROUP BY
        q.word_id,
        q.word,
        wlq.quiz_type,
        wlq.question,
        wlq.user_answer,
        wlq.correct_answer,
        wlq.created_at
    HAVING wrong_count > 0
    ORDER BY wrong_count DESC, last_wrong_at DESC
    """

    df = pd.read_sql_query(query, conn, params=(user_id, user_id))
    conn.close()

    return df


def load_error_details(user_id: str, word_id: str | None = None) -> pd.DataFrame:
    """
    讀取答錯明細。
    如果指定 word_id，就只讀取該單字的錯題明細。
    """
    conn = get_conn()

    if word_id:
        df = pd.read_sql_query(
            """
            SELECT
                word,
                quiz_type,
                question,
                user_answer,
                correct_answer,
                created_at
            FROM quiz_log
            WHERE user_id = ? AND word_id = ? AND is_correct = 0
            ORDER BY id DESC
            """,
            conn,
            params=(user_id, word_id)
        )
    else:
        df = pd.read_sql_query(
            """
            SELECT
                word,
                quiz_type,
                question,
                user_answer,
                correct_answer,
                created_at
            FROM quiz_log
            WHERE user_id = ? AND is_correct = 0
            ORDER BY id DESC
            """,
            conn,
            params=(user_id,)
        )

    conn.close()
    return df


def get_error_word_ids(user_id: str) -> list[str]:
    """
    回傳目前使用者曾經答錯過的 word_id。
    測驗模式的「錯題本」出題來源會使用這個函式。
    """
    error_df = load_error_summary(user_id)
    if error_df.empty:
        return []
    return error_df["word_id"].dropna().astype(str).unique().tolist()



def load_memory_log(user_id: str | None = None) -> pd.DataFrame:
    """讀取記憶曲線歷程紀錄。"""
    ensure_memory_log_table()

    conn = get_conn()
    if user_id:
        df = pd.read_sql_query(
            "SELECT * FROM memory_log WHERE user_id = ? ORDER BY id DESC",
            conn,
            params=(user_id,)
        )
    else:
        df = pd.read_sql_query("SELECT * FROM memory_log ORDER BY id DESC", conn)
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
    3. error_notebook 錯題本統計快照

    注意：
    error_notebook 是由 quiz_log 計算出來的統計結果。
    還原時主要還原 progress 與 quiz_log；
    錯題本會依還原後的 quiz_log 重新產生。
    """
    progress_df = load_progress(user_id)
    quiz_log_df = load_quiz_log(user_id)
    error_df = load_error_summary(user_id)
    memory_df = load_memory_log(user_id)

    backup_data = {
        "backup_type": "vocab_app_user_backup",
        "version": "1.2",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "user_id": user_id,
        "user_name": user_name,
        "progress": progress_df.to_dict(orient="records"),
        "quiz_log": quiz_log_df.to_dict(orient="records"),
        "error_notebook": error_df.to_dict(orient="records"),
        "memory_log": memory_df.to_dict(orient="records"),
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
    error_records = backup_data.get("error_notebook", [])
    memory_records = backup_data.get("memory_log", [])

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

    # 匯入 memory_log。舊備份沒有 memory_log 時，只清空目前 memory_log，避免歷程混用。
    ensure_memory_log_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM memory_log WHERE user_id = ?", (user_id,))

    if isinstance(memory_records, list):
        for row in memory_records:
            word_id = safe_str(row.get("word_id", ""))
            if not word_id:
                continue

            cur.execute(
                """
                INSERT INTO memory_log
                (user_id, word_id, word, source, event_type, is_correct,
                 old_status, new_status, old_streak_correct, new_streak_correct,
                 status_changed, change_direction, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    word_id,
                    safe_str(row.get("word", "")),
                    safe_str(row.get("source", "")),
                    safe_str(row.get("event_type", "")),
                    safe_int(row.get("is_correct", 0)),
                    normalize_status(row.get("old_status", "忘記了")),
                    normalize_status(row.get("new_status", row.get("status", "忘記了"))),
                    safe_int(row.get("old_streak_correct", 0)),
                    safe_int(row.get("new_streak_correct", 0)),
                    safe_int(row.get("status_changed", 0)),
                    safe_str(row.get("change_direction", "")),
                    safe_str(row.get("note", "")),
                    safe_str(row.get("created_at", "")) or datetime.now().isoformat(timespec="seconds"),
                )
            )

    conn.commit()
    conn.close()

    return True, (
        f"已完成單一使用者完整還原："
        f"學習紀錄 {len(progress_records)} 筆，"
        f"測驗紀錄 {len(quiz_log_records)} 筆，"
        f"記憶曲線歷程 {len(memory_records) if isinstance(memory_records, list) else 0} 筆。"
        f"錯題本會由測驗紀錄自動重建；備份檔內含錯題本快照 {len(error_records)} 筆。"
    )


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
                normalize_status(row.get("status", "忘記了")),
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


def export_user_tables_backup(user_id: str) -> dict:
    """
    匯出 Google Sheets 分表備份資料。

    不輸出 error_notebook，因為錯題本可由 quiz_log 即時計算。
    """
    progress_df = load_progress(user_id)
    quiz_log_df = load_quiz_log(user_id)
    memory_log_df = load_memory_log(user_id)

    return {
        "progress": progress_df.to_dict(orient="records"),
        "quiz_log": quiz_log_df.to_dict(orient="records"),
        "memory_log": memory_log_df.to_dict(orient="records"),
    }


def import_user_tables_backup(user_id: str, tables_data: dict) -> tuple[bool, str]:
    """
    從 Google Sheets 分表資料還原單一使用者紀錄。

    固定覆蓋目前使用者：
    1. 覆蓋 progress
    2. 覆蓋 quiz_log
    3. 覆蓋 memory_log
    """
    progress_records = tables_data.get("progress", [])
    quiz_log_records = tables_data.get("quiz_log", [])
    memory_log_records = tables_data.get("memory_log", [])

    if not isinstance(progress_records, list):
        return False, "Google Sheets progress 格式不正確。"
    if not isinstance(quiz_log_records, list):
        return False, "Google Sheets quiz_log 格式不正確。"
    if not isinstance(memory_log_records, list):
        return False, "Google Sheets memory_log 格式不正確。"

    # progress
    progress_df = pd.DataFrame(progress_records)
    if not progress_df.empty:
        ok, msg = import_user_progress_from_csv(user_id, progress_df, import_mode="replace")
        if not ok:
            return False, f"progress 還原失敗：{msg}"
    else:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # quiz_log
    quiz_df = pd.DataFrame(quiz_log_records)
    if not quiz_df.empty:
        ok, msg = import_user_quiz_log_from_csv(user_id, quiz_df)
        if not ok:
            return False, f"quiz_log 還原失敗：{msg}"
    else:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM quiz_log WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # memory_log
    ensure_memory_log_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM memory_log WHERE user_id = ?", (user_id,))

    for row in memory_log_records:
        word_id = safe_str(row.get("word_id", ""))
        if not word_id:
            continue

        cur.execute(
            """
            INSERT INTO memory_log
            (user_id, word_id, word, source, event_type, is_correct,
             old_status, new_status, old_streak_correct, new_streak_correct,
             status_changed, change_direction, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                word_id,
                safe_str(row.get("word", "")),
                safe_str(row.get("source", "")),
                safe_str(row.get("event_type", "")),
                safe_int(row.get("is_correct", 0)),
                normalize_status(row.get("old_status", "忘記了")),
                normalize_status(row.get("new_status", row.get("status", "忘記了"))),
                safe_int(row.get("old_streak_correct", 0)),
                safe_int(row.get("new_streak_correct", 0)),
                safe_int(row.get("status_changed", 0)),
                safe_str(row.get("change_direction", "")),
                safe_str(row.get("note", "")),
                safe_str(row.get("created_at", "")) or datetime.now().isoformat(timespec="seconds"),
            )
        )

    conn.commit()
    conn.close()

    return True, (
        f"已從 Google Sheets 分表還原："
        f"progress {len(progress_records)} 筆，"
        f"quiz_log {len(quiz_log_records)} 筆，"
        f"memory_log {len(memory_log_records)} 筆。"
    )
