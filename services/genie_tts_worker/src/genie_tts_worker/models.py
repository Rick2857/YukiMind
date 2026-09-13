"""Strict versioned models for the local speech IPC protocol."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTOCOL_VERSION = 1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EngineModelVersion(StrEnum):
    V2 = "v2"
    V2_PRO_PLUS = "v2proplus"


class WorkerErrorCode(StrEnum):
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


class ReferenceInput(_StrictModel):
    reference_key: str = Field(min_length=1)
    audio_relative_path: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    language: str = Field(min_length=1)


class _Request(_StrictModel):
    protocol_version: Literal[1] = 1
    request_id: str = Field(min_length=1)


class HealthRequest(_Request):
    operation: Literal["health"] = "health"


class LoadProfileRequest(_Request):
    operation: Literal["load_profile"] = "load_profile"
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_relative_path: str = Field(min_length=1)
    engine_model_version: EngineModelVersion
    language: str = Field(min_length=1)


class UnloadProfileRequest(_Request):
    operation: Literal["unload_profile"] = "unload_profile"
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")


class ReloadProfileRequest(_Request):
    operation: Literal["reload_profile"] = "reload_profile"
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_relative_path: str = Field(min_length=1)
    engine_model_version: EngineModelVersion
    language: str = Field(min_length=1)


class SynthesizeRequest(_Request):
    operation: Literal["synthesize"] = "synthesize"
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    model_relative_path: str = Field(min_length=1)
    engine_model_version: EngineModelVersion
    language: str = Field(min_length=1)
    reference: ReferenceInput
    text: str = Field(min_length=1)
    split_sentence: bool
    output_relative_path: str = Field(min_length=1)


class CancelRequest(_Request):
    operation: Literal["cancel"] = "cancel"
    target_request_id: str = Field(min_length=1)


class ClearReferenceCacheRequest(_Request):
    operation: Literal["clear_reference_cache"] = "clear_reference_cache"


class ShutdownRequest(_Request):
    operation: Literal["shutdown"] = "shutdown"


WorkerRequest = Annotated[
    HealthRequest
    | LoadProfileRequest
    | UnloadProfileRequest
    | ReloadProfileRequest
    | SynthesizeRequest
    | CancelRequest
    | ClearReferenceCacheRequest
    | ShutdownRequest,
    Field(discriminator="operation"),
]
WORKER_REQUEST_ADAPTER: TypeAdapter[WorkerRequest] = TypeAdapter(WorkerRequest)


class SuccessResponse(_StrictModel):
    protocol_version: Literal[1] = 1
    request_id: str
    ok: Literal[True] = True
    operation: str
    status: str = "ok"
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


class FailureResponse(_StrictModel):
    protocol_version: Literal[1] = 1
    request_id: str
    ok: Literal[False] = False
    error: WorkerErrorCode
    detail: str


WorkerResponse = SuccessResponse | FailureResponse
WORKER_RESPONSE_ADAPTER: TypeAdapter[WorkerResponse] = TypeAdapter(WorkerResponse)
