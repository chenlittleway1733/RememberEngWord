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


更新：測驗模式出題數
- 可選 5 題
- 可選 10 題
- 可選 20 題
- 可選任意題數
- 會顯示本次測驗進度、答對題數與完成正確率


更新：快速備份區加入測驗紀錄
- 側邊欄快速備份區現在可下載目前使用者的學習紀錄 progress CSV
- 側邊欄快速備份區現在可下載目前使用者的測驗紀錄 quiz_log CSV
- 上傳功能仍先維持上傳學習紀錄 progress CSV
- 完整還原仍建議用 progress.db


更新：加入測驗紀錄上傳
- 側邊欄快速備份區可上傳目前使用者 quiz_log CSV
- 主備份區也可上傳目前使用者 quiz_log CSV
- 測驗紀錄上傳只支援「覆蓋目前使用者測驗紀錄」
- 不提供合併模式，以避免 quiz_log 重複匯入造成錯題統計失真


更新：單一使用者完整備份 JSON
- 可一次下載目前使用者的完整備份 JSON
- 完整備份 JSON 同時包含 progress 學習紀錄與 quiz_log 測驗紀錄
- 可一次上傳完整備份 JSON
- 上傳完整備份會覆蓋目前使用者的 progress 與 quiz_log
- 原本分開下載 / 上傳 progress、quiz_log 的功能仍保留


更新：快速備份區簡化
- 側邊欄快速備份區最上方只放「完整備份 JSON」下載與上傳
- 完整備份 JSON 同時包含 progress 學習紀錄與 quiz_log 測驗紀錄
- 分開下載 / 上傳 progress、quiz_log 已移到「進階備份」裡
