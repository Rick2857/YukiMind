"""The only adapter allowed to import and call ``genie_tts``."""

from __future__ import annotations

import ctypes
import gc
import importlib
import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from genie_tts_worker.models import EngineModelVersion, SynthesizeRequest, WorkerErrorCode
from genie_tts_worker.paths import SpeechPathError, SpeechPathPolicy

GENIE_TTS_VERSION = "2.0.2"
SAMPLE_RATE = 32_000
CHANNELS = 1
SAMPLE_WIDTH = 2


class EngineFailure(RuntimeError):
    def __init__(self, code: WorkerErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class WaveMetadata:
    relative_path: str
    sample_rate: int
    channels: int
    sample_width: int
    duration_milliseconds: int


class GenieModule(Protocol):
    def load_character(
        self, *, character_name: str, onnx_model_dir: str, language: str
    ) -> object: ...

    def unload_character(self, character_name: str) -> object: ...

    def set_reference_audio(
        self, *, character_name: str, audio_path: str, audio_text: str, language: str
    ) -> object: ...

    def tts(
        self,
        *,
        character_name: str,
        text: str,
        play: bool,
        split_sentence: bool,
        save_path: str,
    ) -> object: ...

    def stop(self) -> object: ...

    def clear_reference_audio_cache(self) -> object: ...


class GenieEngine:
    def __init__(
        self,
        *,
        paths: SpeechPathPolicy,
        genie_data_dir: Path,
        module: GenieModule | None = None,
    ) -> None:
        self._paths = paths
        self._genie_data_dir = genie_data_dir.resolve()
        self._module = module
        self._loaded_profile_id: str | None = None
        self._loaded_language: str | None = None

    @property
    def loaded_profile_id(self) -> str | None:
        return self._loaded_profile_id

    def initialize(self) -> None:
        if not self._genie_data_dir.is_dir() or not any(self._genie_data_dir.iterdir()):
            raise EngineFailure(WorkerErrorCode.GENIE_DATA_MISSING, "GenieData is missing")
        configured = Path(os.environ.get("GENIE_DATA_DIR", "")).resolve()
        if configured != self._genie_data_dir:
            raise EngineFailure(
                WorkerErrorCode.GENIE_DATA_MISSING,
                "GENIE_DATA_DIR was not configured before engine initialization",
            )
        if self._module is None:
            self._module = importlib.import_module("genie_tts")

    def load_profile(
        self,
        *,
        profile_id: str,
        model_relative_path: str,
        engine_model_version: EngineModelVersion,
        language: str,
        reload: bool = False,
    ) -> None:
        if engine_model_version not in {EngineModelVersion.V2, EngineModelVersion.V2_PRO_PLUS}:
            raise EngineFailure(
                WorkerErrorCode.MODEL_UNSUPPORTED, "unsupported Genie model version"
            )
        try:
            model_path = self._paths.profile_model(profile_id, model_relative_path)
        except SpeechPathError as exc:
            raise EngineFailure(WorkerErrorCode.PROFILE_INVALID, str(exc)) from exc
        module = self._require_module()
        try:
            if (
                self._loaded_profile_id == profile_id
                and self._loaded_language == language
                and not reload
            ):
                return
            if self._loaded_profile_id is not None:
                module.unload_character(self._loaded_profile_id)
                _return_unused_heap_memory()
            module.load_character(
                character_name=profile_id,
                onnx_model_dir=str(model_path),
                language=language,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._loaded_profile_id = None
            self._loaded_language = None
            _return_unused_heap_memory()
            raise EngineFailure(WorkerErrorCode.MODEL_LOAD_FAILED, type(exc).__name__) from exc
        _return_unused_heap_memory()
        self._loaded_profile_id = profile_id
        self._loaded_language = language

    def unload_profile(self, profile_id: str) -> None:
        if self._loaded_profile_id != profile_id:
            return
        module = self._require_module()
        try:
            module.unload_character(profile_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise EngineFailure(WorkerErrorCode.MODEL_LOAD_FAILED, type(exc).__name__) from exc
        _return_unused_heap_memory()
        self._loaded_profile_id = None
        self._loaded_language = None

    def synthesize(self, request: SynthesizeRequest) -> WaveMetadata:
        self.load_profile(
            profile_id=request.profile_id,
            model_relative_path=request.model_relative_path,
            engine_model_version=request.engine_model_version,
            language=request.language,
        )
        try:
            reference_path = self._paths.profile_reference(
                request.profile_id, request.reference.audio_relative_path
            )
            output_path = self._paths.cache_output(request.output_relative_path)
        except SpeechPathError as exc:
            raise EngineFailure(WorkerErrorCode.REFERENCE_INVALID, str(exc)) from exc
        temporary = output_path.with_name(f".{output_path.stem}.{request.request_id}.part.wav")
        module = self._require_module()
        try:
            module.set_reference_audio(
                character_name=request.profile_id,
                audio_path=str(reference_path),
                audio_text=request.reference.transcript,
                language=request.reference.language,
            )
            module.tts(
                character_name=request.profile_id,
                text=request.text,
                play=False,
                split_sentence=request.split_sentence,
                save_path=str(temporary),
            )
            metadata = self._validate_wave(temporary, request.output_relative_path)
            os.replace(temporary, output_path)
            return metadata
        except EngineFailure:
            temporary.unlink(missing_ok=True)
            raise
        except (OSError, RuntimeError, ValueError, wave.Error) as exc:
            temporary.unlink(missing_ok=True)
            raise EngineFailure(WorkerErrorCode.SYNTHESIS_FAILED, type(exc).__name__) from exc
        finally:
            _return_unused_heap_memory()

    def stop(self) -> None:
        module = self._require_module()
        try:
            module.stop()
        except (OSError, RuntimeError, ValueError) as exc:
            raise EngineFailure(WorkerErrorCode.CANCELLED, type(exc).__name__) from exc

    def clear_reference_cache(self) -> None:
        module = self._require_module()
        try:
            module.clear_reference_audio_cache()
        except (OSError, RuntimeError, ValueError) as exc:
            raise EngineFailure(WorkerErrorCode.INTERNAL_ERROR, type(exc).__name__) from exc
        _return_unused_heap_memory()

    def discard_output(self, relative_path: str) -> None:
        self._paths.resolve(relative_path).unlink(missing_ok=True)

    def shutdown(self) -> None:
        module = self._require_module()
        try:
            module.stop()
            if self._loaded_profile_id is not None:
                module.unload_character(self._loaded_profile_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise EngineFailure(WorkerErrorCode.INTERNAL_ERROR, type(exc).__name__) from exc
        finally:
            self._loaded_profile_id = None
            self._loaded_language = None
            _return_unused_heap_memory()

    def _validate_wave(self, path: Path, relative_path: str) -> WaveMetadata:
        if not path.is_file() or path.stat().st_size == 0:
            raise EngineFailure(WorkerErrorCode.OUTPUT_INVALID, "Genie produced no WAV output")
        try:
            with wave.open(str(path), "rb") as reader:
                sample_rate = reader.getframerate()
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                frames = reader.getnframes()
        except (OSError, wave.Error) as exc:
            raise EngineFailure(WorkerErrorCode.OUTPUT_INVALID, "invalid WAV output") from exc
        if (sample_rate, channels, sample_width) != (SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH):
            raise EngineFailure(
                WorkerErrorCode.OUTPUT_INVALID,
                "WAV must be 32 kHz mono 16-bit PCM",
            )
        duration = round(frames * 1000 / sample_rate)
        return WaveMetadata(relative_path, sample_rate, channels, sample_width, duration)

    def _require_module(self) -> GenieModule:
        if self._module is None:
            raise EngineFailure(WorkerErrorCode.INTERNAL_ERROR, "Genie engine is not initialized")
        return self._module


def _return_unused_heap_memory() -> None:
    """Best-effort release of large temporary ONNX buffers back to the Linux host."""

    gc.collect()
    if os.name != "posix":
        return
    try:
        malloc_trim = getattr(ctypes.CDLL(None), "malloc_trim", None)
        if malloc_trim is not None:
            malloc_trim(0)
    except (AttributeError, OSError):
        # Non-glibc platforms can safely rely on their allocator's own policy.
        return
