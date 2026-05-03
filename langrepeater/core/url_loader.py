import os
from pathlib import Path


def download(url: str, output_dir: str) -> str:
    """Download audio as mp3 using yt-dlp.

    Returns the path to the downloaded mp3 file.
    """
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)

    before_mp3 = set(Path(output_dir).glob("*.mp3"))

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"},
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    new_mp3 = set(Path(output_dir).glob("*.mp3")) - before_mp3

    if not new_mp3:
        raise RuntimeError("Downloaded audio file not found")

    return str(max(new_mp3, key=lambda p: p.stat().st_mtime))


_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("small", device="auto", compute_type="default")
    return _whisper_model


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def transcribe(audio_path: str) -> str:
    """Transcribe audio to word-level JSON using faster-whisper.

    Requires: pip install faster-whisper
    Returns the srt_path (not yet generated; SRTParser.load() will build it from JSON).
    """
    import json
    import sys

    model = get_whisper_model()
    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        multilingual=True,
        condition_on_previous_text=False,
    )
    total = info.duration

    transcription = []
    for segment in segments:
        sys.stdout.write(
            f"\r  {_fmt_time(segment.end)} / {_fmt_time(total)} ({segment.end / total * 100:3.0f}%)"
        )
        sys.stdout.flush()
        for word in segment.words or []:
            text = word.word.strip()
            if not text or text.startswith("["):
                continue
            transcription.append({
                "text": text,
                "offsets": {
                    "from": int(word.start * 1000),
                    "to": int(word.end * 1000),
                },
            })
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()

    p = Path(audio_path)
    json_path = p.parent / (p.stem + ".mp3.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"transcription": transcription}, f, ensure_ascii=False, indent=2)

    return str(p.with_suffix(".srt"))


def extract_audio(mp4_path: str) -> str:
    """Extract audio from mp4 to mp3 using ffmpeg.

    Returns the path to the generated mp3 file (same folder, same stem).
    """
    import subprocess

    mp3_path = str(Path(mp4_path).with_suffix(".mp3"))
    result = subprocess.run(
        ["ffmpeg", "-i", mp4_path, "-q:a", "0", "-map", "a", mp3_path, "-y"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")
    return mp3_path
