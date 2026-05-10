"""Service for processing and optimizing images."""

import io
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image

from ..config import settings

logger = logging.getLogger(__name__)

# Allowed image formats
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

# Standard podcast cover size
PODCAST_COVER_SIZE = (3000, 3000)


class ImageProcessorService:
    """Service for processing feed cover images."""

    def __init__(self):
        """Initialize the image processor."""
        pass

    async def process_feed_cover(self, uploaded_file: UploadFile) -> str:
        """
        Process uploaded feed cover image.

        1. Validate file type and size
        2. Open with Pillow
        3. Center crop to square
        4. Resize to 3000x3000
        5. Convert to RGB and save as JPEG
        6. Return relative path

        Args:
            uploaded_file: The uploaded image file

        Returns:
            Relative path to saved image (e.g., "feeds/uuid.jpg")

        Raises:
            ValueError: If file is invalid or processing fails
        """
        try:
            # Read file content
            content = await uploaded_file.read()

            # Open image with Pillow
            try:
                image = Image.open(io.BytesIO(content))
            except Exception as e:
                raise ValueError(f"Invalid image file: {e}")

            # Validate format
            if image.format not in ALLOWED_FORMATS:
                raise ValueError(
                    f"Invalid image format: {image.format}. Allowed formats: {', '.join(ALLOWED_FORMATS)}"
                )

            # Process the image
            processed_image = self._process_image(image)

            # Save the image
            relative_path = self._save_image(processed_image)

            logger.info(f"Processed feed cover image: {relative_path}")
            return relative_path

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error processing feed cover: {e}")
            raise ValueError(f"Failed to process image: {e}")

    def _process_image(self, image: Image.Image) -> Image.Image:
        """
        Process image: crop to square and resize to 3000x3000.

        Args:
            image: PIL Image object

        Returns:
            Processed PIL Image object
        """
        # Convert RGBA/LA/P to RGB (handle transparency)
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))

            # Convert P mode to RGBA first
            if image.mode == "P":
                image = image.convert("RGBA")

            # Paste image on background using alpha channel as mask
            if image.mode in ("RGBA", "LA"):
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image)

            image = background
        elif image.mode != "RGB":
            # Convert any other mode to RGB
            image = image.convert("RGB")

        # Crop to square (center crop)
        width, height = image.size
        min_dim = min(width, height)

        # Calculate crop box (center crop)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        right = left + min_dim
        bottom = top + min_dim

        image = image.crop((left, top, right, bottom))

        # Resize to 3000x3000 using LANCZOS filter (high quality)
        image = image.resize(PODCAST_COVER_SIZE, Image.Resampling.LANCZOS)

        return image

    def _save_image(self, image: Image.Image) -> str:
        """
        Save processed image to disk.

        Args:
            image: PIL Image object to save

        Returns:
            Relative path to saved image
        """
        # Ensure feeds cover directory exists
        feeds_cover_dir = settings.covers_path / "feeds"
        feeds_cover_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        filename = f"{uuid.uuid4()}.jpg"
        file_path = feeds_cover_dir / filename

        # Save as JPEG with high quality
        image.save(file_path, "JPEG", quality=90, optimize=True)

        # Return relative path from data/ directory
        return f"covers/feeds/{filename}"

    def delete_cover(self, cover_path: str) -> bool:
        """
        Delete a feed cover image.

        Args:
            cover_path: Relative path to cover image (e.g., "feeds/uuid.jpg")

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # Construct full path
            full_path = settings.covers_path / cover_path

            # Delete file if it exists
            if full_path.exists():
                full_path.unlink()
                logger.info(f"Deleted feed cover: {cover_path}")
                return True

            logger.warning(f"Feed cover not found: {cover_path}")
            return False

        except Exception as e:
            logger.error(f"Error deleting feed cover {cover_path}: {e}")
            return False
