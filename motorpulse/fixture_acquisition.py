"""Experimental in-memory fixture packets; never a live device interface."""

from __future__ import annotations

import struct
from typing import Any
import zlib

from .sensor_gateway import (
    MAX_FRAME_BYTES,
    _utc,
    canonical_frame_bytes,
    parse_frame_json,
)

MAGIC = b"MPF1"
HEADER = struct.Struct(">4sII")
MAX_PAYLOAD_BYTES = MAX_FRAME_BYTES - 1
MAX_BATCH_BYTES = 16 * 1024 * 1024
MAX_PACKETS = 300
NATIVE_RATE = 4000


def _fixture_payload(frame: dict[str, Any]) -> bytes:
    try:
        payload = canonical_frame_bytes(frame)
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("invalid fixture frame") from exc
    if not all(
        frame[key].startswith("fixture-") for key in ("device_id", "asset_id")
    ):
        raise ValueError("fixture identities required")
    sampling = (frame["sample_rate_hz"], frame["sample_count"])
    if sampling != (NATIVE_RATE, NATIVE_RATE):
        raise ValueError("native fixture rate and sample count must be 4000")
    if not 0 < len(payload) <= MAX_PAYLOAD_BYTES:
        raise ValueError("fixture payload exceeds size limit")
    return payload


def encode_fixture_packet(frame: dict[str, Any]) -> bytes:
    """Encode one generated capture-v1 fixture, not a hardware wire protocol."""
    payload = _fixture_payload(frame)
    return HEADER.pack(MAGIC, len(payload), zlib.crc32(payload)) + payload


def decode_fixture_batch(data: bytes) -> list[dict[str, Any]]:
    """Decode one complete bounded in-memory batch or reject it entirely."""
    if type(data) is not bytes or not 0 < len(data) <= MAX_BATCH_BYTES:
        raise ValueError("invalid fixture batch size or type")
    frames: list[dict[str, Any]] = []
    offset = 0
    while offset < len(data):
        if len(frames) >= MAX_PACKETS:
            raise ValueError("fixture packet count exceeds limit")
        if len(data) - offset < HEADER.size:
            raise ValueError("truncated fixture header")
        magic, length, checksum = HEADER.unpack_from(data, offset)
        offset += HEADER.size
        if magic != MAGIC:
            raise ValueError("invalid fixture magic")
        if not 0 < length <= MAX_PAYLOAD_BYTES:
            raise ValueError("invalid fixture payload length")
        if length > len(data) - offset:
            raise ValueError("truncated fixture payload")
        payload = data[offset : offset + length]
        offset += length
        if zlib.crc32(payload) != checksum:
            raise ValueError("fixture checksum mismatch")
        try:
            frame = parse_frame_json(payload.decode("utf-8"))
        except (UnicodeError, RecursionError) as exc:
            raise ValueError("invalid fixture JSON") from exc
        if _fixture_payload(frame) != payload:
            raise ValueError("fixture payload must be canonical")
        if frames:
            previous = frames[-1]
            for key in ("device_id", "asset_id", "provenance"):
                if frame[key] != previous[key]:
                    raise ValueError("fixture session identity changed")
            if frame["sequence"] != previous["sequence"] + 1:
                raise ValueError("fixture sequence discontinuity")
            if frame["device_uptime_ms"] <= previous["device_uptime_ms"]:
                raise ValueError("fixture uptime must increase")
            if _utc(frame["captured_at_utc"]) <= _utc(previous["captured_at_utc"]):
                raise ValueError("fixture UTC must increase")
        frames.append(frame)
    return frames
