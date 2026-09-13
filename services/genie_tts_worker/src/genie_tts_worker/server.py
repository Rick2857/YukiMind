"""Concurrent control-plane, serial-synthesis Unix socket server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from genie_tts_worker.engine import EngineFailure, GenieEngine
from genie_tts_worker.models import (
    CancelRequest,
    ClearReferenceCacheRequest,
    FailureResponse,
    HealthRequest,
    LoadProfileRequest,
    ReloadProfileRequest,
    ShutdownRequest,
    SuccessResponse,
    SynthesizeRequest,
    UnloadProfileRequest,
    WorkerErrorCode,
    WorkerRequest,
    WorkerResponse,
)
from genie_tts_worker.protocol import read_request, write_frame
from genie_tts_worker.text_frontends import (
    SpeechFrontendRegistry,
    SpeechTextFrontendUnavailable,
)


class GenieWorkerServer:
    def __init__(
        self,
        *,
        socket_path: Path,
        engine: GenieEngine,
        socket_mode: int,
        idle_recycle_seconds: float = 0,
        text_frontends: SpeechFrontendRegistry | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._engine = engine
        self._socket_mode = socket_mode
        self._server: asyncio.AbstractServer | None = None
        self._synthesis_lock = asyncio.Lock()
        self._shutdown = asyncio.Event()
        self._shutdown_task: asyncio.Task[None] | None = None
        self._current_request_id: str | None = None
        self._cancelled_request_ids: set[str] = set()
        self._idle_recycle_seconds = max(0.0, idle_recycle_seconds)
        self._idle_recycle_task: asyncio.Task[None] | None = None
        self._text_frontends = text_frontends or SpeechFrontendRegistry()

    @property
    def queue_depth(self) -> int:
        return int(self._synthesis_lock.locked())

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.unlink(missing_ok=True)
        start_unix_server = cast(Any, asyncio).start_unix_server
        self._server = await start_unix_server(self._handle_client, path=self._socket_path)
        os.chmod(self._socket_path, self._socket_mode)
        try:
            self._engine.initialize()
        except EngineFailure:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._socket_path.unlink(missing_ok=True)
            raise

    async def serve_until_shutdown(self) -> None:
        if self._server is None:
            raise RuntimeError("worker server has not started")
        await self._shutdown.wait()
        self._server.close()
        await self._server.wait_closed()
        self._socket_path.unlink(missing_ok=True)
        self._cancel_idle_recycle()

    async def request_shutdown(self) -> None:
        if self._shutdown.is_set():
            return
        self._cancel_idle_recycle()
        if self._current_request_id is not None:
            await self._stop_engine(self._current_request_id)
        await asyncio.to_thread(self._engine.shutdown)
        self._shutdown.set()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while not reader.at_eof():
                try:
                    request = await read_request(reader)
                except asyncio.IncompleteReadError:
                    break
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    ValidationError,
                    ValueError,
                ) as exc:
                    await write_frame(
                        writer,
                        FailureResponse(
                            request_id="unknown",
                            error=WorkerErrorCode.INVALID_REQUEST,
                            detail=type(exc).__name__,
                        ),
                    )
                    break
                response = await self._dispatch(request)
                await write_frame(writer, response)
                if isinstance(request, ShutdownRequest):
                    break
        except (ConnectionError, BrokenPipeError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    async def _dispatch(self, request: WorkerRequest) -> WorkerResponse:
        try:
            if isinstance(request, HealthRequest):
                japanese = self._text_frontends.health("jp")
                return self._success(
                    request,
                    ready=True,
                    busy=self._synthesis_lock.locked(),
                    loaded_profile_id=self._engine.loaded_profile_id,
                    japanese_frontend_available=(
                        japanese.available if japanese is not None else None
                    ),
                    japanese_frontend_version=(japanese.version if japanese is not None else None),
                    japanese_frontend_signature=(
                        japanese.signature if japanese is not None else None
                    ),
                )
            if isinstance(request, LoadProfileRequest):
                self._cancel_idle_recycle()
                await asyncio.to_thread(
                    self._engine.load_profile,
                    profile_id=request.profile_id,
                    model_relative_path=request.model_relative_path,
                    engine_model_version=request.engine_model_version,
                    language=request.language,
                )
                self._schedule_idle_recycle()
                return self._success(request, loaded_profile_id=request.profile_id)
            if isinstance(request, ReloadProfileRequest):
                self._cancel_idle_recycle()
                await asyncio.to_thread(
                    self._engine.load_profile,
                    profile_id=request.profile_id,
                    model_relative_path=request.model_relative_path,
                    engine_model_version=request.engine_model_version,
                    language=request.language,
                    reload=True,
                )
                self._schedule_idle_recycle()
                return self._success(request, loaded_profile_id=request.profile_id)
            if isinstance(request, UnloadProfileRequest):
                self._cancel_idle_recycle()
                await asyncio.to_thread(self._engine.unload_profile, request.profile_id)
                self._schedule_idle_recycle()
                return self._success(request)
            if isinstance(request, SynthesizeRequest):
                self._cancel_idle_recycle()
                return await self._synthesize(request)
            if isinstance(request, CancelRequest):
                cancelled = await self._stop_engine(request.target_request_id)
                return self._success(request, status="cancelled" if cancelled else "not_running")
            if isinstance(request, ClearReferenceCacheRequest):
                await asyncio.to_thread(self._engine.clear_reference_cache)
                return self._success(request)
            if isinstance(request, ShutdownRequest):
                self._shutdown_task = asyncio.create_task(self.request_shutdown())
                return self._success(request, status="shutting_down")
            raise TypeError(f"unhandled request type: {type(request).__name__}")
        except EngineFailure as exc:
            return FailureResponse(
                request_id=request.request_id,
                error=exc.code,
                detail=self._sanitize_detail(exc.detail),
            )

    async def _synthesize(self, request: SynthesizeRequest) -> WorkerResponse:
        async with self._synthesis_lock:
            self._current_request_id = request.request_id
            try:
                if request.request_id in self._cancelled_request_ids:
                    return self._cancelled(request)
                processed = self._text_frontends.process(request.language, request.text)
                synthesis_request = (
                    request.model_copy(update={"text": processed.spoken_text})
                    if processed is not None
                    else request
                )
                metadata = await asyncio.to_thread(self._engine.synthesize, synthesis_request)
                if request.request_id in self._cancelled_request_ids:
                    self._engine.discard_output(metadata.relative_path)
                    return self._cancelled(request)
                return self._success(
                    request,
                    output_relative_path=metadata.relative_path,
                    sample_rate=metadata.sample_rate,
                    channels=metadata.channels,
                    sample_width=metadata.sample_width,
                    duration_milliseconds=metadata.duration_milliseconds,
                    loaded_profile_id=request.profile_id,
                    spoken_text_hash=(
                        processed.spoken_text_hash if processed is not None else None
                    ),
                    frontend_version=(
                        processed.frontend_version if processed is not None else None
                    ),
                    transformed_token_count=(
                        len(processed.transformed_tokens) if processed is not None else 0
                    ),
                )
            except SpeechTextFrontendUnavailable as exc:
                return FailureResponse(
                    request_id=request.request_id,
                    error=WorkerErrorCode.JAPANESE_FRONTEND_UNAVAILABLE,
                    detail=str(exc),
                )
            except EngineFailure as exc:
                if request.request_id in self._cancelled_request_ids:
                    return self._cancelled(request)
                return FailureResponse(
                    request_id=request.request_id,
                    error=exc.code,
                    detail=self._sanitize_detail(exc.detail),
                )
            finally:
                self._cancelled_request_ids.discard(request.request_id)
                self._current_request_id = None
                self._schedule_idle_recycle()

    async def _stop_engine(self, request_id: str) -> bool:
        if request_id != self._current_request_id:
            return False
        self._cancelled_request_ids.add(request_id)
        try:
            await asyncio.to_thread(self._engine.stop)
        except EngineFailure:
            return True
        return True

    def _schedule_idle_recycle(self) -> None:
        if self._idle_recycle_seconds <= 0 or self._shutdown.is_set():
            return
        self._cancel_idle_recycle()
        self._idle_recycle_task = asyncio.create_task(self._recycle_after_idle())

    def _cancel_idle_recycle(self) -> None:
        task = self._idle_recycle_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        if task is not asyncio.current_task():
            self._idle_recycle_task = None

    async def _recycle_after_idle(self) -> None:
        try:
            await asyncio.sleep(self._idle_recycle_seconds)
            if self._synthesis_lock.locked() or self._shutdown.is_set():
                return
            await self.request_shutdown()
        except asyncio.CancelledError:
            return

    @staticmethod
    def _success(request: WorkerRequest, **updates: object) -> SuccessResponse:
        return SuccessResponse.model_validate(
            {"request_id": request.request_id, "operation": request.operation, **updates}
        )

    @staticmethod
    def _cancelled(request: WorkerRequest) -> FailureResponse:
        return FailureResponse(
            request_id=request.request_id,
            error=WorkerErrorCode.CANCELLED,
            detail="synthesis was cancelled",
        )

    def _sanitize_detail(self, detail: str) -> str:
        return detail.replace(str(self._socket_path), "<socket>")
