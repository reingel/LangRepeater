from fastapi import APIRouter

from langrepeater.core.file_finder import FileFinder

router = APIRouter(prefix="/files", tags=["files"])
_finder = FileFinder()


@router.get("/media")
def search_media(directory: str) -> list[str]:
    return _finder.find_media(directory)


@router.get("/srt")
def search_srt(directory: str) -> list[str]:
    return _finder.find_srt(directory)
