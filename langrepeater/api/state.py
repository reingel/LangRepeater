from langrepeater.core.audio_player import AudioPlayer, create_player

_player: AudioPlayer | None = None
_current_media_path: str | None = None


def get_player(media_path: str) -> AudioPlayer:
    global _player, _current_media_path
    if _player is None or _current_media_path != media_path:
        if _player is not None:
            _player.stop()
        _player = create_player(media_path)
        _current_media_path = media_path
    return _player


def stop_player() -> None:
    global _player
    if _player is not None:
        _player.stop()
