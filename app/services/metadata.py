"""Service for reading and writing audio file metadata."""

import logging
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.mp4 import MP4, MP4Cover

from ..config import settings

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for reading and writing audio file metadata."""

    @staticmethod
    def read_metadata(file_path: Path) -> dict:
        """
        Read metadata from an audio file.

        Args:
            file_path: Path to the audio file

        Returns:
            Dictionary containing metadata fields
        """
        try:
            audio = MutagenFile(str(file_path))

            if audio is None:
                logger.warning(f"Could not read metadata from {file_path}")
                return {}

            metadata = {
                "title": None,
                "subtitle": None,
                "author": None,
                "narrator": None,
                "series": None,
                "series_position": None,
                "description": None,
                "publisher": None,
                "duration_seconds": None,
                "genres": None,
            }

            # Handle MP4/M4A/M4B files (most common for audiobooks)
            if isinstance(audio, MP4):
                # Title
                if "\xa9nam" in audio:
                    metadata["title"] = audio["\xa9nam"][0]

                # Author (Artist)
                if "\xa9ART" in audio:
                    metadata["author"] = audio["\xa9ART"][0]
                elif "\xa9alb" in audio:  # Album Artist
                    metadata["author"] = audio["\xa9alb"][0]

                # Narrator (Composer field often used for narrator)
                if "\xa9wrt" in audio:
                    metadata["narrator"] = audio["\xa9wrt"][0]

                # Description/Comment
                if "\xa9cmt" in audio:
                    metadata["description"] = audio["\xa9cmt"][0]
                elif "desc" in audio:
                    metadata["description"] = audio["desc"][0]
                elif "ldes" in audio:
                    metadata["description"] = audio["ldes"][0]

                # Publisher
                if "\xa9pub" in audio:
                    metadata["publisher"] = audio["\xa9pub"][0]

                # Series (Album)
                if "\xa9alb" in audio:
                    metadata["series"] = audio["\xa9alb"][0]

                # Series position (Track number)
                if "trkn" in audio and audio["trkn"]:
                    track_info = audio["trkn"][0]
                    if isinstance(track_info, tuple) and len(track_info) > 0:
                        metadata["series_position"] = str(track_info[0])

                # Genre
                if "\xa9gen" in audio:
                    genres = audio["\xa9gen"]
                    metadata["genres"] = genres if isinstance(genres, list) else [genres]

                # Duration
                if hasattr(audio.info, "length"):
                    metadata["duration_seconds"] = int(audio.info.length)

            # Add support for other formats if needed
            else:
                # Generic fallback for other formats
                if hasattr(audio, "tags") and audio.tags:
                    tags = audio.tags

                    # Try common tag names
                    for tag_name in ["title", "TIT2"]:
                        if tag_name in tags:
                            metadata["title"] = str(tags[tag_name][0])
                            break

                    for tag_name in ["artist", "TPE1"]:
                        if tag_name in tags:
                            metadata["author"] = str(tags[tag_name][0])
                            break

                if hasattr(audio.info, "length"):
                    metadata["duration_seconds"] = int(audio.info.length)

            return metadata

        except Exception as e:
            logger.error(f"Error reading metadata from {file_path}: {e}")
            return {}

    @staticmethod
    def extract_cover_art(file_path: Path, output_path: Path) -> bool:
        """
        Extract cover art from an audio file.

        Args:
            file_path: Path to the audio file
            output_path: Path where cover image should be saved

        Returns:
            True if cover art was extracted successfully, False otherwise
        """
        try:
            audio = MutagenFile(str(file_path))

            if audio is None:
                return False

            # Handle MP4/M4A/M4B files
            if isinstance(audio, MP4):
                if "covr" in audio:
                    cover_data = audio["covr"][0]

                    # Write cover art to file
                    with open(output_path, "wb") as f:
                        f.write(cover_data)

                    logger.info(f"Extracted cover art to {output_path}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error extracting cover art from {file_path}: {e}")
            return False

    @staticmethod
    def update_metadata(file_path: Path, metadata: dict) -> bool:
        """
        Update metadata in an audio file.

        Args:
            file_path: Path to the audio file
            metadata: Dictionary of metadata to update

        Returns:
            True if metadata was updated successfully, False otherwise
        """
        try:
            audio = MutagenFile(str(file_path))

            if audio is None:
                return False

            # Handle MP4/M4A/M4B files
            if isinstance(audio, MP4):
                if "title" in metadata and metadata["title"]:
                    audio["\xa9nam"] = metadata["title"]

                if "author" in metadata and metadata["author"]:
                    audio["\xa9ART"] = metadata["author"]

                if "narrator" in metadata and metadata["narrator"]:
                    audio["\xa9wrt"] = metadata["narrator"]

                if "description" in metadata and metadata["description"]:
                    audio["\xa9cmt"] = metadata["description"]

                if "publisher" in metadata and metadata["publisher"]:
                    audio["\xa9pub"] = metadata["publisher"]

                if "series" in metadata and metadata["series"]:
                    audio["\xa9alb"] = metadata["series"]

                if "genre" in metadata and metadata["genre"]:
                    audio["\xa9gen"] = metadata["genre"]

                audio.save()
                logger.info(f"Updated metadata for {file_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating metadata for {file_path}: {e}")
            return False
