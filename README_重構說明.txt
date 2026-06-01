國中英文單字智慧複習系統：重構版

使用方式：
1. 把整個資料夾內容上傳到 GitHub repository。
2. Streamlit Cloud 的 Main file path 設為 app.py。
3. requirements.txt 保留在同一層。
4. words.csv 必須放在 app.py 同一層。

主要檔案：
- app.py：主入口
- config.py：設定
- utils.py：共用工具
- data.py：單字資料
- database.py：SQLite 學習紀錄與測驗紀錄
- audio.py：發音
- quiz.py：測驗邏輯
- ui_common.py：共用 UI
- ui_cards.py：單字卡畫面
- ui_quiz.py：測驗畫面
# 階段功能說明：SQLite 學習紀錄與備份機制

## 一、階段目標

本階段主要目標是建立一套可供家庭自用的學習紀錄保存機制，讓系統能記錄不同使用者的單字學習狀況、測驗結果與錯題來源。

目前系統不使用 Google Sheets 或 Supabase，而是採用 SQLite 資料庫檔案 `progress.db` 儲存學習紀錄。這種方式設定簡單、適合少量使用者，也方便下載完整備份。

---

## 二、資料儲存方式

系統目前使用三種主要資料來源：

| 資料   | 儲存位置           | 說明                       |
| ---- | -------------- | ------------------------ |
| 單字資料 | `words.csv`    | 儲存單字、中文、詞性、三態、例句、測驗選項    |
| 學習紀錄 | `progress.db`  | 儲存使用者學習進度與測驗紀錄           |
| 發音快取 | `audio_cache/` | 儲存 edge-tts 產生的單字與例句 mp3 |

其中最重要的是 `progress.db`，它會在 Streamlit App 執行時自動建立。

---

## 三、`progress.db` 儲存內容

`progress.db` 目前包含三個主要資料表：

### 1. `users`

用來記錄使用者帳號。

目前預設三個使用者：

| user_id  | 使用者 |
| -------- | --- |
| daughter | 女兒  |
| son      | 兒子  |
| test     | 測試帳 |

---

### 2. `progress`

用來記錄每位使用者對每個單字的學習狀況。

主要欄位包含：

| 欄位             | 說明            |
| -------------- | ------------- |
| user_id        | 使用者 ID        |
| word_id        | 單字唯一 ID       |
| word           | 單字            |
| status         | 未學、學習中、熟悉、已掌握 |
| mastery        | 熟練度           |
| review_count   | 複習次數          |
| correct_count  | 答對次數          |
| wrong_count    | 答錯次數          |
| streak_correct | 連續答對次數        |
| last_review    | 上次複習日期        |
| next_review    | 下次複習日期        |

當使用者在單字卡按下「忘記了 / 不熟 / 認識 / 很熟」時，系統會更新這張表。

---

### 3. `quiz_log`

用來記錄每一次測驗作答結果。

主要欄位包含：

| 欄位             | 說明      |
| -------------- | ------- |
| user_id        | 使用者 ID  |
| word_id        | 單字唯一 ID |
| word           | 單字      |
| quiz_type      | 題型      |
| question       | 題目      |
| correct_answer | 正確答案    |
| user_answer    | 使用者作答   |
| is_correct     | 是否答對    |
| created_at     | 作答時間    |

`quiz_log` 是未來錯題本功能的重要來源。

---

## 四、備份功能

由於 Streamlit Cloud 的執行環境不是永久資料庫空間，`progress.db` 不會自動回寫到 GitHub，也不能保證永遠保存，因此系統加入備份功能。

目前備份功能分成兩種：

### 1. 依使用者下載學習紀錄

在側邊欄使用者下方，可快速下載目前使用者的學習紀錄。

例如：

| 使用者 | 下載檔案                           |
| --- | ------------------------------ |
| 女兒  | `daughter_progress_backup.csv` |
| 兒子  | `son_progress_backup.csv`      |
| 測試帳 | `test_progress_backup.csv`     |

這種 CSV 檔適合查看個別使用者的學習進度，也可以用來匯入單一帳號紀錄。

---

### 2. 完整下載 `progress.db`

系統也提供完整資料庫備份功能，可下載：

```text
progress.db
```

這是最完整的備份，包含：

* 使用者資料
* 所有人的學習進度
* 所有人的測驗紀錄
* 未來錯題本所需資料

若系統資料遺失，可以透過上傳 `progress.db` 進行完整還原。

---

## 五、上傳還原功能

系統目前支援兩種還原方式：

### 1. 上傳單一使用者學習紀錄 CSV

適合只還原某一位使用者的 `progress` 學習進度。

例如：

* 還原女兒紀錄
* 還原兒子紀錄
* 還原測試帳紀錄

匯入時系統會依目前選定的使用者寫入資料，避免不同使用者資料混在一起。

---

### 2. 上傳完整 `progress.db`

適合完整還原整個系統。

這種方式會覆蓋目前的 `progress.db`，包含：

* 女兒資料
* 兒子資料
* 測試帳資料
* 測驗紀錄
* 錯題來源資料

因此系統會要求使用者確認後才能執行完整還原。

---

## 六、GitHub 與 Streamlit Cloud 的關係

GitHub 只儲存程式碼與固定資料檔，例如：

```text
app.py
config.py
data.py
database.py
ui_cards.py
ui_quiz.py
words.csv
requirements.txt
```

但 `progress.db` 是程式在 Streamlit Cloud 執行時產生的檔案，不會自動出現在 GitHub repository 中。

因此在 GitHub 看不到以下檔案是正常的：

```text
progress.db
audio_cache/
```

---

## 七、使用注意事項

如果 App 幾天沒有使用，資料不一定會消失；但如果 Streamlit Cloud 重新部署、重啟或重建執行環境，`progress.db` 有可能遺失。

因此建議定期備份：

| 情境              | 建議                   |
| --------------- | -------------------- |
| 平常使用            | 每週下載一次 `progress.db` |
| 段考前密集練習         | 每天或每次練習後下載           |
| 上傳新版本到 GitHub 前 | 先下載 `progress.db`    |
| 測驗紀錄很多時         | 下載完整 `progress.db`   |

---

## 八、本階段完成狀態

本階段已完成：

* 使用 SQLite 儲存學習紀錄
* 支援女兒、兒子、測試帳三個使用者
* 各使用者學習紀錄分開保存
* 記錄單字熟練度與下次複習日
* 記錄測驗作答結果
* 支援個別使用者 CSV 下載
* 支援個別使用者 CSV 上傳
* 支援完整 `progress.db` 下載
* 支援完整 `progress.db` 還原
* 說明 GitHub 看不到 `progress.db` 是正常現象

---

## 九、下一階段方向

下一階段可進入「錯題本功能」。

錯題本會根據 `quiz_log` 中答錯的紀錄，自動整理：

* 最常錯的單字
* 最常錯的題型
* 最近答錯的題目
* 使用者錯誤答案
* 正確答案
* 錯題加強練習

這樣測驗資料就不只是記錄，而能真正用來安排後續複習。
