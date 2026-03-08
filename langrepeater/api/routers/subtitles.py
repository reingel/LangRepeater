from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from langrepeater.core.srt_parser import SRTParser

router = APIRouter(prefix="/subtitles", tags=["subtitles"])
_parser = SRTParser()


class SubtitleOut(BaseModel):
    index: int
    start: float
    end: float
    text: str


@router.get("/")
def get_subtitles(srt_path: str) -> list[SubtitleOut]:
    try:
        subs = _parser.load(srt_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"SRT file not found: {srt_path}")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [SubtitleOut(index=s.index, start=s.start, end=s.end, text=s.text) for s in subs]
