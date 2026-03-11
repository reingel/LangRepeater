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


def transcribe(audio_path: str) -> str:
    """Generate SRT from audio using openai-whisper, split by sentence.

    Returns the path to the generated SRT file.
    """
    import whisper

    model = whisper.load_model("base")
    result = model.transcribe(audio_path)

    # Group whisper segments into sentences by sentence-ending punctuation
    sentences: list[tuple[float, float, str]] = []
    buf_text = ""
    buf_start: float | None = None
    buf_end: float | None = None

    for seg in result["segments"]:
        text = seg["text"].strip()
        if not text:
            continue
        if buf_start is None:
            buf_start = seg["start"]
        buf_end = seg["end"]
        buf_text = (buf_text + " " + text).strip() if buf_text else text
        if text[-1] in ".!?":
            sentences.append((buf_start, buf_end, buf_text))
            buf_text = ""
            buf_start = None
            buf_end = None

    if buf_text and buf_start is not None:
        sentences.append((buf_start, buf_end, buf_text))  # type: ignore[arg-type]

    srt_path = str(Path(audio_path).with_suffix(".srt"))
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(sentences, 1):
            f.write(f"{i}\n{_to_srt_time(start)} --> {_to_srt_time(end)}\n{text}\n\n")

    return srt_path


def _to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
