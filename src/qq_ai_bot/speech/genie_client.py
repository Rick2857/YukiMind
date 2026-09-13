"""Strict Unix Domain Socket client for the isolated Genie-TTS worker."""

from __future__ import annotations

import asyncio
import json
import struct
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from qq_ai_bot.speech.models import VoiceProfile, VoiceReference
from qq_ai_bot.speech.provider import SpeechProviderHealth

_LENGTH = struct.Struct(">I")


class GenieWorkerErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INCOMPATIBLE_PROTOCOL = "incompatible_protocol"
    GENIE_DATA_MISSING = "genie_data_missing"
    PROFILE_MISSING = "profile_missing"
    PROFILE_INVALID = "profile_invalid"
    MODEL_UNSUPPORTED = "model_unsupported"
    MODEL_LOAD_FAILED = "model_load_failed"
    REFERENCE_MISSING = "reference_missing"
    REFERENCE_INVALID = "reference_invalid"
    SYNTHESIS_FAILED = "synthesis_failed"
    OUTPUT_INVALID = "output_invalid"
    CANCELLED = "cancelled"
    WORKER_BUSY = "worker_busy"
    JAPANESE_FRONTEND_UNAVAILABLE = "japanese_frontend_unavailable"
    INTERNAL_ERROR = "internal_error"


class GenieWorkerUnavailable(ConnectionError):
    """The configured local worker cannot be reached."""


class GenieWorkerFailure(RuntimeError):
    def __init__(self, code: GenieWorkerErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Success(_WireModel):
    protocol_version: Literal[1]
    request_id: str
    ok: Literal[True]
    operation: str
    status: str
    output_relative_path: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    sample_width: int | None = None
    duration_milliseconds: int | None = None
    loaded_profile_id: str | None = None
    ready: bool | None = None
    busy: bool | None = None
    japanese_frontend_available: bool | None = None
    japanese_frontend_version: str | None = None
    japanese_frontend_signature: str | None = None
    spoken_text_hash: str | None = None
    frontend_version: str | None = None
    transformed_token_count: int | None = None


class _Failure(_WireModel):
    protocol_version: Literal[1]
    request_id: str
    ok: Literal[False]
    error: GenieWorkerErrorCode
    detail: str


_Response = Annotated[_Success | _Failure, Field(discriminator="ok")]
_RESPONSE_ADAPTER: TypeAdapter[_Response] = TypeAdapter(_Response)


class GenieWorkerClient:
    """One-request-per-connection IPC client; audio never crosses this socket."""

    def __init__(self, socket_path: Path, *, request_timeout_seconds: float) -> None:
        self._socket_path = socket_path
        self._timeout = request_timeout_seconds

    async def health(self) -> SpeechProviderHealth:
        try:
            result = await self._call({"operation": "health"})
        except GenieWorkerUnavailable as exc:
            return SpeechProviderHealth(False, False, False, False, detail=str(exc))
        except GenieWorkerFailure as exc:
            return SpeechProviderHealth(False, True, False, False, detail=exc.code.value)
        return SpeechProviderHealth(
            available=bool(result.ready),
            connected=True,
            ready=bool(result.ready),
            busy=bool(result.busy),
            loaded_profile_id=result.loaded_profile_id,
            japanese_frontend_available=result.japanese_frontend_available,
            japanese_frontend_version=result.japanese_frontend_version,
            japanese_frontend_signature=result.japanese_frontend_signature,
        )

    async def japanese_frontend_signature(self) -> str:
        result = await self._call({"operation": "health"})
        if not result.japanese_frontend_available or not result.japanese_frontend_signature:
            raise GenieWorkerFailure(
                GenieWorkerErrorCode.JAPANESE_FRONTEND_UNAVAILABLE,
                "Japanese speech frontend is unavailable",
            )
        return result.japanese_frontend_signature

    async def load_profile(self, profile: VoiceProfile, *, reload: bool = False) -> None:
        await self._call(
            {
                "operation": "reload_profile" if reload else "load_profile",
                "profile_id": profile.profile_id,
                "model_relative_path": profile.model_relative_path,
                "engine_model_version": profile.engine_model_version.value,
                "language": profile.language,
            }
        )

    async def unload_profile(self, profile_id: str) -> None:
        await self._call({"operation": "unload_profile", "profile_id": profile_id})

    async def clear_reference_cache(self) -> None:
        await self._call({"operation": "clear_reference_cache"})

    async def shutdown(self) -> None:
        await self._call({"operation": "shutdown"})

    async def synthesize(
        self,
        *,
        request_id: str,
        profile: VoiceProfile,
        reference: VoiceReference,
        target_language: str,
        text: str,
        split_sentence: bool,
        output_relative_path: str,
        cancellation: asyncio.Event | None,
    ) -> _Success:
        call = asyncio.create_task(
            self._call(
                {
                    "operation": "synthesize",
                    "request_id": request_id,
                    "profile_id": profile.profile_id,
                    "model_relative_path": profile.model_relative_path,
                    "engine_model_version": profile.engine_model_version.value,
                    "language": target_language,
                    "reference": {
                        "reference_key": reference.reference_key,
                        "audio_relative_path": reference.audio_relative_path,
                        "transcript": reference.transcript,
                        "language": reference.language,
                    },
                    "text": text,
                    "split_sentence": split_sentence,
                    "output_relative_path": output_relative_path,
                }
            )
        )
        if cancellation is None:
            return await call
        cancelled = asyncio.create_task(cancellation.wait())
        try:
            done, _ = await asyncio.wait({call, cancelled}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            cancelled.cancel()
            try:
                await asyncio.shield(
                    self._call(
                        {
                            "operation": "cancel",
                            "target_request_id": request_id,
                        }
                    )
                )
            except (GenieWorkerUnavailable, GenieWorkerFailure):
                pass
            call.cancel()
            try:
                await call
            except asyncio.CancelledError:
                pass
            raise
        if call in done:
            cancelled.cancel()
            return await call
        try:
            await self._call(
                {
                    "operation": "cancel",
                    "target_request_id": request_id,
                }
            )
        finally:
            call.cancel()
        raise asyncio.CancelledError

    async def _call(self, payload: dict[str, object]) -> _Success:
        body = {
            "protocol_version": 1,
            "request_id": str(payload.get("request_id") or uuid4()),
            **payload,
        }
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            async with asyncio.timeout(self._timeout):
                open_unix_connection = cast(Any, asyncio).open_unix_connection
                reader, writer = await open_unix_connection(self._socket_path)
                try:
                    writer.write(_LENGTH.pack(len(raw)) + raw)
                    await writer.drain()
                    header = await reader.readexactly(_LENGTH.size)
                    (size,) = _LENGTH.unpack(header)
                    response_raw = await reader.readexactly(size)
                finally:
                    writer.close()
                    await writer.wait_closed()
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as exc:
            raise GenieWorkerUnavailable("local Genie-TTS worker is unavailable") from exc
        response = _RESPONSE_ADAPTER.validate_json(response_raw)
        if isinstance(response, _Failure):
            raise GenieWorkerFailure(response.error, response.detail)
        return response

    async def close(self) -> None:
        """Connections are request-scoped, so no persistent resource remains."""
