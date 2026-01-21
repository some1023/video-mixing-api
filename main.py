import os
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- CORS設定（すべてのドメインパターンを網羅） ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://iiakome.com",
        "http://iiakome.com",
        "https://www.iiakome.com",
        "http://www.iiakome.com",
    ],
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
        v_ext = os.path.splitext(video.filename)[1].lower()
        a_ext = os.path.splitext(audio.filename)[1].lower()
        
        v_in = os.path.join(tmpdir, "in_v" + v_ext)
        a_in = os.path.join(tmpdir, "in_a" + a_ext)
        v_out = os.path.join(tmpdir, "output.mp4")

        content_v = await video.read()
        with open(v_in, "wb") as f: f.write(content_v)
        content_a = await audio.read()
        with open(a_in, "wb") as f: f.write(content_a)

        # 【修正ポイント】
        # 元動画に音がない場合でもエラーにならない強力なFFmpegコマンド
        # 1. 無音(anullsrc)を生成して元動画の音(もしあれば)と合成
        # 2. BGMの音量を調整
        # 3. amixで混合
        filter_complex = (
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0];"
            f"[1:a]volume={volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", v_in,
            "-i", a_in,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", # 無音源を予備で追加
            "-filter_complex", filter_complex,
            "-map", "0:v:0",   # 映像はそのまま
            "-map", "[aout]",   # 音声はミックスしたもの
            "-c:v", "copy",     # 映像は高速コピー
            "-c:a", "aac",      # 音声はAACに変換
            "-shortest",        # 短い方に合わせる
            v_out
        ]

        try:
            # 実行ログを確認できるように出力
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg Error Output: {result.stderr}")
                raise Exception("FFmpeg command failed")
                
            return FileResponse(v_out, media_type="video/mp4", filename="mixed_video.mp4")
        except Exception as e:
            print(f"System Error: {str(e)}")
            raise HTTPException(status_code=500, detail="動画の合成処理に失敗しました。ファイル形式を確認してください。")