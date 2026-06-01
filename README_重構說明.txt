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
