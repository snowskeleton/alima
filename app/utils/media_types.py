"""Audio media types.

One source of truth, because three places have to agree or podcast players
reject the episode: the RSS <enclosure type>, the Content-Type stored on the B2
object, and the Content-Type the signed URL serves back.
"""

AUDIO_MEDIA_TYPES = {
    "m4a": "audio/mp4",
    "m4b": "audio/x-m4b",
    "mp3": "audio/mpeg",
}

DEFAULT_AUDIO_MEDIA_TYPE = "audio/x-m4b"


def audio_media_type(file_format: str | None) -> str:
    """Map a bare file extension ("m4a", "mp3") to its audio media type."""
    if not file_format:
        return DEFAULT_AUDIO_MEDIA_TYPE
    return AUDIO_MEDIA_TYPES.get(file_format.lower().lstrip("."), DEFAULT_AUDIO_MEDIA_TYPE)
