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
    """Generate word-level SRT from audio using stable-ts.

    Uses: stable-ts input.mp3 -o input.srt --mel_first --regroup True
    The resulting SRT uses <font color=...> tags to highlight each word
    in sequence, which SRTParser converts into sentence-grouped Subtitles.

    Returns the path to the generated SRT file.
    """
    import subprocess

    srt_path = str(Path(audio_path).with_suffix(".srt"))
    result = subprocess.run(
        ["stable-ts", audio_path, "-o", srt_path, "--mel_first", "--regroup", "True"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"stable-ts failed: {result.stderr}")
    return srt_path


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
