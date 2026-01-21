import os
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# 【重要】ここが抜けていると「appが定義されていません」になります
app = FastAPI()

# iiakome.com からのアクセスを許可（セキュリティ設定）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iiakome.com", "http://127.0.0.1:5500", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 制限設定
MAX_VIDEO_SIZE = 50 * 1024 * 1024 
MAX_AUDIO_SIZE = 15 * 1024 * 1024 

@app.get("/")
def read_root():
    return {"status": "iiakome API is running"}

@app.post("/merge")
async def merge_video_audio(
    video: UploadFile = File(...), 
    audio: UploadFile = File(...),
    volume: float = Form(0.3)  # フロントエンドのスライダー値を受け取る
):
    with tempfile.TemporaryDirectory() as tmpdir:
        v_ext = os.path.splitext(video.filename)[1].lower()
        a_ext = os.path.splitext(audio.filename)[1].lower()
        
        v_in = os.path.join(tmpdir, "in_v" + v_ext)
        a_in = os.path.join(tmpdir, "in_a" + a_ext)
        v_out = os.path.join(tmpdir, "output.mp4")

        # ファイル保存
        content_v = await video.read()
        with open(v_in, "wb") as f: f.write(content_v)
        content_a = await audio.read()
        with open(a_in, "wb") as f: f.write(content_a)

        # FFmpeg実行 (amixフィルタで音量を反映)
        # volume={volume} の部分にフロントエンドからの数値が入ります
        filter_complex = f"[1:a]volume={volume}[bgm]; [0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"

        cmd = [
            "ffmpeg", "-y",
            "-i", v_in,
            "-i", a_in,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            v_out
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail="合成失敗")