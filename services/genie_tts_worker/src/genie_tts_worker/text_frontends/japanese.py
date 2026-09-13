"""Offline English-to-katakana frontend for Japanese speech synthesis."""

from __future__ import annotations

import hashlib
import importlib
import re
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from genie_tts_worker.text_frontends.base import (
    ProcessedSpeechText,
    SpeechTextFrontendUnavailable,
)

FRONTEND_VERSION = "japanese-e2k-v1"
_LATIN_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_LATIN_ANY = re.compile(r"[A-Za-z]")
_REQUIRED_ASSETS = ("model-c2k.npz", "ngram.json.zip")


class _C2K(Protocol):
    def __call__(self, word: str) -> str: ...


class _NGram(Protocol):
    def __call__(self, word: str) -> bool: ...

    def as_is(self, word: str) -> str: ...


class JapaneseSpeechFrontend:
    """Convert only ASCII Latin spans while preserving existing Japanese text."""

    def __init__(
        self,
        *,
        asset_dir: Path,
        lexicon_path: Path,
        c2k: _C2K | None = None,
        ngram: _NGram | None = None,
    ) -> None:
        self._asset_dir = asset_dir
        self._lexicon_path = lexicon_path
        self._validate_assets(required=c2k is None or ngram is None)
        self._lexicon = _load_lexicon(lexicon_path)
        if c2k is None or ngram is None:
            c2k, ngram = _load_e2k(asset_dir)
        self._c2k = c2k
        self._ngram = ngram
        self._signature = _signature(asset_dir, lexicon_path)

    @property
    def language(self) -> str:
        return "jp"

    @property
    def version(self) -> str:
        return FRONTEND_VERSION

    @property
    def signature(self) -> str:
        return self._signature

    def process(self, text: str) -> ProcessedSpeechText:
        transformed: list[str] = []

        def replace(match: re.Match[str]) -> str:
            original = match.group(0)
            transformed.append(original)
            configured = self._lexicon.get(original.casefold())
            if configured is not None:
                return configured
            return self._convert(original)

        spoken = _LATIN_TOKEN.sub(replace, text)
        if _LATIN_ANY.search(spoken):
            raise SpeechTextFrontendUnavailable(
                "Japanese frontend left an unsupported Latin character"
            )
        return ProcessedSpeechText(
            original_text_hash=_hash(text),
            spoken_text=spoken,
            spoken_text_hash=_hash(spoken),
            language=self.language,
            frontend_version=self.version,
            transformed_tokens=tuple(transformed),
        )

    def _convert(self, token: str) -> str:
        lowered = token.casefold()
        abbreviation = token.isupper()
        if abbreviation or not self._ngram(lowered):
            converted = self._ngram.as_is(lowered)
        else:
            converted = self._c2k(lowered)
        if converted and not _LATIN_ANY.search(converted):
            return converted
        return _spell_letters(lowered)

    def _validate_assets(self, *, required: bool) -> None:
        if not self._lexicon_path.is_file():
            raise SpeechTextFrontendUnavailable("Japanese frontend lexicon is missing")
        if required:
            missing = [name for name in _REQUIRED_ASSETS if not (self._asset_dir / name).is_file()]
            if missing:
                raise SpeechTextFrontendUnavailable(
                    "Japanese frontend assets are missing: " + ", ".join(missing)
                )


def _load_e2k(asset_dir: Path) -> tuple[_C2K, _NGram]:
    """Load e2k with its resource resolver bound to the deployment asset directory."""

    try:
        inference = importlib.import_module("e2k.inference")
    except ImportError as exc:
        raise SpeechTextFrontendUnavailable("e2k is not installed") from exc
    resolver = cast(Callable[[str], str], lambda filename: str(asset_dir / filename))
    cast(Any, inference).get_asset_path = resolver
    try:
        c2k = cast(_C2K, cast(Any, inference).C2K())
        ngram = cast(_NGram, cast(Any, inference).NGramCollection())
    except (OSError, ValueError, KeyError) as exc:
        raise SpeechTextFrontendUnavailable("e2k assets are invalid") from exc
    return c2k, ngram


def _load_lexicon(path: Path) -> dict[str, str]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SpeechTextFrontendUnavailable("Japanese frontend lexicon is invalid") from exc
    words = payload.get("words")
    if not isinstance(words, dict):
        raise SpeechTextFrontendUnavailable("Japanese frontend lexicon needs a [words] table")
    result: dict[str, str] = {}
    for word, reading in words.items():
        if not isinstance(word, str) or not isinstance(reading, str) or _LATIN_ANY.search(reading):
            raise SpeechTextFrontendUnavailable("Japanese frontend lexicon entry is invalid")
        result[word.casefold()] = reading
    return result


def _signature(asset_dir: Path, lexicon_path: Path) -> str:
    digest = hashlib.sha256(FRONTEND_VERSION.encode("ascii"))
    for path in sorted(asset_dir.glob("*"), key=lambda item: item.name):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(_file_hash(path).encode("ascii"))
    digest.update(_file_hash(lexicon_path).encode("ascii"))
    return digest.hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_LETTER_READINGS = {
    "a": "エー",
    "b": "ビー",
    "c": "シー",
    "d": "ディー",
    "e": "イー",
    "f": "エフ",
    "g": "ジー",
    "h": "エイチ",
    "i": "アイ",
    "j": "ジェー",
    "k": "ケー",
    "l": "エル",
    "m": "エム",
    "n": "エヌ",
    "o": "オー",
    "p": "ピー",
    "q": "キュー",
    "r": "アール",
    "s": "エス",
    "t": "ティー",
    "u": "ユー",
    "v": "ヴィー",
    "w": "ダブリュー",
    "x": "エックス",
    "y": "ワイ",
    "z": "ゼット",
}


def _spell_letters(word: str) -> str:
    return "".join(_LETTER_READINGS[letter] for letter in word if letter in _LETTER_READINGS)
