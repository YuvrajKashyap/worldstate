from __future__ import annotations

import struct
from datetime import UTC, datetime

import cv2
import numpy as np
import pytest

from worldstate_api.capture import (
    FRAME_HEADER,
    FramePacket,
    FrameProtocolError,
    decode_frame,
    pack_frame,
    score_quality,
    sniff_video_media_type,
    unpack_frame,
)


def _jpeg(width: int = 16, height: int = 12) -> bytes:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, width // 2 :] = 255
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def test_frame_envelope_round_trip_and_decode() -> None:
    packet = FramePacket(
        sequence=7,
        captured_at=datetime(2026, 1, 2, tzinfo=UTC),
        width=16,
        height=12,
        encoding="jpeg",
        payload=_jpeg(),
    )

    unpacked = unpack_frame(
        pack_frame(packet),
        maximum_bytes=100_000,
        maximum_width=1920,
        maximum_height=1080,
    )
    decoded = decode_frame(unpacked)

    assert unpacked.sequence == 7
    assert unpacked.captured_at == packet.captured_at
    assert decoded.bgr.shape == (12, 16, 3)
    assert set(decoded.quality) == {
        "brightness",
        "contrast",
        "sharpness",
        "exposure",
        "keyframe_score",
    }


def test_rgba_frame_round_trip_preserves_pixels_without_image_compression() -> None:
    rgba = np.array([[[255, 0, 0, 255], [0, 255, 0, 255]]], dtype=np.uint8)
    packet = FramePacket(
        sequence=8,
        captured_at=datetime(2026, 1, 2, tzinfo=UTC),
        width=2,
        height=1,
        encoding="rgba",
        payload=rgba.tobytes(),
    )

    unpacked = unpack_frame(
        pack_frame(packet),
        maximum_bytes=100,
        maximum_width=100,
        maximum_height=100,
    )
    decoded = decode_frame(unpacked)

    assert unpacked.encoding == "rgba"
    assert decoded.bgr.tolist() == [[[0, 0, 255], [0, 255, 0]]]

    invalid = FramePacket(9, datetime.now(UTC), 2, 1, "rgba", b"too-short")
    with pytest.raises(FrameProtocolError, match="RGBA payload length"):
        decode_frame(invalid)


def test_i420_frame_round_trip_preserves_camera_yuv_without_compression() -> None:
    bgr = np.zeros((2, 4, 3), dtype=np.uint8)
    bgr[:, :] = (20, 110, 220)
    i420 = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)
    packet = FramePacket(
        sequence=10,
        captured_at=datetime(2026, 1, 2, tzinfo=UTC),
        width=4,
        height=2,
        encoding="i420",
        payload=i420.tobytes(),
    )

    unpacked = unpack_frame(
        pack_frame(packet),
        maximum_bytes=100,
        maximum_width=100,
        maximum_height=100,
    )
    decoded = decode_frame(unpacked)

    assert unpacked.encoding == "i420"
    assert decoded.bgr.shape == bgr.shape
    assert np.max(np.abs(decoded.bgr.astype(int) - bgr.astype(int))) <= 3

    invalid = FramePacket(11, datetime.now(UTC), 4, 2, "i420", b"too-short")
    with pytest.raises(FrameProtocolError, match="I420 payload length"):
        decode_frame(invalid)


@pytest.mark.parametrize(
    "message,error",
    [
        (b"short", "truncated"),
        (b"BAD!" + b"\0" * FRAME_HEADER.size, "magic"),
    ],
)
def test_frame_envelope_rejects_invalid_messages(message: bytes, error: str) -> None:
    with pytest.raises(FrameProtocolError, match=error):
        unpack_frame(
            message,
            maximum_bytes=10_000,
            maximum_width=100,
            maximum_height=100,
        )


def test_frame_envelope_rejects_limits_encoding_and_nonfinite_time() -> None:
    payload = b"x"
    oversized = FramePacket(1, datetime.now(UTC), 10, 10, "jpeg", payload * 10)
    with pytest.raises(FrameProtocolError, match="configured limit"):
        unpack_frame(
            pack_frame(oversized),
            maximum_bytes=5,
            maximum_width=100,
            maximum_height=100,
        )

    bad_encoding = FRAME_HEADER.pack(b"WSF1", 1, 0.0, 10, 10, 99) + payload
    with pytest.raises(FrameProtocolError, match="unsupported"):
        unpack_frame(
            bad_encoding,
            maximum_bytes=10,
            maximum_width=100,
            maximum_height=100,
        )

    nan_time = FRAME_HEADER.pack(b"WSF1", 1, float("nan"), 10, 10, 1) + payload
    with pytest.raises(FrameProtocolError, match="finite"):
        unpack_frame(
            nan_time,
            maximum_bytes=10,
            maximum_width=100,
            maximum_height=100,
        )


def test_decode_rejects_invalid_image_and_dimension_mismatch() -> None:
    invalid = FramePacket(1, datetime.now(UTC), 1, 1, "jpeg", b"not-an-image")
    with pytest.raises(FrameProtocolError, match="cannot be decoded"):
        decode_frame(invalid)

    mismatch = FramePacket(1, datetime.now(UTC), 99, 99, "jpeg", _jpeg())
    with pytest.raises(FrameProtocolError, match="dimensions"):
        decode_frame(mismatch)


def test_quality_and_media_sniffing_validation() -> None:
    with pytest.raises(ValueError, match="uint8 BGR"):
        score_quality(np.zeros((10, 10), dtype=np.uint8))
    assert sniff_video_media_type(struct.pack(">I4s4s", 24, b"ftyp", b"isom")) == "video/mp4"
    assert sniff_video_media_type(struct.pack(">I4s4s", 24, b"ftyp", b"qt  ")) == "video/quicktime"
    assert sniff_video_media_type(b"not-video") is None
