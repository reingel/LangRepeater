from fastapi import APIRouter
from pydantic import BaseModel

from langrepeater.core.stats_store import StatsStore

router = APIRouter(prefix="/stats", tags=["stats"])
_store = StatsStore()


class IncrementRequest(BaseModel):
    media_path: str
    subtitle_index: int


@router.get("/")
def get_stats(media_path: str) -> dict:
    stats = _store.load(media_path)
    return {
        "media_path": stats.media_path,
        "total_play_count": stats.total_play_count,
        "subtitle_play_counts": stats.subtitle_play_counts,
    }


@router.post("/increment")
def increment_play(req: IncrementRequest) -> dict:
    _store.increment_play(req.media_path, req.subtitle_index)
    return {"status": "incremented"}
