import os
import subprocess
import tempfile
import logging
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
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

# 処理後に一時ファイルを消す関数
def cleanup(tmpdir: str):
    try:
        shutil.rmtree(tmpdir)
        logger.info(f"Successfully cleaned up: {tmpdir}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

@app.get("/")
def read_root():
    return {"status": "iiakome API is running"}

@app.post("/merge")
async def merge_video_audio(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...), 
    audio: UploadFile = File(...),
    volume: float = Form(0.3)
):
    ffmpeg_path = shutil.which("ffmpeg")
    tmpdir = tempfile.mkdtemp()
    
    try:
        v_in = os.path.join(tmpdir, "v_in.mp4") 
        a_in = os.path.join(tmpdir, "a_in.mp3")
        v_out = os.path.join(tmpdir, "output.mp4")

        # チャンク保存（メモリ節約）
        for source, dest in [(video, v_in), (audio, a_in)]:
            with open(dest, "wb") as f:
                while chunk := await source.read(1024 * 1024):
                    f.write(chunk)

        # 映像はコピー、音声のみミックス
        filter_complex = f"[1:a]volume={volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]"

        cmd = [
            ffmpeg_path, "-y", "-i", v_in, "-i", a_in,
            "-filter_complex", filter_complex,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest", v_out
        ]

        process = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if process.returncode != 0:
            background_tasks.add_task(cleanup, tmpdir)
            raise HTTPException(status_code=500, detail="Mixing Failed")

        # 送信後にフォルダを消す予約
        background_tasks.add_task(cleanup, tmpdir)
        return FileResponse(v_out, media_type="video/mp4", filename="iiakome_mixed.mp4")

    except Exception as e:
        background_tasks.add_task(cleanup, tmpdir)
        raise HTTPException(status_code=500, detail=str(e))