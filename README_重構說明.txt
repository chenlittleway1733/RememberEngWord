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


修正：聽力測驗音檔播放策略
- iPad Safari / Streamlit iframe 對自動播放限制較多
- 本版取消聽力測驗每題自動播放
- 改為每題按「播放本題音檔」
- 避免下一題先播放上一題音檔
- audio.py 回到穩定播放方式


更新：例句中文翻譯預設隱藏
- 單字卡例句區只先顯示英文例句
- 每個例句都有「顯示中文 / 隱藏中文」按鈕
- 按下後才顯示該句中文翻譯
- 保留例句發音按鈕


更新：Google Sheets 雲端備份 / 還原
- 新增 google_backup.py
- 快速備份區新增 Google Sheets 雲端備份
- 可將目前使用者完整備份 JSON 上傳到 Google Sheets
- 可從 Google Sheets 讀取完整備份 JSON 並還原
- Google Sheets 讀取失敗時，仍可用本機完整備份 JSON 還原
- requirements.txt 新增 requests
- 新增 google_apps_script_備份API範本.txt
- 需要在 Streamlit Secrets 設定：
  GOOGLE_SCRIPT_URL
  GOOGLE_BACKUP_TOKEN


更新：等級挑戰版
- 單字等級改為四級：忘記了、不熟、認識、很熟
- 單字卡只顯示目前等級，不提供手動改等級按鈕
- 孩子必須透過測驗挑戰提升單字等級
- 測驗答錯會降級一級：很熟→認識→不熟→忘記了
- 測驗連續答對 2 次才升級一級：忘記了→不熟→認識→很熟
- 很熟的單字仍會低頻出現，不會完全消失
- 測驗出題依等級加權：忘記了 8、不熟 5、認識 2、很熟 1
- 新增 memory_log 記憶曲線歷程表
- 每次測驗造成的等級變化都會記錄到 memory_log
- 統計報表新增記憶曲線歷程
- 完整備份 JSON 新增 memory_log


更新：快速備份區顯示 memory_log
- 快速備份區文字改為完整備份包含 progress、quiz_log、error_notebook、memory_log
- Google Sheets 讀取備份時會顯示記憶曲線歷程 memory_log 筆數
- 上傳本機完整備份 JSON 時也會顯示 memory_log 筆數


更新：單字卡版面順序調整
- 詞性說明移到「重聽單字」按鈕上方
- 上一個 / 下一個移到「重聽單字」按鈕下方
- 學習狀態與等級挑戰區塊移到導覽按鈕下方
