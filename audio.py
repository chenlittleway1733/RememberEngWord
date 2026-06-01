"""
audio.py
處理單字與例句發音。
"""

import asyncio
import base64
import hashlib
from pathlib import Path
import streamlit as st

from config import AUDIO_DIR, VOICE
from utils import safe_str


def text_to_audio_filename(text: str) -> Path:
    """同一句文字對應同一個 mp3 檔名。"""
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    return AUDIO_DIR / f"{text_hash}.mp3"


async def _create_audio_async(text: str, output_path: Path):
    """使用 edge-tts 非同步產生 mp3。"""
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=VOICE)
    await communicate.save(str(output_path))


def get_audio_file(text: str) -> Path | None:
    """取得發音檔，若不存在就自動產生。"""
    text = safe_str(text)
    if not text:
        return None

    output_path = text_to_audio_filename(text)

    if output_path.exists():
        return output_path

    try:
        asyncio.run(_create_audio_async(text, output_path))
        return output_path
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_create_audio_async(text, output_path))
        loop.close()
        return output_path
    except Exception as e:
        st.warning(f"產生發音失敗：{e}")
        return None


def autoplay_audio(audio_path: Path | None):
    """
    自動播放音檔。

    修正版重點：
    1. 播放新音檔前，先停止頁面上既有的 audio。
    2. 避免聽力測驗進入下一題時，上一題音檔還沒停止，造成「先唸上一題、再唸本題」。
    3. 使用 components.html 執行少量 JavaScript，主動停止舊音檔。
    """
    if audio_path is None or not audio_path.exists():
        return

    import streamlit.components.v1 as components

    audio_bytes = audio_path.read_bytes()
    audio_base64 = base64.b64encode(audio_bytes).decode()

    audio_html = f"""
    <script>
    function stopAllAudio(doc) {{
        try {{
            const audios = doc.querySelectorAll('audio');
            audios.forEach(function(a) {{
                try {{
                    a.pause();
                    a.currentTime = 0;
                    a.src = '';
                    a.remove();
                }} catch (e) {{}}
            }});

            const iframes = doc.querySelectorAll('iframe');
            iframes.forEach(function(frame) {{
                try {{
                    if (frame.contentWindow && frame.contentWindow.document) {{
                        stopAllAudio(frame.contentWindow.document);
                    }}
                }} catch (e) {{}}
            }});
        }} catch (e) {{}}
    }}

    try {{
        stopAllAudio(window.parent.document);
    }} catch (e) {{
        stopAllAudio(document);
    }}

    const audio = new Audio("data:audio/mp3;base64,{audio_base64}");
    audio.autoplay = true;
    audio.play().catch(function(e) {{
        console.log("Autoplay was blocked or interrupted:", e);
    }});
    </script>
    """

    components.html(audio_html, height=0, width=0)

def audio_button(text: str, label: str, key: str):
    """顯示播放按鈕。"""
    if st.button(label, key=key):
        audio_path = get_audio_file(text)
        autoplay_audio(audio_path)
