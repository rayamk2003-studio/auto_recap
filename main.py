from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import threading
import uuid
from fractions import Fraction
from pathlib import Path

# Reuse this machine's existing free local runtime packages when available.
ROOT = Path(__file__).resolve().parent
runtime_parent = Path.home() / ".codex" / ".chatgpt-projects"
if runtime_parent.is_dir():
    for candidate in sorted(runtime_parent.glob("*/.runtime-packages")):
        if (candidate / "faster_whisper").exists() and (candidate / "myanmar_tts").exists():
            sys.path.insert(0, str(candidate))
            break

import numpy as np
import soundfile as sf
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai
import imageio_ffmpeg

app = FastAPI(title="Auto Recap")
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "output"
UPLOADS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUTS)), name="output")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MODEL = "gemini-3.5-flash-lite"
MAX_UPLOAD = 30 * 1024 * 1024 * 1024
app.state.max_upload_size = MAX_UPLOAD
JOBS: dict[str, dict] = {}
JOB_LOCK = threading.Lock()
ALLOWED = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
VOICE_PRESETS = {"natural": 0.0, "male": -2.5, "female": 2.5}


def _has_package(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _public_job(job: dict) -> dict:
    return {key: value for key, value in job.items() if not key.startswith("_")}


def _update(job_id: str, **values):
    with JOB_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(values)


def _key_for_job(supplied: str) -> str:
    key = (supplied or os.getenv("GEMINI_API_KEY", "")).strip()
    if not key:
        raise HTTPException(400, "Gemini API key ထည့်ပါ။ AI Studio မှာ အခမဲ့ key ထုတ်နိုင်သည်။")
    if not key.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise HTTPException(400, "API key ထဲမှာ မလိုအပ်သောစာသား ပါနေသည်။ Key တစ်ခုတည်းကို ပြန်ထည့်ပါ။")
    return key


def _run_ffmpeg(args: list[str], stage: str):
    result = subprocess.run(
        [FFMPEG, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{stage} မအောင်မြင်ပါ။ {detail[-1400:]}")


def _summarize(transcript: str, api_key: str, job_id: str) -> str:
    client = genai.Client(api_key=api_key)
    prompt = (
        "Write a coherent, natural spoken Burmese (Myanmar) recap, about five minutes long, "
        "from the transcript below. Keep important events and facts in order. Do not invent "
        "details. Use natural Burmese phrasing that is comfortable to read aloud. Return only "
        "the narration text in Burmese, with no title, headings, or commentary.\n\n"
        "TRANSCRIPT (text only):\n" + transcript
    )
    _update(job_id, stage="Transcript စာသားကိုသာ Gemini သို့ပို့ပြီး မြန်မာ recap ရေးနေသည်", progress=54)
    chunks = []
    try:
        stream = client.models.generate_content_stream(
            model=MODEL,
            contents=prompt,
            config={"temperature": 0.25, "max_output_tokens": 2600},
        )
        for packet in stream:
            part = getattr(packet, "text", None)
            if part:
                chunks.append(part)
                count = sum(len(item) for item in chunks)
                _update(job_id, stage=f"Gemini recap ရေးနေသည် · {count} စာလုံး", progress=min(66, 54 + count // 500))
    except Exception as exc:
        detail = str(exc).replace(api_key, "[API key ဖျောက်ထားသည်]")
        raise RuntimeError(f"Gemini API error: {detail[:1200]}") from exc
    narration = "".join(chunks).strip()
    if len(narration) < 100:
        raise RuntimeError("Gemini က မြန်မာ recap စာသား မထုတ်နိုင်ပါ။ API key, free-tier quota သို့မဟုတ် region ကိုစစ်ပါ။")
    return narration


def _make_voice(narration: str, job_id: str, voice: str = "natural") -> Path:
    from myanmar_tts import MyanmarTTS

    _update(job_id, stage="MyanmarTTS ဖြင့် local မှာ အသံဖန်တီးနေသည်", progress=70)
    tts = MyanmarTTS(device="cuda" if _has_cuda() else "cpu")
    pitch = VOICE_PRESETS.get(voice, 0.0)
    scale = 2 ** (pitch / 12)
    duration_ratio = Fraction(1 / scale).limit_denominator(1000) if pitch else None
    sentences = [part.strip() for part in re.split(r"(?<=[။!?])\s*", narration) if part.strip()]
    pieces = []
    for index, sentence in enumerate(sentences):
        audio_part = tts.tts(sentence, solver="euler", step=16, length_scale=scale)
        if hasattr(audio_part, "detach"):
            audio_part = audio_part.detach().cpu().numpy()
        audio_part = np.asarray(audio_part, dtype=np.float32).reshape(-1)
        if duration_ratio:
            from scipy.signal import resample_poly
            audio_part = resample_poly(audio_part, duration_ratio.numerator, duration_ratio.denominator).astype(np.float32)
        pieces.append(audio_part)
        if index < len(sentences) - 1:
            pieces.append(np.zeros(round(44100 * 0.22), dtype=np.float32))
        progress = 70 + int(20 * (index + 1) / max(1, len(sentences)))
        _update(job_id, stage=f"မြန်မာအသံထုတ်နေသည် · {index + 1}/{len(sentences)} ဝါကျ", progress=progress)
    if not pieces:
        raise RuntimeError("အသံဖန်တီးရန် မြန်မာစာမရှိပါ။")
    audio_path = OUTPUTS / f"{job_id}_voice.wav"
    sf.write(str(audio_path), np.concatenate(pieces), 44100)
    return audio_path


def _render_recap(source_path: Path, voice_path: Path, job_id: str, source_duration: float) -> str:
    video_path = OUTPUTS / f"{job_id}_recap.mp4"
    voice_info = sf.info(str(voice_path))
    voice_duration = voice_info.frames / max(1, voice_info.samplerate)
    # Show the source video across the full narration, sped up to fit; no fabricated shot selection.
    setpts = max(0.001, voice_duration / max(1.0, source_duration))
    _update(job_id, stage="Recap MP4 ကို local မှာ ပေါင်းစပ်နေသည်", progress=93)
    _run_ffmpeg([
        "-y", "-i", str(source_path), "-i", str(voice_path),
        "-map", "0:v:0", "-map", "1:a:0", "-vf", f"setpts={setpts:.8f}*PTS",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "29",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video_path),
    ], "ဗီဒီယိုပေါင်းစပ်ခြင်း")
    return f"/output/{video_path.name}"


def _finish_from_transcript(job_id: str, transcript: str, api_key: str, voice: str):
    try:
        narration = _summarize(transcript, api_key, job_id)
        recap_file = OUTPUTS / f"{job_id}_recap.txt"
        recap_file.write_text(narration, encoding="utf-8")
        _update(job_id, narration=narration, recap_url=f"/output/{recap_file.name}", transcript_url=f"/output/{job_id}_transcript.txt")
        voice_path = _make_voice(narration, job_id, voice)
        source_path = Path(JOBS[job_id]["_source_path"])
        source_duration = float(JOBS[job_id]["_source_duration"])
        video_url = _render_recap(source_path, voice_path, job_id, source_duration)
        _update(job_id, status="completed", stage="ပြီးပါပြီ · မြန်မာ recap အသံနှင့် MP4 အသင့်ဖြစ်ပါပြီ", progress=100,
                audio_url=f"/output/{voice_path.name}", video_url=video_url)
    except Exception as exc:
        safe_error = str(exc).replace(api_key, "[API key ဖျောက်ထားသည်]")
        _update(job_id, status="error", stage="လုပ်ဆောင်မှု ရပ်သွားသည်", error=safe_error[:1800])
        print(f"Auto Recap job {job_id} failed: {type(exc).__name__}: {safe_error[:1000]}")


def _process_video(job_id: str, api_key: str, voice: str):
    try:
        source_path = Path(JOBS[job_id]["_source_path"])
        audio_path = UPLOADS / f"{job_id}_source.wav"
        transcript_path = OUTPUTS / f"{job_id}_transcript.txt"
        _update(job_id, stage="FFmpeg ဖြင့် source အသံထုတ်နေသည် · local", progress=4)
        _run_ffmpeg(["-y", "-i", str(source_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)], "အသံထုတ်ခြင်း")

        if not _has_package("faster_whisper"):
            raise RuntimeError("faster-whisper မရှိပါ။ ပရောဂျက်အတွက် သတ်မှတ်ထားသော Python runtime နဲ့ဖွင့်ပါ။")
        from faster_whisper import WhisperModel
        device = "cuda" if _has_cuda() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        model = WhisperModel(os.getenv("WHISPER_MODEL", "base"), device=device, compute_type=compute_type)
        segments, info = model.transcribe(str(audio_path), beam_size=1, vad_filter=True)
        duration = max(1.0, float(getattr(info, "duration", 0) or 1.0))
        lines = []
        last_update = 0.0
        for segment in segments:
            text = (segment.text or "").strip()
            if text:
                lines.append(f"[{segment.start:.1f}] {text}")
            if segment.end - last_update >= 20 or segment.end >= duration:
                pct = min(48, 5 + int(43 * segment.end / duration))
                _update(job_id, stage=f"Whisper transcript ထုတ်နေသည် · {int(segment.end // 60)} / {max(1, int(duration // 60))} မိနစ်", progress=pct)
                last_update = segment.end
        del model
        transcript = "\n".join(lines).strip()
        if len(transcript) < 100:
            raise RuntimeError("အသုံးပြုနိုင်သော transcript မရပါ။ အသံဘာသာစကား သို့မဟုတ် ဗီဒီယိုကိုစစ်ပါ။")
        transcript_path.write_text(transcript, encoding="utf-8")
        _update(job_id, transcript_url=f"/output/{transcript_path.name}", transcript_preview=transcript[:1600], _source_duration=duration)
        _finish_from_transcript(job_id, transcript, api_key, voice)
    except Exception as exc:
        safe_error = str(exc).replace(api_key, "[API key ဖျောက်ထားသည်]")
        _update(job_id, status="error", stage="လုပ်ဆောင်မှု ရပ်သွားသည်", error=safe_error[:1800])
        print(f"Auto Recap job {job_id} failed: {type(exc).__name__}: {safe_error[:1000]}")


def _has_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


@app.get("/")
def home():
    return FileResponse(ROOT / "index.html")


@app.get("/api/status")
def status():
    return {
        "server": "ready",
        "whisper": _has_package("faster_whisper"),
        "tts": _has_package("myanmar_tts"),
        "ffmpeg": bool(FFMPEG),
        "model": MODEL,
    }


@app.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    gemini_api_key: str = Form(""),
    cloud_consent: str = Form(""),
    voice: str = Form("natural"),
):
    api_key = _key_for_job(gemini_api_key)
    if cloud_consent != "yes":
        raise HTTPException(400, "Transcript စာသားကို Gemini သို့ပို့ရန် သဘောတူညီချက်ကို အမှန်ခြစ်ပါ။")
    if not _has_package("faster_whisper"):
        raise HTTPException(503, "Local faster-whisper မတွေ့ပါ။ အောက်ပါ runtime Python ဖြင့် app ကိုဖွင့်ပါ။")
    if not _has_package("myanmar_tts"):
        raise HTTPException(503, "Local MyanmarTTS မတွေ့ပါ။ အောက်ပါ runtime Python ဖြင့် app ကိုဖွင့်ပါ။")
    extension = Path(file.filename or "video.mp4").suffix.lower()
    if extension not in ALLOWED:
        raise HTTPException(400, "MP4, MKV, MOV, WEBM, AVI, M4V ဖိုင်များကိုသာ လက်ခံသည်။")
    job_id = uuid.uuid4().hex[:12]
    source_path = UPLOADS / f"{job_id}{extension}"
    total = 0
    with source_path.open("wb") as destination:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD:
                source_path.unlink(missing_ok=True)
                raise HTTPException(413, "ဗီဒီယိုဖိုင်သည် 30 GB ထက်ကြီးနေသည်။")
            destination.write(chunk)
    if total == 0:
        raise HTTPException(400, "ရွေးထားသောဖိုင်မှာ ဗလာဖြစ်နေသည်။")
    safe_voice = voice if voice in VOICE_PRESETS else "natural"
    with JOB_LOCK:
        JOBS[job_id] = {
            "id": job_id, "status": "processing", "stage": "အလုပ်စတင်နေသည်", "progress": 2,
            "_source_path": str(source_path), "_source_duration": 3600.0,
        }
    background_tasks.add_task(_process_video, job_id, api_key, safe_voice)
    return {"id": job_id, "status": "processing", "stage": "အလုပ်စတင်နေသည်", "progress": 2}


@app.post("/api/jobs/{job_id}/retry")
async def retry_gemini(
    job_id: str,
    background_tasks: BackgroundTasks,
    gemini_api_key: str = Form(""),
    cloud_consent: str = Form(""),
    voice: str = Form("natural"),
):
    api_key = _key_for_job(gemini_api_key)
    if cloud_consent != "yes":
        raise HTTPException(400, "Transcript စာသားကို Gemini သို့ပို့ရန် သဘောတူညီချက်ကို အမှန်ခြစ်ပါ။")
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job or not job.get("transcript_url"):
            raise HTTPException(404, "ဒီ job မှာ transcript မတွေ့ပါ။ ပြန်တင်ရန်လိုသည်။")
        source_path = Path(job["_source_path"])
        transcript_path = OUTPUTS / f"{job_id}_transcript.txt"
        if not transcript_path.exists() or not source_path.exists():
            raise HTTPException(404, "Transcript သို့မဟုတ် မူရင်းဗီဒီယို မတွေ့ပါ။")
        job.update(status="processing", stage="Transcript မှ recap ပြန်စနေသည်", progress=52)
        JOBS[job_id]["_retry_voice"] = voice if voice in VOICE_PRESETS else "natural"
    background_tasks.add_task(_retry_from_saved_transcript, job_id, api_key)
    return _public_job(JOBS[job_id])


def _retry_from_saved_transcript(job_id: str, api_key: str):
    try:
        transcript_path = OUTPUTS / f"{job_id}_transcript.txt"
        transcript = transcript_path.read_text(encoding="utf-8")
        narration = _summarize(transcript, api_key, job_id)
        recap_file = OUTPUTS / f"{job_id}_recap.txt"
        recap_file.write_text(narration, encoding="utf-8")
        _update(job_id, narration=narration, recap_url=f"/output/{recap_file.name}")
        voice = JOBS[job_id].get("_retry_voice", "natural")
        audio_path = _make_voice(narration, job_id, voice)
        video_url = _render_recap(Path(JOBS[job_id]["_source_path"]), audio_path, job_id, float(JOBS[job_id]["_source_duration"]))
        _update(job_id, status="completed", stage="ပြီးပါပြီ · မြန်မာ recap အသံနှင့် MP4 အသင့်ဖြစ်ပါပြီ", progress=100,
                audio_url=f"/output/{audio_path.name}", video_url=video_url)
    except Exception as exc:
        detail = str(exc).replace(api_key, "[API key ဖျောက်ထားသည်]")
        _update(job_id, status="error", stage="လုပ်ဆောင်မှု ရပ်သွားသည်", error=detail[:1800])


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job:
            return _public_job(job)
    video = OUTPUTS / f"{job_id}_recap.mp4"
    transcript = OUTPUTS / f"{job_id}_transcript.txt"
    if video.exists():
        return {"id": job_id, "status": "completed", "stage": "အသံနှင့် recap video အသင့်ဖြစ်ပါပြီ", "progress": 100,
                "video_url": f"/output/{video.name}", "transcript_url": f"/output/{transcript.name}" if transcript.exists() else None}
    raise HTTPException(404, "Job status မတွေ့ပါ။ Server ပြန်စထားပါက ဗီဒီယိုကို ပြန်တင်ပါ။")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)