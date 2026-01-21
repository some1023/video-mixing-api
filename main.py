import os
import subprocess
import tempfile
import logging
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
    return {"status": "iiakome API is running"}

@app.post("/merge")
async def merge_video_audio(
    video: UploadFile = File(...), 
    audio: UploadFile = File(...),
    volume: float = Form(0.3)
):
    with tempfile.TemporaryDirectory() as tmpdir:
        # 拡張子を保持しつつ固定名にする
        v_ext = os.path.splitext(video.filename)[1].lower() or ".mp4"
        a_ext = os.path.splitext(audio.filename)[1].lower() or ".mp3"
        v_in = os.path.join(tmpdir, f"v_in{v_ext}")
        a_in = os.path.join(tmpdir, f"a_in{a_ext}")
        v_out = os.path.join(tmpdir, "output.mp4")

        # ファイルを保存
        with open(v_in, "wb") as f: f.write(await video.read())
        with open(a_in, "wb") as f: f.write(await audio.read())

        # FFmpegフィルタ: 入力不足を補う設定を追加
        filter_complex = (
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            f"[1:a]volume={volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", v_in,
            "-i", a_in,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "libx264", # copyではなく再エンコードすることで互換性を高める
            "-preset", "ultrafast", # 速度優先
            "-c:a", "aac",
            "-shortest",
            v_out
        ]

        try:
            # ログに実行コマンドを出力
            logger.info(f"Running FFmpeg...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg Stderr: {result.stderr}")
                raise Exception("FFmpeg failed to create output file")

            if not os.path.exists(v_out):
                raise Exception("Output file was not generated")

            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
            
        except Exception as e:
            logger.error(f"Final Error: {str(e)}")
            raise HTTPException(status_code=500, detail="Synthesis failed")