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


更新：第四階段錯題本
- 新增 ui_errors.py
- 主功能新增「錯題本」
- 錯題本會從 quiz_log 的答錯紀錄產生
- 錯題本顯示錯誤次數、最近錯誤題目、錯誤答案、正確答案
- 測驗模式的出題來源新增「錯題本」
- 可下載目前使用者錯題本 CSV


更新：完整備份 JSON 整合錯題本
- 完整備份 JSON 現在包含 progress、quiz_log、error_notebook
- error_notebook 是錯題本統計快照，方便人工查看
- 還原時主要還原 progress 與 quiz_log
- 錯題本會依 quiz_log 自動重新產生，因此不需要另外匯入錯題本 CSV


更新：統計報表與聽力測驗
- 新增 ui_stats.py
- 新增 ui_listening.py
- 主功能新增「統計報表」
- 主功能新增「聽力測驗」
- 統計報表顯示學習總覽、測驗正確率、各題型正確率、最常錯單字
- 聽力測驗支援聽單字選英文
- 聽力測驗支援 5 / 10 / 20 / 任意題
- 聽力測驗答題結果會寫入 quiz_log，並更新 progress


修正：聽力測驗下一題播放上一題音檔
- 每題新增 question_id
- 下一題 / 跳過時會清除 last_listening_autoplay_key
- 自動播放會依 question_id 判斷，避免沿用上一題音檔


修正：聽力測驗下一題會先播放上一題
- 修改 audio.py 的 autoplay_audio()
- 播放新音檔前會先停止頁面上既有的 audio
- 避免上一題音檔殘留播放
