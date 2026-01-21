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
    
    with tempfile.TemporaryDirectory() as tmpdir:
        v_in = os.path.join(tmpdir, "v_in.mp4") 
        a_in = os.path.join(tmpdir, "a_in.mp3")
        v_out = os.path.join(tmpdir, "output.mp4")

        # ファイル保存
        with open(v_in, "wb") as f: f.write(await video.read())
        with open(a_in, "wb") as f: f.write(await audio.read())

        # シンプルかつ強力なフィルタ設定
        # 映像は再エンコードせずコピー (-c:v copy)
        # 音声だけ合成してAACに変換
        filter_complex = f"[1:a]volume={volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]"

        cmd = [
            ffmpeg_path, "-y",
            "-i", v_in,
            "-i", a_in,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy", 
            "-c:a", "aac",
            "-shortest",
            v_out
        ]

        logger.info(f"Executing: {' '.join(cmd)}")

        try:
            # shell=Falseで実行し、エラー出力をキャッチ
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if process.returncode != 0:
                # ここでFFmpegが何を言ったかログに出す
                logger.error(f"FFmpeg failed with return code {process.returncode}")
                logger.error(f"FFmpeg Stderr: {process.stderr}")
                raise HTTPException(status_code=500, detail=f"FFmpeg Error: {process.stderr}")

            if not os.path.exists(v_out):
                logger.error("Output file missing after FFmpeg process")
                raise HTTPException(status_code=500, detail="Output file was not created")

            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timeout")
            raise HTTPException(status_code=408, detail="Process timeout")
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))