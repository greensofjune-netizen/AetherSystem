"""Validated local image attachments shared by chat API surfaces."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_IMAGE_BYTES = 2_000_000
MAX_IMAGES_PER_MESSAGE = 4
MAX_TOTAL_IMAGE_BYTES = 6_000_000
ImageMediaType = Literal["image/jpeg", "image/png", "image/webp"]


class ImageAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    media_type: ImageMediaType
    data: str = Field(min_length=1, max_length=2_800_000)

    @model_validator(mode="after")
    def validate_image(self) -> ImageAttachment:
        if Path(self.name).name != self.name or "\\" in self.name:
            raise ValueError("Image name must be a plain filename.")
        try:
            image = base64.b64decode(self.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Image data must be valid base64.") from error
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise ValueError("Each image must be no larger than 2,000,000 bytes.")
        if not _matches_media_type(image, self.media_type):
            raise ValueError("Image content does not match its declared type.")
        return self

    def decoded_data(self) -> bytes:
        """Return the validated image bytes."""
        return base64.b64decode(self.data, validate=True)


def validate_image_batch(images: list[ImageAttachment]) -> int:
    """Validate message-level image count and total decoded byte limits."""
    if len(images) > MAX_IMAGES_PER_MESSAGE:
        raise ValueError(f"Attach no more than {MAX_IMAGES_PER_MESSAGE} images.")
    total_bytes = sum(len(image.decoded_data()) for image in images)
    if total_bytes > MAX_TOTAL_IMAGE_BYTES:
        raise ValueError("Images exceed the 6,000,000-byte total limit.")
    return total_bytes


def _matches_media_type(data: bytes, media_type: ImageMediaType) -> bool:
    if media_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if media_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
