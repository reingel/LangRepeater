from fastapi import APIRouter
from pydantic import BaseModel

from langrepeater.core.models import Session
from langrepeater.core.progress_store import ProgressStore

router = APIRouter(prefix="/sessions", tags=["sessions"])
_store = ProgressStore()


class SessionModel(BaseModel):
    media_path: str
    srt_path: str
    current_index: int = 0


class DeleteRequest(BaseModel):
    media_path: str


@router.get("/")
def get_sessions() -> list[SessionModel]:
    return [
        SessionModel(media_path=s.media_path, srt_path=s.srt_path, current_index=s.current_index)
        for s in _store.load()
    ]


@router.post("/")
def upsert_session(session: SessionModel) -> dict:
    _store.upsert(Session(
        media_path=session.media_path,
        srt_path=session.srt_path,
        current_index=session.current_index,
    ))
    return {"status": "saved"}


@router.delete("/")
def delete_session(req: DeleteRequest) -> dict:
    sessions = [s for s in _store.load() if s.media_path != req.media_path]
    _store.save(sessions)
    return {"status": "deleted"}
