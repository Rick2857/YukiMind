"""Four-byte big-endian length framing for UTF-8 JSON messages."""

from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

from pydantic import ValidationError

from genie_tts_worker.models import (
    WORKER_REQUEST_ADAPTER,
    WORKER_RESPONSE_ADAPTER,
    WorkerRequest,
    WorkerResponse,
)

_LENGTH = struct.Struct(">I")


def encode_payload(payload: WorkerRequest | WorkerResponse) -> bytes:
    body = json.dumps(
        payload.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _LENGTH.pack(len(body)) + body


async def read_json_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    header = await reader.readexactly(_LENGTH.size)
    (size,) = _LENGTH.unpack(header)
    body = await reader.readexactly(size)
    decoded = json.loads(body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("IPC frame must contain a JSON object")
    return decoded


async def write_frame(
    writer: asyncio.StreamWriter, payload: WorkerRequest | WorkerResponse
) -> None:
    writer.write(encode_payload(payload))
    await writer.drain()


async def read_request(reader: asyncio.StreamReader) -> WorkerRequest:
    payload = await read_json_frame(reader)
    return WORKER_REQUEST_ADAPTER.validate_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


async def read_response(reader: asyncio.StreamReader) -> WorkerResponse:
    payload = await read_json_frame(reader)
    return WORKER_RESPONSE_ADAPTER.validate_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


__all__ = [
    "ValidationError",
    "encode_payload",
    "read_json_frame",
    "read_request",
    "read_response",
    "write_frame",
]
