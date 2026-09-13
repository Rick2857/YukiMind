"""Single path-containment policy for every Worker filesystem operation."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SpeechPathError(ValueError):
    """A requested path is not an allowed speech-root relative path."""


class SpeechPathPolicy:
    def __init__(self, speech_root: Path) -> None:
        self.root = speech_root.resolve()

    def resolve(self, relative_path: str, *, must_exist: bool = False) -> Path:
        pure = PurePosixPath(relative_path.replace("\\", "/"))
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise SpeechPathError("path must be a normalized relative path")
        candidate = self.root.joinpath(*pure.parts).resolve()
        if not candidate.is_relative_to(self.root):
            raise SpeechPathError("path escapes speech root")
        if must_exist and not candidate.exists():
            raise SpeechPathError("required speech path does not exist")
        return candidate

    def profile_model(self, profile_id: str, relative_path: str) -> Path:
        self._validate_profile_id(profile_id)
        path = self.resolve(relative_path, must_exist=True)
        profile_root = self.resolve(f"voices/{profile_id}", must_exist=True)
        if not path.is_dir() or not path.is_relative_to(profile_root):
            raise SpeechPathError("model directory must remain inside its profile")
        return path

    def profile_reference(self, profile_id: str, relative_path: str) -> Path:
        self._validate_profile_id(profile_id)
        path = self.resolve(relative_path, must_exist=True)
        references_root = self.resolve(f"voices/{profile_id}/references", must_exist=True)
        if not path.is_file() or not path.is_relative_to(references_root):
            raise SpeechPathError("reference audio must remain inside its profile")
        return path

    def cache_output(self, relative_path: str) -> Path:
        path = self.resolve(relative_path)
        cache_root = self.resolve("cache")
        if not path.is_relative_to(cache_root) or path.suffix.casefold() != ".wav":
            raise SpeechPathError("output must be a WAV below the speech cache")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _validate_profile_id(profile_id: str) -> None:
        if _PROFILE_ID.fullmatch(profile_id) is None:
            raise SpeechPathError("invalid profile id")
