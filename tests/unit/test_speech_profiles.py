from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from qq_ai_bot.persistence.database import Database
from qq_ai_bot.speech.cache import speech_cache_key
from qq_ai_bot.speech.language import prepare_text_for_language, resolve_target_language
from qq_ai_bot.speech.models import VoiceProfile, VoiceProfileManifest
from qq_ai_bot.speech.paths import SpeechPathError, SpeechPathPolicy
from qq_ai_bot.speech.profiles import VoiceProfileService
from qq_ai_bot.speech.repository import VoiceProfileRepository
from qq_ai_bot.speech.style_resolver import StyleResolver
from qq_ai_bot.speech.text_normalizer import normalize_speech_text


def _profile_toml(*, extra: str = "", default_style: str = "neutral") -> str:
    return f'''id = "yuki"
display_name = "Yuki"
provider = "genie"
engine_model_version = "v2proplus"
language = "zh"
supported_languages = ["zh", "jp"]
default_style = "{default_style}"
enabled = true
source = "user_supplied"
source_note = "local"
license_note = "deployment owner"
{extra}
[model]
path = "model"

[[references]]
id = "neutral"
style = "neutral"
aliases = ["日常", "平静"]
audio = "references/neutral.wav"
text = "你好。"
language = "zh"
enabled = true
priority = 1

[[references]]
id = "shy"
style = "shy"
aliases = ["害羞", "轻声"]
audio = "references/shy.wav"
text = "才不是呢。"
language = "zh"
enabled = true
priority = 5
'''


def _make_profile(root: Path, *, content: str | None = None) -> Path:
    profile = root / "source"
    (profile / "model").mkdir(parents=True)
    (profile / "references").mkdir()
    (profile / "model" / "voice.onnx").write_bytes(b"onnx-model")
    (profile / "references" / "neutral.wav").write_bytes(b"neutral")
    (profile / "references" / "shy.wav").write_bytes(b"shy")
    (profile / "profile.toml").write_text(content or _profile_toml(), encoding="utf-8")
    return profile


def test_profile_manifest_parses_and_rejects_unknown_fields(tmp_path: Path) -> None:
    source = _make_profile(tmp_path)
    service = VoiceProfileService(
        repository=VoiceProfileRepository.__new__(VoiceProfileRepository),
        paths=SpeechPathPolicy(tmp_path / "speech"),
    )
    manifest = service.validate_profile(source)
    assert isinstance(manifest, VoiceProfileManifest)
    assert tuple(item.style for item in manifest.references) == ("neutral", "shy")
    assert manifest.supported_languages == ("zh", "jp")

    invalid = _make_profile(tmp_path / "other", content=_profile_toml(extra="unknown = true"))
    with pytest.raises(ValueError, match="invalid voice profile manifest"):
        service.validate_profile(invalid)


def test_manifest_paths_and_default_style_are_strict(tmp_path: Path) -> None:
    service = VoiceProfileService(
        repository=VoiceProfileRepository.__new__(VoiceProfileRepository),
        paths=SpeechPathPolicy(tmp_path / "speech"),
    )
    escaped = _make_profile(
        tmp_path / "escape",
        content=_profile_toml().replace('path = "model"', 'path = "../model"'),
    )
    with pytest.raises(SpeechPathError):
        service.validate_profile(escaped)

    missing_default = _make_profile(
        tmp_path / "missing-default",
        content=_profile_toml(default_style="playful"),
    )
    with pytest.raises(ValueError, match="invalid voice profile manifest"):
        service.validate_profile(missing_default)


async def test_profile_import_is_atomic_persistent_and_style_resolution_is_deterministic(
    database: Database, tmp_path: Path
) -> None:
    speech_root = tmp_path / "speech"
    source = _make_profile(tmp_path / "input")
    repository = VoiceProfileRepository(database)
    service = VoiceProfileService(
        repository=repository,
        paths=SpeechPathPolicy(speech_root),
    )

    imported = await service.import_profile(source)
    assert imported.profile_id == "yuki"
    assert imported.model_relative_path == "voices/yuki/model"
    assert len(imported.references) == 2
    assert all(not Path(item.audio_relative_path).is_absolute() for item in imported.references)
    assert (speech_root / "voices" / "yuki" / "profile.toml").is_file()
    assert not tuple((speech_root / "imports").iterdir())

    resolver = StyleResolver()
    assert resolver.resolve(imported, "shy").reference_key == "shy"
    assert resolver.resolve(imported, "害羞").reference_key == "shy"
    assert resolver.resolve(imported, "轻 声").reference_key == "shy"
    assert resolver.resolve(imported, "unknown").reference_key == "neutral"

    activated = await service.activate_profile("yuki")
    assert activated.is_default
    assert (await repository.get_default()).profile_id == "yuki"  # type: ignore[union-attr]


