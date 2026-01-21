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
        # ファイル名を完全に固定して、FFmpegが混乱しないようにする
        v_in = os.path.join(tmpdir, "v_input") 
        a_in = os.path.join(tmpdir, "a_input")
        v_out = os.path.join(tmpdir, "output.mp4")

        # 拡張子に依存せずバイナリとして書き込む
        with open(v_in, "wb") as f: f.write(await video.read())
        with open(a_in, "wb") as f: f.write(await audio.read())

        # 【強化ポイント】
        # -ac 2 (ステレオ強制) と libx264 (標準映像) で、iPhone動画なども強制変換
        filter_complex = (
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            f"[1:a]volume={volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            ffmpeg_path, "-y",
            "-i", v_in,
            "-i", a_in,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p", # スマホやブラウザで再生可能な形式に固定
            "-preset", "ultrafast",
            "-c:a", "aac",
            "-shortest",
            v_out
        ]

        try:
            logger.info("FFmpeg synthesis started...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg Stderr: {result.stderr}")
                raise Exception(f"FFmpeg error: {result.stderr}")

            if os.path.exists(v_out) and os.path.getsize(v_out) > 0:
                return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
            else:
                raise Exception("Output file is empty or missing")
                
        except Exception as e:
            logger.error(f"System Error: {str(e)}")
            raise HTTPException(status_code=500, detail="動画の合成中にエラーが発生しました。")