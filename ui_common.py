"""
ui_common.py
共用 UI 元件。
"""

from datetime import date
import json
import pandas as pd
import streamlit as st

from config import DB_PATH
from utils import safe_str
from database import (
    load_progress,
    load_quiz_log,
    import_user_progress_from_csv,
    import_user_quiz_log_from_csv,
    export_user_combined_backup,
    import_user_combined_backup,
    export_user_tables_backup,
    import_user_tables_backup,
    restore_full_db,
)
from google_backup import (
    is_google_backup_configured,
    save_user_tables_to_google,
    load_user_tables_from_google,
)


def apply_global_styles():
    """套用全域 CSS。"""
    st.markdown(
        """
        <style>
        .main-title {
            font-size: 2.0rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }
        .small-caption {
            color: #888;
            font-size: 0.95rem;
            margin-bottom: 1.0rem;
        }
        .word-card {
            border: 1px solid rgba(120,140,180,0.28);
            border-radius: 18px;
            padding: 22px;
            margin-bottom: 14px;
            background: linear-gradient(135deg, rgba(80,120,200,0.10), rgba(255,255,255,0.035));
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        }
        .soft-card {
            border: 1px solid rgba(120,140,180,0.25);
            border-radius: 16px;
            padding: 14px 16px;
            margin-bottom: 14px;
            background: rgba(80,120,200,0.055);
        }
        .soft-card-green {
            border: 1px solid rgba(60,160,120,0.28);
            border-radius: 16px;
            padding: 14px 16px;
            margin-bottom: 14px;
            background: rgba(60,160,120,0.060);
        }
        .soft-card-orange {
            border: 1px solid rgba(180,130,60,0.28);
            border-radius: 16px;
            padding: 14px 16px;
            margin-bottom: 14px;
            background: rgba(180,130,60,0.065);
        }
        .soft-card-purple {
            border: 1px solid rgba(150,90,190,0.28);
            border-radius: 16px;
            padding: 14px 16px;
            margin-bottom: 14px;
            background: rgba(150,90,190,0.060);
        }
        .soft-title {
            font-size: 1.15rem;
            font-weight: 900;
            margin-bottom: 0.65rem;
        }
        .word-text {
            text-align: center;
            font-size: 3.0rem;
            font-weight: 900;
            line-height: 1.1;
            margin-bottom: 0.6rem;
        }
        .meaning-text {
            text-align: center;
            font-size: 1.45rem;
            font-weight: 700;
            color: #BBBBBB;
        }
        .section-title {
            font-size: 1.18rem;
            font-weight: 800;
            margin-top: 0.8rem;
            margin-bottom: 0.4rem;
        }
        .example-card {
            border: 1px solid rgba(160,160,160,0.25);
            border-radius: 14px;
            padding: 12px 14px;
            margin-bottom: 10px;
            background-color: rgba(255,255,255,0.035);
        }
        .example-en {
            font-size: 1.02rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .example-zh {
            font-size: 0.95rem;
            color: #AAAAAA;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.45rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def show_info_table(rows: list[tuple[str, str]]):
    """用表格顯示資料。"""
    clean_rows = [(k, v) for k, v in rows if safe_str(v)]
    if not clean_rows:
        return
    df = pd.DataFrame(clean_rows, columns=["項目", "內容"])
    st.dataframe(df, hide_index=True, use_container_width=True)


def open_card(title: str, icon: str = "📌", css_class: str = "soft-card"):
    """開啟一個簡單色塊卡片標題。"""
    st.markdown(
        f"""
        <div class="{css_class}">
            <div class="soft-title">{icon} {title}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def show_table_in_card(title: str, rows: list[tuple[str, str]], icon: str = "📌", css_class: str = "soft-card"):
    """穩定版卡片：標題色塊 + Streamlit 原生表格。"""
    open_card(title, icon=icon, css_class=css_class)
    show_info_table(rows)


def render_sidebar_user_selector(users_df: pd.DataFrame):
    """側邊欄：選擇使用者。"""
    st.sidebar.header("👤 使用者")
    user_options = {
        f"{row['user_name']}（{row['user_id']}）": row["user_id"]
        for _, row in users_df.iterrows()
    }
    selected_user_label = st.sidebar.selectbox("選擇使用者", list(user_options.keys()))
    selected_user_id = user_options[selected_user_label]
    selected_user_name = selected_user_label.split("（")[0]
    return selected_user_id, selected_user_name


def render_sidebar_quick_backup(user_id: str, user_name: str):
    """
    側邊欄：快速備份 / 還原目前使用者紀錄。

    設計原則：
    1. 一般使用者只需要用「完整備份 JSON」。
    2. 完整備份 JSON 會同時包含：
       - progress 學習紀錄
       - quiz_log 測驗紀錄
    3. 分開下載 / 上傳 progress、quiz_log 放到「進階備份」裡，避免畫面混亂。
    """
    st.sidebar.markdown("### 💾 快速備份")

    try:
        # ----------------------------------------------------
        # 主要功能：單一使用者完整備份 JSON
        # ----------------------------------------------------
        combined_backup = export_user_combined_backup(user_id, user_name)

        st.sidebar.download_button(
            label=f"⬇️ 下載{user_name}完整備份",
            data=combined_backup,
            file_name=f"{user_id}_full_backup.json",
            mime="application/json",
            key=f"sidebar_download_full_backup_{user_id}",
            use_container_width=True
        )

        st.sidebar.caption("完整備份包含：學習狀態、測驗紀錄、錯題本快照、記憶曲線歷程。")

        with st.sidebar.expander(f"⬆️ 上傳{user_name}完整備份"):
            st.caption("完整備份會同時覆蓋目前使用者的學習狀態、測驗紀錄與記憶曲線歷程。")

            uploaded_combined = st.file_uploader(
                "選擇完整備份 JSON",
                type=["json"],
                key=f"sidebar_upload_full_backup_{user_id}"
            )

            confirm_combined = st.checkbox(
                f"確認覆蓋{user_name}完整紀錄",
                key=f"sidebar_confirm_full_backup_{user_id}"
            )

            if uploaded_combined is not None:
                try:
                    backup_data = json.load(uploaded_combined)

                    st.write("備份檔資訊：")
                    st.write(f"匯出時間：{backup_data.get('exported_at', '')}")
                    st.write(f"原使用者：{backup_data.get('user_name', '')}（{backup_data.get('user_id', '')}）")
                    st.write(f"學習狀態 progress：{len(backup_data.get('progress', []))} 筆")
                    st.write(f"測驗紀錄 quiz_log：{len(backup_data.get('quiz_log', []))} 筆")
                    st.write(f"錯題本快照 error_notebook：{len(backup_data.get('error_notebook', []))} 筆")
                    st.write(f"記憶曲線歷程 memory_log：{len(backup_data.get('memory_log', []))} 筆")

                    if st.button(
                        "開始覆蓋匯入完整備份",
                        disabled=not confirm_combined,
                        key=f"sidebar_start_full_backup_import_{user_id}",
                        use_container_width=True
                    ):
                        ok, msg = import_user_tables_backup(user_id, backup_data)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

                except Exception as e:
                    st.error(f"讀取完整備份 JSON 失敗：{e}")


        # ----------------------------------------------------
        # Google Sheets 雲端備份 / 還原
        # ----------------------------------------------------
        with st.sidebar.expander("☁️ Google Sheets 雲端備份"):
            if not is_google_backup_configured():
                st.warning("尚未設定 Google Sheets 雲端備份。請先在 Streamlit Secrets 設定 GOOGLE_SCRIPT_URL 與 GOOGLE_BACKUP_TOKEN。")
            else:
                st.caption("可將目前使用者資料分表存到 Google Sheets，也可從 Google Sheets 分表讀回還原。Google Sheets 會建立 progress、quiz_log、memory_log、backup_meta，方便直接查看。")

                if st.button(
                    f"☁️ 同步{user_name}資料到 Google Sheets",
                    key=f"sidebar_google_upload_{user_id}",
                    use_container_width=True
                ):
                    try:
                        tables = export_user_tables_backup(user_id)

                        ok, msg, data = save_user_tables_to_google(
                            user_id=user_id,
                            user_name=user_name,
                            progress_records=tables.get("progress", []),
                            quiz_log_records=tables.get("quiz_log", []),
                            memory_log_records=tables.get("memory_log", []),
                        )

                        if ok:
                            st.success(msg)
                            st.write(f"progress：{len(tables.get('progress', []))} 筆")
                            st.write(f"quiz_log：{len(tables.get('quiz_log', []))} 筆")
                            st.write(f"memory_log：{len(tables.get('memory_log', []))} 筆")
                        else:
                            st.error(msg)

                    except Exception as e:
                        st.error(f"產生或上傳 Google Sheets 分表資料失敗：{e}")

                st.divider()

                if st.button(
                    f"☁️ 從 Google Sheets 讀取{user_name}分表資料",
                    key=f"sidebar_google_load_{user_id}",
                    use_container_width=True
                ):
                    ok, msg, backup_data = load_user_tables_from_google(user_id)

                    if ok:
                        st.session_state[f"google_backup_preview_{user_id}"] = backup_data
                        st.success(msg)
                    else:
                        st.error(msg)
                        st.info("如果 Google Sheets 分表資料有問題，請改用上方「上傳完整備份 JSON」還原本機備份檔。")

                preview_key = f"google_backup_preview_{user_id}"
                if preview_key in st.session_state:
                    backup_data = st.session_state[preview_key]

                    st.write("Google Sheets 分表資料資訊：")
                    st.write(f"同步時間：{backup_data.get('exported_at', backup_data.get('synced_at', ''))}")
                    st.write(f"原使用者：{backup_data.get('user_name', '')}（{backup_data.get('user_id', '')}）")
                    st.write(f"progress：{len(backup_data.get('progress', []))} 筆")
                    st.write(f"quiz_log：{len(backup_data.get('quiz_log', []))} 筆")
                    st.write(f"memory_log：{len(backup_data.get('memory_log', []))} 筆")

                    confirm_cloud_restore = st.checkbox(
                        f"確認用 Google Sheets 分表資料覆蓋{user_name}目前紀錄",
                        key=f"confirm_google_restore_{user_id}"
                    )

                    if st.button(
                        "開始從 Google Sheets 分表還原",
                        disabled=not confirm_cloud_restore,
                        key=f"start_google_restore_{user_id}",
                        use_container_width=True
                    ):
                        ok, msg = import_user_tables_backup(user_id, backup_data)

                        if ok:
                            st.success(msg)
                            del st.session_state[preview_key]
                            st.rerun()
                        else:
                            st.error(msg)

        # ----------------------------------------------------
        # 進階功能：分開處理 progress 與 quiz_log
        # ----------------------------------------------------
        with st.sidebar.expander("進階備份：分開下載 / 上傳"):
            st.caption("通常不用使用這裡；一般建議使用上方完整備份。")

            sidebar_selected_progress = load_progress(user_id)
            sidebar_quiz_log = load_quiz_log(user_id)

            sidebar_csv_bytes = sidebar_selected_progress.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=f"⬇️ 下載{user_name}學習紀錄 CSV",
                data=sidebar_csv_bytes,
                file_name=f"{user_id}_progress_backup.csv",
                mime="text/csv",
                key=f"sidebar_download_progress_csv_{user_id}",
                use_container_width=True
            )

            sidebar_quiz_bytes = sidebar_quiz_log.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=f"⬇️ 下載{user_name}測驗紀錄 CSV",
                data=sidebar_quiz_bytes,
                file_name=f"{user_id}_quiz_log_backup.csv",
                mime="text/csv",
                key=f"sidebar_download_quiz_log_csv_{user_id}",
                use_container_width=True
            )

            st.divider()

            st.markdown("**上傳學習紀錄 CSV**")
            sidebar_import_mode_label = st.radio(
                "學習紀錄匯入方式",
                ["覆蓋", "合併"],
                index=0,
                horizontal=True,
                key=f"sidebar_import_mode_{user_id}"
            )
            sidebar_import_mode = "replace" if sidebar_import_mode_label == "覆蓋" else "merge"

            sidebar_uploaded_csv = st.file_uploader(
                "選擇 progress CSV",
                type=["csv"],
                key=f"sidebar_upload_progress_csv_{user_id}"
            )

            sidebar_confirm_import = st.checkbox(
                f"確認匯入{user_name}學習紀錄",
                key=f"sidebar_confirm_progress_import_{user_id}"
            )

            if sidebar_uploaded_csv is not None:
                try:
                    sidebar_preview_df = pd.read_csv(sidebar_uploaded_csv)
                    st.write("預覽前 3 筆：")
                    st.dataframe(sidebar_preview_df.head(3), use_container_width=True, hide_index=True)

                    if st.button(
                        "開始匯入學習紀錄",
                        disabled=not sidebar_confirm_import,
                        key=f"sidebar_start_progress_import_{user_id}",
                        use_container_width=True
                    ):
                        ok, msg = import_user_progress_from_csv(
                            user_id,
                            sidebar_preview_df,
                            import_mode=sidebar_import_mode
                        )
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"讀取 progress CSV 失敗：{e}")

            st.divider()

            st.markdown("**上傳測驗紀錄 CSV**")
            st.caption("測驗紀錄固定採用覆蓋模式，避免重複匯入。")

            sidebar_uploaded_quiz_csv = st.file_uploader(
                "選擇 quiz_log CSV",
                type=["csv"],
                key=f"sidebar_upload_quiz_log_csv_{user_id}"
            )

            sidebar_confirm_quiz_import = st.checkbox(
                f"確認覆蓋{user_name}測驗紀錄",
                key=f"sidebar_confirm_quiz_import_{user_id}"
            )

            if sidebar_uploaded_quiz_csv is not None:
                try:
                    sidebar_quiz_preview_df = pd.read_csv(sidebar_uploaded_quiz_csv)
                    st.write("預覽前 3 筆：")
                    st.dataframe(sidebar_quiz_preview_df.head(3), use_container_width=True, hide_index=True)

                    if st.button(
                        "開始覆蓋匯入測驗紀錄",
                        disabled=not sidebar_confirm_quiz_import,
                        key=f"sidebar_start_quiz_import_{user_id}",
                        use_container_width=True
                    ):
                        ok, msg = import_user_quiz_log_from_csv(
                            user_id,
                            sidebar_quiz_preview_df
                        )
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"讀取 quiz_log CSV 失敗：{e}")

    except Exception as e:
        st.sidebar.warning(f"快速備份功能暫時無法使用：{e}")