async def test_profile_model_and_reference_checksums_change_independently(
    database: Database, tmp_path: Path
) -> None:
    speech_root = tmp_path / "speech"
    source = _make_profile(tmp_path / "input")
    service = VoiceProfileService(
        repository=VoiceProfileRepository(database),
        paths=SpeechPathPolicy(speech_root),
    )
    profile = await service.import_profile(source)
    assert (
        profile.model_checksum
        == hashlib.sha256(
            b"voice.onnx" + hashlib.sha256(b"onnx-model").hexdigest().encode()
        ).hexdigest()
    )
    assert profile.references[0].audio_checksum != profile.references[1].audio_checksum


async def test_profile_metadata_sync_does_not_warm_synthesis_model(
    database: Database, tmp_path: Path
) -> None:
    class Loader:
        def __init__(self) -> None:
            self.loaded: list[tuple[str, bool]] = []

        async def load_profile(self, profile: VoiceProfile, *, reload: bool = False) -> None:
            self.loaded.append((profile.profile_id, reload))

        async def unload_profile(self, profile_id: str) -> None:
            pass

    speech_root = tmp_path / "speech"
    repository = VoiceProfileRepository(database)
    bootstrap = VoiceProfileService(
        repository=repository,
        paths=SpeechPathPolicy(speech_root),
    )
    await bootstrap.import_profile(_make_profile(tmp_path / "input"))
    loader = Loader()
    service = VoiceProfileService(
        repository=repository,
        paths=SpeechPathPolicy(speech_root),
        loader=loader,
    )

    profile = await service.sync_profile_metadata("yuki")

    assert profile.profile_id == "yuki"
    assert loader.loaded == []


def test_speech_path_policy_never_persists_absolute_paths(tmp_path: Path) -> None:
    policy = SpeechPathPolicy(tmp_path / "speech")
    policy.ensure_layout()
    with pytest.raises(SpeechPathError):
        policy.resolve("../outside")
    with pytest.raises(SpeechPathError):
        policy.relative(tmp_path / "outside")


async def test_reference_sidecar_import_rewrites_manifest_atomically(
    database: Database, tmp_path: Path
) -> None:
    speech_root = tmp_path / "speech"
    service = VoiceProfileService(
        repository=VoiceProfileRepository(database),
        paths=SpeechPathPolicy(speech_root),
    )
    await service.import_profile(_make_profile(tmp_path / "input"))
    source = tmp_path / "happy.wav"
    source.write_bytes(b"happy-reference")
    source.with_suffix(".toml").write_text(
        """id = "happy"
style = "happy"
aliases = ["开心"]
text = "今天真开心。"
language = "zh"
enabled = true
priority = 3
""",
        encoding="utf-8",
    )

    added = await service.add_reference("yuki", source)

    assert added.reference_key == "happy"
    assert added.audio_relative_path == "voices/yuki/references/happy.wav"
    profile = await service.get_profile("yuki")
    assert profile is not None
    assert StyleResolver().resolve(profile, "开心").reference_key == "happy"


async def test_cache_key_uses_model_reference_and_normalized_text(
    database: Database, tmp_path: Path
) -> None:
    service = VoiceProfileService(
        repository=VoiceProfileRepository(database),
        paths=SpeechPathPolicy(tmp_path / "speech"),
    )
    profile = await service.import_profile(_make_profile(tmp_path / "input"))
    reference = profile.references[0]
    key = speech_cache_key(
        profile=profile,
        reference=reference,
        normalized_text="晚安",
        split_sentence=True,
        target_language="zh",
    )
    assert key != speech_cache_key(
        profile=profile,
        reference=reference.model_copy(update={"audio_checksum": "f" * 64}),
        normalized_text="晚安",
        split_sentence=True,
        target_language="zh",
    )
    assert key != speech_cache_key(
        profile=profile,
        reference=reference,
        normalized_text="早安",
        split_sentence=True,
        target_language="zh",
    )
    assert key != speech_cache_key(
        profile=profile,
        reference=reference,
        normalized_text="晚安",
        split_sentence=True,
        target_language="jp",
    )


async def test_target_language_uses_actual_script_before_planner_hint(
    database: Database, tmp_path: Path
) -> None:
    service = VoiceProfileService(
        repository=VoiceProfileRepository(database),
        paths=SpeechPathPolicy(tmp_path / "speech"),
    )
    profile = await service.import_profile(_make_profile(tmp_path / "input"))

    assert resolve_target_language(profile, "晚安，明天见。", "jp") == "zh"
    assert resolve_target_language(profile, "おやすみ、また明日。", "zh") == "jp"
    assert resolve_target_language(profile, "……", "jp") == "jp"


def test_chinese_g2p_compatibility_preserves_intent_without_touching_japanese() -> None:
    assert prepare_text_for_language("嗯…啊…", "zh") == "恩…啊…"
    assert prepare_text_for_language("んっ…はぁ…", "jp") == "んっ…はぁ…"


def test_speech_text_normalizer_omits_code_and_full_urls() -> None:
    normalized = normalize_speech_text(
        "**你好** [说明](https://example.com/doc)\n```python\nprint('secret')\n```\n"
        "详情 https://example.com/very/long/path"
    )
    assert "print" not in normalized
    assert "https://" not in normalized
    assert "你好" in normalized
    assert "说明" in normalized
    assert "链接" in normalized
