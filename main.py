import os
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 自分のサイトのみを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iiakome.com", "https://www.iiakome.com"],
    allow_credentials=True,
    allow_methods=["POST"], # GETなどは不要なので制限
    allow_headers=["*"],
)

# 【対策】サーバーに届く前にサイズをチェックする(50MB制限)
MAX_SIZE = 50 * 1024 * 1024

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > MAX_SIZE:
            return FileResponse(status_code=413) # Payload Too Large
    return await call_next(request)

@app.get("/")
def read_root():
    return {"status": "iiakome API is running"}

@app.post("/merge")
async def merge_video_audio(
    video: UploadFile = File(...), 
    audio: UploadFile = File(...),
    volume: float = Form(0.3)
):
    # ファイル形式のホワイトリスト
    if video.content_type not in ["video/mp4", "video/quicktime"]:
        raise HTTPException(status_code=400, detail="Invalid video format")

    with tempfile.TemporaryDirectory() as tmpdir:
        # ユーザーのファイル名を無視して固定名にする(インジェクション対策)
        v_in = os.path.join(tmpdir, "v_in.mp4")
        a_in = os.path.join(tmpdir, "a_in.mp3")
        v_out = os.path.join(tmpdir, "v_out.mp4")

        try:
            with open(v_in, "wb") as f: f.write(await video.read())
            with open(a_in, "wb") as f: f.write(await audio.read())
        except Exception:
            raise HTTPException(status_code=500, detail="Storage error")

        # 音量バリデーション (0.0〜1.0以外は拒否)
        volume = max(0.0, min(1.0, volume))

        filter_complex = (
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            f"[1:a]volume={volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            "ffmpeg", "-y", "-i", v_in, "-i", a_in,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", filter_complex,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest", v_out
        ]

        try:
            # 30秒以内に終わらない処理は強制終了させる(タイムアウト対策)
            subprocess.run(cmd, capture_output=True, timeout=30)
            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=408, detail="Processing timeout")
        except Exception:
            raise HTTPException(status_code=500, detail="Processing error")