def render_sidebar_filters(merged_df: pd.DataFrame) -> dict:
    """側邊欄：學習範圍與模式。"""
    st.sidebar.divider()
    st.sidebar.header("📚 選擇學習範圍")

    mode = st.sidebar.radio(
        "學習模式",
        ["全部單字", "今日複習", "忘記了", "不熟", "認識", "很熟"],
        index=0
    )

    grade_options = ["全部"] + sorted([x for x in merged_df["grade"].unique().tolist() if safe_str(x)])
    selected_grade = st.sidebar.selectbox("年級", grade_options)

    temp_df = merged_df.copy()
    if selected_grade != "全部":
        temp_df = temp_df[temp_df["grade"] == selected_grade]

    semester_options = ["全部"] + sorted([x for x in temp_df["semester"].unique().tolist() if safe_str(x)])
    selected_semester = st.sidebar.selectbox("學期", semester_options)

    if selected_semester != "全部":
        temp_df = temp_df[temp_df["semester"] == selected_semester]

    lesson_options = ["全部"] + sorted([x for x in temp_df["lesson"].unique().tolist() if safe_str(x)])
    selected_lesson = st.sidebar.selectbox("課次", lesson_options)

    if selected_lesson != "全部":
        temp_df = temp_df[temp_df["lesson"] == selected_lesson]

    pos_options = ["全部"] + sorted([x for x in temp_df["pos_zh"].unique().tolist() if safe_str(x)])
    selected_pos = st.sidebar.selectbox("詞性", pos_options)

    keyword = st.sidebar.text_input("搜尋單字、中文、例句、用法或標籤")

    return {
        "mode": mode,
        "grade": selected_grade,
        "semester": selected_semester,
        "lesson": selected_lesson,
        "pos": selected_pos,
        "keyword": keyword,
    }


