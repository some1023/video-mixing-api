import os
import subprocess
import tempfile
import logging
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
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
    # 起動時にFFmpegがあるかチェックしてログに出す
    ffmpeg_path = shutil.which("ffmpeg")
    return {"status": "iiakome API is running", "ffmpeg": ffmpeg_path}

@app.post("/merge")
async def merge_video_audio(
    video: UploadFile = File(...), 
    audio: UploadFile = File(...),
    volume: float = Form(0.3)
):
    # FFmpegの存在確認
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.error("FFmpeg not found in system path")
        raise HTTPException(status_code=500, detail="FFmpeg is not installed on server")

    with tempfile.TemporaryDirectory() as tmpdir:
        v_ext = os.path.splitext(video.filename)[1].lower() or ".mp4"
        a_ext = os.path.splitext(audio.filename)[1].lower() or ".mp3"
        v_in = os.path.join(tmpdir, f"v_in{v_ext}")
        a_in = os.path.join(tmpdir, f"a_in{a_ext}")
        v_out = os.path.join(tmpdir, "output.mp4")

        with open(v_in, "wb") as f: f.write(await video.read())
        with open(a_in, "wb") as f: f.write(await audio.read())

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
            "-preset", "ultrafast",
            "-c:a", "aac",
            "-shortest",
            v_out
        ]

        try:
            # stderrを確実にキャッチする
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg Stderr: {result.stderr}")
                raise Exception(f"FFmpeg process error: {result.stderr}")

            if not os.path.exists(v_out):
                raise Exception("Output file was not generated after processing")

            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
            
        except Exception as e:
            logger.error(f"Final Error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))