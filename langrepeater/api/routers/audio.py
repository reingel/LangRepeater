from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from langrepeater.api import state

router = APIRouter(prefix="/audio", tags=["audio"])


class PlayRequest(BaseModel):
    media_path: str
    start: float
    end: float


@router.post("/play")
def play_audio(req: PlayRequest) -> dict:
    try:
        player = state.get_player(req.media_path)
        player.play_segment(req.media_path, req.start, req.end)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "playing"}


@router.post("/stop")
def stop_audio() -> dict:
    state.stop_player()
    return {"status": "stopped"}
