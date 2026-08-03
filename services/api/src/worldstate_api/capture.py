"""Bounded frame envelopes, image decoding, and capture quality metrics."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

import cv2
import numpy as np

FRAME_MAGIC = b"WSF1"
FRAME_HEADER = struct.Struct(">4sQdHHB3x")
ENCODING_JPEG = 1
ENCODING_WEBP = 2
ENCODING_RGBA = 3
ENCODING_I420 = 4


class FrameProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FramePacket:
    sequence: int
    captured_at: datetime
    width: int
    height: int
    encoding: Literal["jpeg", "webp", "rgba", "i420"]
    payload: bytes


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    packet: FramePacket
    bgr: np.ndarray
    quality: dict[str, float]


def pack_frame(packet: FramePacket) -> bytes:
    encoding_code = {
        "jpeg": ENCODING_JPEG,
        "webp": ENCODING_WEBP,
        "rgba": ENCODING_RGBA,
        "i420": ENCODING_I420,
    }[packet.encoding]
    timestamp = packet.captured_at.timestamp()
    return (
        FRAME_HEADER.pack(
            FRAME_MAGIC,
            packet.sequence,
            timestamp,
            packet.width,
            packet.height,
            encoding_code,
        )
        + packet.payload
    )


def unpack_frame(
    message: bytes,
    *,
    maximum_bytes: int,
    maximum_width: int,
    maximum_height: int,
) -> FramePacket:
    if len(message) <= FRAME_HEADER.size:
        raise FrameProtocolError("frame packet is truncated")
    if len(message) - FRAME_HEADER.size > maximum_bytes:
        raise FrameProtocolError("encoded frame exceeds the configured limit")

    magic, sequence, captured_at, width, height, encoding_code = FRAME_HEADER.unpack_from(message)
    if magic != FRAME_MAGIC:
        raise FrameProtocolError("frame magic or protocol version is invalid")
    if captured_at != captured_at or captured_at in {float("inf"), float("-inf")}:
        raise FrameProtocolError("frame timestamp must be finite")
    if not 1 <= width <= maximum_width or not 1 <= height <= maximum_height:
        raise FrameProtocolError("frame dimensions exceed the configured limit")
    if encoding_code == ENCODING_JPEG:
        encoding: Literal["jpeg", "webp", "rgba", "i420"] = "jpeg"
    elif encoding_code == ENCODING_WEBP:
        encoding = "webp"
    elif encoding_code == ENCODING_RGBA:
        encoding = "rgba"
    elif encoding_code == ENCODING_I420:
        encoding = "i420"
    else:
        raise FrameProtocolError("frame encoding is unsupported")
    try:
        timestamp = datetime.fromtimestamp(captured_at, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise FrameProtocolError("frame timestamp is outside the supported range") from error
    return FramePacket(
        sequence=sequence,
        captured_at=timestamp,
        width=width,
        height=height,
        encoding=encoding,
        payload=message[FRAME_HEADER.size :],
    )


def decode_frame(packet: FramePacket) -> DecodedFrame:
    if packet.encoding == "rgba":
        expected_bytes = packet.width * packet.height * 4
        if len(packet.payload) != expected_bytes:
            raise FrameProtocolError("RGBA payload length does not match the frame header")
        rgba = np.frombuffer(packet.payload, dtype=np.uint8).reshape(packet.height, packet.width, 4)
        image = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    elif packet.encoding == "i420":
        if packet.width % 2 != 0 or packet.height % 2 != 0:
            raise FrameProtocolError("I420 frame dimensions must be even")
        expected_bytes = packet.width * packet.height * 3 // 2
        if len(packet.payload) != expected_bytes:
            raise FrameProtocolError("I420 payload length does not match the frame header")
        i420 = np.frombuffer(packet.payload, dtype=np.uint8).reshape(
            packet.height * 3 // 2,
            packet.width,
        )
        image = cv2.cvtColor(i420, cv2.COLOR_YUV2BGR_I420)
    else:
        encoded = np.frombuffer(packet.payload, dtype=np.uint8)
        image = cast(np.ndarray | None, cv2.imdecode(encoded, cv2.IMREAD_COLOR))
        if image is None or image.ndim != 3 or image.shape[2] != 3:
            raise FrameProtocolError("encoded frame cannot be decoded as a color image")
    height, width = image.shape[:2]
    if (width, height) != (packet.width, packet.height):
        raise FrameProtocolError("encoded dimensions do not match the frame header")
    return DecodedFrame(packet=packet, bgr=image, quality=score_quality(image))


def score_quality(image_bgr: np.ndarray) -> dict[str, float]:
    """Return normalized, explainable capture-quality signals."""

    if image_bgr.dtype != np.uint8 or image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("quality scoring requires a uint8 BGR image")
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray) / 255.0)
    contrast = float(min(1.0, np.std(gray) / 64.0))
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = float(min(1.0, laplacian_variance / 500.0))
    dark_fraction = float(np.mean(gray < 18))
    clipped_fraction = float(np.mean(gray > 245))
    exposure = float(max(0.0, 1.0 - dark_fraction - clipped_fraction))
    keyframe_score = float(max(0.0, min(1.0, 0.45 * sharpness + 0.30 * exposure + 0.25 * contrast)))
    return {
        "brightness": brightness,
        "contrast": contrast,
        "sharpness": sharpness,
        "exposure": exposure,
        "keyframe_score": keyframe_score,
    }


def sniff_video_media_type(prefix: bytes) -> Literal["video/mp4", "video/quicktime"] | None:
    """Recognize ISO base media files without trusting the filename."""

    if len(prefix) < 12 or prefix[4:8] != b"ftyp":
        return None
    brand = prefix[8:12]
    if brand == b"qt  ":
        return "video/quicktime"
    return "video/mp4"
