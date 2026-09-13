from __future__ import annotations

import asyncio
import os
import stat
import threading
import time
import wave
from pathlib import Path

import pytest
from pydantic import ValidationError

from genie_tts_worker.engine import CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH, GenieEngine
from genie_tts_worker.main import configure_offline_environment
from genie_tts_worker.models import (
    WORKER_REQUEST_ADAPTER,
    EngineModelVersion,
    FailureResponse,
    HealthRequest,
    ReferenceInput,
    SynthesizeRequest,
    WorkerErrorCode,
)
from genie_tts_worker.paths import SpeechPathError, SpeechPathPolicy
from genie_tts_worker.protocol import encode_payload, read_response, write_frame
from genie_tts_worker.server import GenieWorkerServer


class FakeGenie:
    def __init__(self, *, delay: float = 0) -> None:
        self.loaded: str | None = None
        self.reference_path = ""
        self.reference_text = ""
        self.reference_language = ""
        self.loaded_languages: list[str] = []
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.stopped = False
        self.cache_cleared = False
        self._lock = threading.Lock()

    def load_character(self, *, character_name: str, onnx_model_dir: str, language: str) -> None:
        assert Path(onnx_model_dir).is_dir()
        assert language
        self.loaded = character_name
        self.loaded_languages.append(language)

    def unload_character(self, character_name: str) -> None:
        assert character_name == self.loaded
        self.loaded = None

    def set_reference_audio(
        self, *, character_name: str, audio_path: str, audio_text: str, language: str
    ) -> None:
        assert character_name == self.loaded
        self.reference_path = audio_path
        self.reference_text = audio_text
        self.reference_language = language

    def tts(
        self,
        *,
        character_name: str,
        text: str,
        play: bool,
        split_sentence: bool,
        save_path: str,
    ) -> None:
        assert character_name == self.loaded
        assert text and not play
        assert isinstance(split_sentence, bool)
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            _write_wave(Path(save_path))
        finally:
            with self._lock:
                self.active -= 1

    def stop(self) -> None:
        self.stopped = True

    def clear_reference_audio_cache(self) -> None:
        self.cache_cleared = True