def render_sidebar_stats(merged_df: pd.DataFrame, user_name: str):
    """
    側邊欄：顯示目前使用者的學習統計。

    等級挑戰版統計：
    - 忘記了
    - 不熟
    - 認識
    - 很熟
    """
    today_str = date.today().isoformat()

    if merged_df is None or merged_df.empty:
        st.sidebar.divider()
        st.sidebar.markdown("### 📊 學習統計")
        st.sidebar.write("目前沒有學習紀錄。")
        return

    status_col = merged_df["status"].astype(str) if "status" in merged_df.columns else pd.Series([], dtype=str)

    due_today = 0
    if "next_review" in merged_df.columns:
        due_today = len(
            merged_df[
                (merged_df["next_review"].astype(str) == "") |
                (merged_df["next_review"].astype(str) <= today_str)
            ]
        )

    forgot = len(merged_df[status_col == "忘記了"])
    hard = len(merged_df[status_col == "不熟"])
    known = len(merged_df[status_col == "認識"])
    mastered = len(merged_df[status_col == "很熟"])

    st.sidebar.divider()
    st.sidebar.markdown("### 📊 學習統計")
    st.sidebar.write(f"目前使用者：**{user_name}**")
    st.sidebar.write(f"這位使用者目前共有 **{len(merged_df)}** 筆學習紀錄。")
    st.sidebar.write(f"今日可複習：**{due_today}**")
    st.sidebar.write(f"忘記了：**{forgot}**")
    st.sidebar.write(f"不熟：**{hard}**")
    st.sidebar.write(f"認識：**{known}**")
    st.sidebar.write(f"很熟：**{mastered}**")

