from __future__ import annotations

import re
from pathlib import Path

import pytest

from genie_tts_worker.text_frontends import (
    SpeechFrontendRegistry,
    SpeechTextFrontendUnavailable,
)
from genie_tts_worker.text_frontends.japanese import JapaneseSpeechFrontend


class FakeC2K:
    def __call__(self, word: str) -> str:
        return {"hello": "ハロー", "world": "ワールド"}.get(word, "")


class FakeNGram:
    def __call__(self, word: str) -> bool:
        return word in {"hello", "world"}

    def as_is(self, word: str) -> str:
        return {"gpt": "ジーピーティー"}.get(word, "")


@pytest.fixture
def frontend(tmp_path: Path) -> JapaneseSpeechFrontend:
    lexicon = tmp_path / "lexicon.toml"
    lexicon.write_text(
        '[words]\nYuki = "ユキ"\nOpenAI = "オープンエーアイ"\n'
        'ChatGPT = "チャットジーピーティー"\nAPI = "エーピーアイ"\n',
        encoding="utf-8",
    )
    return JapaneseSpeechFrontend(
        asset_dir=tmp_path,
        lexicon_path=lexicon,
        c2k=FakeC2K(),
        ngram=FakeNGram(),
    )


def test_lexicon_and_existing_japanese_are_preserved(
    frontend: JapaneseSpeechFrontend,
) -> None:
    result = frontend.process("OpenAIを使います Yuki")
    assert result.spoken_text == "オープンエーアイを使います ユキ"
    assert result.transformed_tokens == ("OpenAI", "Yuki")
    assert result.spoken_text_hash != result.original_text_hash


def test_abbreviation_regular_word_and_unknown_have_no_latin(
    frontend: JapaneseSpeechFrontend,
) -> None:
    result = frontend.process("GPT hello XYZ")
    assert result.spoken_text.startswith("ジーピーティー ハロー ")
    assert not re.search(r"[A-Za-z]", result.spoken_text)


def test_mixed_lexicon_tokens_have_no_latin(frontend: JapaneseSpeechFrontend) -> None:
    result = frontend.process("ChatGPTとAPI")
    assert not re.search(r"[A-Za-z]", result.spoken_text)


def test_registry_leaves_non_japanese_languages_unchanged(
    frontend: JapaneseSpeechFrontend,
) -> None:
    registry = SpeechFrontendRegistry((frontend,))
    assert registry.process("zh", "OpenAI") is None
    assert registry.process("en", "OpenAI") is None


def test_missing_assets_report_unavailable(tmp_path: Path) -> None:
    lexicon = tmp_path / "lexicon.toml"
    lexicon.write_text("[words]\n", encoding="utf-8")
    registry = SpeechFrontendRegistry.build_japanese(
        enabled=True,
        asset_dir=tmp_path / "models",
        lexicon_path=lexicon,
    )
    health = registry.health("jp")
    assert health is not None and not health.available
    with pytest.raises(SpeechTextFrontendUnavailable):
        registry.process("jp", "Hello")


def test_signature_changes_with_lexicon(tmp_path: Path) -> None:
    lexicon = tmp_path / "lexicon.toml"
    lexicon.write_text('[words]\nYuki = "ユキ"\n', encoding="utf-8")
    first = JapaneseSpeechFrontend(
        asset_dir=tmp_path,
        lexicon_path=lexicon,
        c2k=FakeC2K(),
        ngram=FakeNGram(),
    )
    lexicon.write_text('[words]\nYuki = "ユキー"\n', encoding="utf-8")
    second = JapaneseSpeechFrontend(
        asset_dir=tmp_path,
        lexicon_path=lexicon,
        c2k=FakeC2K(),
        ngram=FakeNGram(),
    )
    assert first.signature != second.signature
