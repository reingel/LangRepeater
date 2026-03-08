from fastapi import FastAPI

from langrepeater.api.routers import audio, files, sessions, stats, subtitles


def create_app() -> FastAPI:
    app = FastAPI(title="LangRepeater API", version="0.2.0")
    app.include_router(files.router)
    app.include_router(subtitles.router)
    app.include_router(audio.router)
    app.include_router(sessions.router)
    app.include_router(stats.router)
    return app


app = create_app()
