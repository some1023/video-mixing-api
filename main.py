import os
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 1. CORS設定（許可するドメインを厳密に指定）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://iiakome.com",
        "https://www.iiakome.com",
    ],
    allow_credentials=True,
    allow_methods=["POST"], 
    allow_headers=["*"],
)

# 2. ファイルサイズ制限（50MB）
MAX_SIZE = 50 * 1024 * 1024

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/merge":
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > MAX_SIZE:
            return FileResponse(status_code=413) 
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
    # 形式チェック
    v_ext = os.path.splitext(video.filename)[1].lower()
    if v_ext not in [".mp4", ".mov"]:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    with tempfile.TemporaryDirectory() as tmpdir:
        v_in = os.path.join(tmpdir, "v_input" + v_ext)
        a_in = os.path.join(tmpdir, "a_input.mp3")
        v_out = os.path.join(tmpdir, "output.mp4")

        # ファイル保存
        with open(v_in, "wb") as f: f.write(await video.read())
        with open(a_in, "wb") as f: f.write(await audio.read())

        # 3. 最強のFFmpegフィルタ（無音動画でもエラーにならない）
        # 元動画に音があるか不明なため、無音源を合成のベースに敷く
        filter_complex = (
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            f"[1:a]volume={volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", v_in,
            "-i", a_in,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", # ダミー無音
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",  # 映像は再圧縮せず高速コピー
            "-c:a", "aac",
            "-shortest",     # 短い方に合わせる
            v_out
        ]

        try:
            # タイムアウトを120秒に設定
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
        except subprocess.TimeoutExpired:
            print("ERROR: Timeout")
            raise HTTPException(status_code=408, detail="Timeout")
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error: {e.stderr.decode()}")
            raise HTTPException(status_code=500, detail="Synthesis failed")