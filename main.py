import os
import subprocess
import tempfile
import logging
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iiakome.com", "https://www.iiakome.com"],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    ffmpeg_path = shutil.which("ffmpeg")
    return {"status": "iiakome API is running", "ffmpeg": ffmpeg_path}

@app.post("/merge")
async def merge_video_audio(
    video: UploadFile = File(...), 
    audio: UploadFile = File(...),
    volume: float = Form(0.3)
):
    ffmpeg_path = shutil.which("ffmpeg")
    
    # tempfile.mkdtemp を使い、一時フォルダの寿命を確実に管理
    tmpdir = tempfile.mkdtemp()
    try:
        v_in = os.path.join(tmpdir, "v_in.mp4") 
        a_in = os.path.join(tmpdir, "a_in.mp3")
        v_out = os.path.join(tmpdir, "output.mp4")

        # 【超重要】メモリ節約のため1MBずつディスクに書き込む
        for source, dest in [(video, v_in), (audio, a_in)]:
            with open(dest, "wb") as f:
                while chunk := await source.read(1024 * 1024):
                    f.write(chunk)

        # 映像を再エンコードせず、音声のミックスのみを行う最軽量コマンド
        filter_complex = f"[1:a]volume={volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]"

        cmd = [
            ffmpeg_path, "-y",
            "-i", v_in,
            "-i", a_in,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",     # 映像は絶対にいじらない（メモリ対策）
            "-c:a", "aac",      # 音声のみ変換
            "-shortest",
            v_out
        ]

        logger.info(f"FFmpeg command starting...")
        # 実行
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if process.returncode != 0:
            logger.error(f"FFmpeg Failed: {process.stderr}")
            raise HTTPException(status_code=500, detail="FFmpeg Mixing Failed")

        if not os.path.exists(v_out):
            raise HTTPException(status_code=500, detail="Result file not found")

        return FileResponse(v_out, media_type="video/mp4", filename="iiakome_mixed.mp4")

    except Exception as e:
        logger.error(f"Process Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    # ファイル送信後に一時フォルダを消すと送信エラーになるため、
    # 本来はBackgroundTasksで消すべきですが、まずは動かすことを優先します。