def render_backup_section(user_id: str, user_name: str):
    """主畫面下方：完整備份 / 上傳區。"""
    with st.expander("備份 / 上傳更新學習紀錄"):
        st.write("目前學習紀錄存在 `progress.db`。")
        st.warning("如果部署在 Streamlit Cloud，重新部署或休眠後資料可能遺失，建議定期下載備份。")

        all_progress = load_progress()
        selected_progress = load_progress(user_id)
        selected_quiz_log = load_quiz_log(user_id)

        tab_download, tab_upload_user, tab_upload_db = st.tabs([
            "下載備份",
            "上傳單一帳號紀錄",
            "還原完整資料庫"
        ])

        with tab_download:
            st.subheader("下載備份")
            st.write(f"目前使用者：**{user_name}**")
            st.write(f"這位使用者目前共有 **{len(selected_progress)}** 筆學習紀錄。")
            st.dataframe(selected_progress, use_container_width=True, hide_index=True)

            csv_bytes = selected_progress.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=f"下載 {user_name} 的學習紀錄 CSV",
                data=csv_bytes,
                file_name=f"{user_id}_progress_backup.csv",
                mime="text/csv",
                key=f"download_csv_{user_id}"
            )

            quiz_csv_bytes = selected_quiz_log.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=f"下載 {user_name} 的測驗紀錄 CSV",
                data=quiz_csv_bytes,
                file_name=f"{user_id}_quiz_log_backup.csv",
                mime="text/csv",
                key=f"download_quiz_log_{user_id}"
            )

            combined_backup = export_user_combined_backup(user_id, user_name)
            st.download_button(
                label=f"下載 {user_name} 的完整備份 JSON",
                data=combined_backup,
                file_name=f"{user_id}_full_backup.json",
                mime="application/json",
                key=f"download_combined_{user_id}"
            )

            all_csv_bytes = all_progress.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="下載全部使用者學習紀錄 CSV",
                data=all_csv_bytes,
                file_name="all_progress_backup.csv",
                mime="text/csv",
                key="download_all_csv"
            )

            if DB_PATH.exists():
                with open(DB_PATH, "rb") as db_file:
                    st.download_button(
                        label="下載 progress.db 完整備份",
                        data=db_file,
                        file_name="progress.db",
                        mime="application/octet-stream",
                        key="download_db"
                    )
            else:
                st.error("目前找不到 progress.db。")

        with tab_upload_user:
            st.subheader("上傳單一使用者完整備份")
            st.info("完整備份 JSON 會同時覆蓋目前使用者的 progress 學習狀態、quiz_log 測驗紀錄與 memory_log 記憶曲線歷程。")

            uploaded_combined_json = st.file_uploader(
                f"上傳 {user_name} 的完整備份 JSON",
                type=["json"],
                key=f"upload_combined_json_{user_id}"
            )

            confirm_combined_import = st.checkbox(
                f"我確認要覆蓋 {user_name} 的完整紀錄",
                key=f"confirm_combined_import_{user_id}"
            )

            if uploaded_combined_json is not None:
                try:
                    backup_data = json.load(uploaded_combined_json)

                    st.write("完整備份資訊：")
                    st.write(f"匯出時間：{backup_data.get('exported_at', '')}")
                    st.write(f"原使用者：{backup_data.get('user_name', '')}（{backup_data.get('user_id', '')}）")
                    st.write(f"學習狀態 progress：{len(backup_data.get('progress', []))} 筆")
                    st.write(f"測驗紀錄 quiz_log：{len(backup_data.get('quiz_log', []))} 筆")
                    st.write(f"錯題本快照 error_notebook：{len(backup_data.get('error_notebook', []))} 筆")
                    st.write(f"記憶曲線歷程 memory_log：{len(backup_data.get('memory_log', []))} 筆")

                    if st.button("開始覆蓋匯入完整備份", disabled=not confirm_combined_import, key=f"start_combined_import_{user_id}"):
                        ok, msg = import_user_tables_backup(user_id, backup_data)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

                except Exception as e:
                    st.error(f"讀取完整備份 JSON 失敗：{e}")

            st.divider()
            st.subheader("分開上傳學習紀錄 progress")
            st.info(f"這裡只會更新目前選定帳號：{user_name}（{user_id}）。")

            import_mode_label = st.radio(
                "匯入方式",
                ["覆蓋目前帳號紀錄", "合併更新目前帳號紀錄"],
                index=0,
                key=f"import_mode_{user_id}"
            )
            import_mode = "replace" if import_mode_label == "覆蓋目前帳號紀錄" else "merge"

            uploaded_csv = st.file_uploader(
                f"上傳 {user_name} 的 progress CSV 備份",
                type=["csv"],
                key=f"upload_csv_{user_id}"
            )
            confirm_user_import = st.checkbox(
                f"我確認要把上傳的 CSV 匯入到 {user_name} 帳號",
                key=f"confirm_user_import_{user_id}"
            )

            if uploaded_csv is not None:
                try:
                    preview_df = pd.read_csv(uploaded_csv)
                    st.write("CSV 預覽：")
                    st.dataframe(preview_df.head(10), use_container_width=True, hide_index=True)

                    if st.button("開始匯入單一帳號紀錄", disabled=not confirm_user_import, key=f"start_import_{user_id}"):
                        ok, msg = import_user_progress_from_csv(user_id, preview_df, import_mode=import_mode)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"讀取 CSV 失敗：{e}")


            st.divider()
            st.subheader("上傳測驗紀錄 quiz_log")
            st.info("測驗紀錄上傳固定採用覆蓋模式：會先清除目前使用者的 quiz_log，再匯入 CSV。")

            uploaded_quiz_csv = st.file_uploader(
                f"上傳 {user_name} 的 quiz_log CSV 備份",
                type=["csv"],
                key=f"upload_quiz_csv_{user_id}"
            )

            confirm_quiz_import = st.checkbox(
                f"我確認要覆蓋 {user_name} 的測驗紀錄",
                key=f"confirm_quiz_import_{user_id}"
            )

            if uploaded_quiz_csv is not None:
                try:
                    quiz_preview_df = pd.read_csv(uploaded_quiz_csv)
                    st.write("quiz_log CSV 預覽：")
                    st.dataframe(quiz_preview_df.head(10), use_container_width=True, hide_index=True)

                    if st.button("開始覆蓋匯入測驗紀錄", disabled=not confirm_quiz_import, key=f"start_quiz_import_{user_id}"):
                        ok, msg = import_user_quiz_log_from_csv(user_id, quiz_preview_df)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"讀取 quiz_log CSV 失敗：{e}")

        with tab_upload_db:
            st.subheader("還原完整 progress.db")
            st.error("這個功能會覆蓋整個 progress.db，包含女兒、兒子、測試帳所有資料。")

            uploaded_db = st.file_uploader(
                "上傳 progress.db 完整備份",
                type=["db", "sqlite", "sqlite3"],
                key="upload_full_db"
            )
            confirm_db_restore = st.checkbox(
                "我確認要覆蓋目前完整 progress.db",
                key="confirm_db_restore"
            )

            if uploaded_db is not None:
                st.write(f"已選擇檔案：{uploaded_db.name}")
                if st.button("開始還原完整資料庫", disabled=not confirm_db_restore, key="start_restore_db"):
                    ok, msg = restore_full_db(uploaded_db)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