def _write_wave(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(CHANNELS)
        writer.setsampwidth(SAMPLE_WIDTH)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(b"\0\0" * 320)


@pytest.fixture
def speech_layout(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "speech"
    data = root / "genie_data"
    model = root / "voices" / "yuki" / "model"
    references = root / "voices" / "yuki" / "references"
    for directory in (data, model, references, root / "cache"):
        directory.mkdir(parents=True)
    (data / "resource.bin").write_bytes(b"offline")
    (model / "model.onnx").write_bytes(b"onnx")
    _write_wave(references / "neutral.wav")
    return root, data


def _synthesis(request_id: str = "request-1") -> SynthesizeRequest:
    return SynthesizeRequest(
        request_id=request_id,
        profile_id="yuki",
        model_relative_path="voices/yuki/model",
        engine_model_version=EngineModelVersion.V2_PRO_PLUS,
        language="zh",
        reference=ReferenceInput(
            reference_key="neutral",
            audio_relative_path="voices/yuki/references/neutral.wav",
            transcript="你好",
            language="zh",
        ),
        text="晚安",
        split_sentence=True,
        output_relative_path=f"cache/{request_id}.wav",
    )


def test_path_policy_rejects_escape_and_profile_crossing(speech_layout: tuple[Path, Path]) -> None:
    root, _ = speech_layout
    paths = SpeechPathPolicy(root)
    with pytest.raises(SpeechPathError):
        paths.resolve("../secret")
    with pytest.raises(SpeechPathError):
        paths.resolve(str((root / "cache").resolve()))
    with pytest.raises(SpeechPathError):
        paths.profile_reference("other", "voices/yuki/references/neutral.wav")
    with pytest.raises(SpeechPathError):
        paths.cache_output("voices/yuki/output.wav")


def test_protocol_is_big_endian_utf8_and_strict() -> None:
    request = HealthRequest(request_id="健康")
    framed = encode_payload(request)
    assert int.from_bytes(framed[:4], "big") == len(framed[4:])
    assert "健康".encode() in framed
    with pytest.raises(ValidationError):
        WORKER_REQUEST_ADAPTER.validate_python(
            {"protocol_version": 2, "request_id": "x", "operation": "health"}
        )
    with pytest.raises(ValidationError):
        WORKER_REQUEST_ADAPTER.validate_python(
            {
                "protocol_version": 1,
                "request_id": "x",
                "operation": "health",
                "unexpected": True,
            }
        )


def test_offline_environment_is_set_before_engine_initialization(
    speech_layout: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, data = speech_layout
    monkeypatch.delenv("GENIE_DATA_DIR", raising=False)
    configure_offline_environment(data)
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    engine = GenieEngine(paths=SpeechPathPolicy(root), genie_data_dir=data, module=FakeGenie())
    engine.initialize()


def test_missing_genie_data_fails_explicitly(tmp_path: Path) -> None:
    data = tmp_path / "missing"
    os.environ["GENIE_DATA_DIR"] = str(data)
    engine = GenieEngine(paths=SpeechPathPolicy(tmp_path), genie_data_dir=data, module=FakeGenie())
    with pytest.raises(Exception, match="GenieData is missing"):
        engine.initialize()


def test_engine_loads_reference_and_writes_valid_atomic_wave(
    speech_layout: tuple[Path, Path],
) -> None:
    root, data = speech_layout
    configure_offline_environment(data)
    fake = FakeGenie()
    engine = GenieEngine(paths=SpeechPathPolicy(root), genie_data_dir=data, module=fake)
    engine.initialize()
    result = engine.synthesize(_synthesis())
    assert result.sample_rate == SAMPLE_RATE
    assert result.channels == CHANNELS
    assert result.sample_width == SAMPLE_WIDTH
    assert result.duration_milliseconds > 0
    assert (root / result.relative_path).is_file()
    assert not tuple((root / "cache").glob("*.part.wav"))
    assert fake.reference_path.endswith("neutral.wav")
    assert fake.reference_language == "zh"


def test_engine_reloads_same_profile_when_target_language_changes(
    speech_layout: tuple[Path, Path],
) -> None:
    root, data = speech_layout
    configure_offline_environment(data)
    fake = FakeGenie()
    engine = GenieEngine(paths=SpeechPathPolicy(root), genie_data_dir=data, module=fake)
    engine.initialize()
    engine.synthesize(_synthesis("zh-request"))
    japanese = _synthesis("jp-request").model_copy(
        update={
            "language": "jp",
            "reference": _synthesis().reference.model_copy(update={"language": "jp"}),
            "text": "おやすみ",
        }
    )
    engine.synthesize(japanese)

    assert fake.loaded_languages == ["zh", "jp"]
    assert fake.reference_language == "jp"


async def _roundtrip(socket_path: Path, request: HealthRequest | SynthesizeRequest):
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        await write_frame(writer, request)
        return await read_response(reader)
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_worker_socket_permissions_health_and_serial_synthesis(
    speech_layout: tuple[Path, Path], tmp_path: Path
) -> None:
    root, data = speech_layout
    configure_offline_environment(data)
    fake = FakeGenie(delay=0.05)
    engine = GenieEngine(paths=SpeechPathPolicy(root), genie_data_dir=data, module=fake)
    socket_path = tmp_path / "runtime" / "genie.sock"
    server = GenieWorkerServer(socket_path=socket_path, engine=engine, socket_mode=0o660)
    await server.start()
    try:
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o660
        health = await _roundtrip(socket_path, HealthRequest(request_id="health"))
        assert health.ok
        first, second = await asyncio.gather(
            _roundtrip(socket_path, _synthesis("one")),
            _roundtrip(socket_path, _synthesis("two")),
        )
        assert first.ok and second.ok
        assert fake.max_active == 1
    finally:
        await server.request_shutdown()
        await server.serve_until_shutdown()


@pytest.mark.asyncio
async def test_worker_rejects_invalid_frame(
    speech_layout: tuple[Path, Path], tmp_path: Path
) -> None:
    root, data = speech_layout
    configure_offline_environment(data)
    engine = GenieEngine(paths=SpeechPathPolicy(root), genie_data_dir=data, module=FakeGenie())
    socket_path = tmp_path / "genie.sock"
    server = GenieWorkerServer(socket_path=socket_path, engine=engine, socket_mode=0o600)
    await server.start()
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write((2).to_bytes(4, "big") + b"[]")
        await writer.drain()
        response = await read_response(reader)
        assert isinstance(response, FailureResponse)
        assert response.error is WorkerErrorCode.INVALID_REQUEST
        writer.close()
        await writer.wait_closed()
    finally:
        await server.request_shutdown()
        await server.serve_until_shutdown()


@pytest.mark.asyncio
async def test_worker_recycles_after_synthesis_idle_timeout(
    speech_layout: tuple[Path, Path], tmp_path: Path
) -> None:
    root, data = speech_layout
    configure_offline_environment(data)
    fake = FakeGenie()
    engine = GenieEngine(paths=SpeechPathPolicy(root), genie_data_dir=data, module=fake)
    socket_path = tmp_path / "recycle.sock"
    server = GenieWorkerServer(
        socket_path=socket_path,
        engine=engine,
        socket_mode=0o600,
        idle_recycle_seconds=0.01,
    )
    await server.start()

    response = await _roundtrip(socket_path, _synthesis("idle-recycle"))
    assert response.ok
    await asyncio.wait_for(server.serve_until_shutdown(), timeout=1)

    assert fake.stopped
    assert fake.loaded is None
    assert not socket_path.exists()
