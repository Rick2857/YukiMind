"""Path containment and atomic filesystem helpers for local speech data."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path, PurePosixPath

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SpeechPathError(ValueError):
    pass


class SpeechPathPolicy:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def ensure_layout(self) -> None:
        for relative in ("genie_data", "voices", "cache", "runtime", "imports"):
            self.resolve(relative).mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str, *, must_exist: bool = False) -> Path:
        pure = PurePosixPath(relative_path.replace("\\", "/"))
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise SpeechPathError("speech path must be normalized and relative")
        target = self.root.joinpath(*pure.parts).resolve()
        if not target.is_relative_to(self.root):
            raise SpeechPathError("speech path escapes configured root")
        if must_exist and not target.exists():
            raise SpeechPathError("required speech path does not exist")
        return target

    def profile_root(self, profile_id: str, *, must_exist: bool = False) -> Path:
        if _PROFILE_ID.fullmatch(profile_id) is None:
            raise SpeechPathError("invalid profile id")
        return self.resolve(f"voices/{profile_id}", must_exist=must_exist)

    def inside_profile(
        self, profile_id: str, profile_relative_path: str, *, must_exist: bool = False
    ) -> Path:
        profile = self.profile_root(profile_id, must_exist=True)
        pure = PurePosixPath(profile_relative_path.replace("\\", "/"))
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise SpeechPathError("profile path must be normalized and relative")
        target = profile.joinpath(*pure.parts).resolve()
        if not target.is_relative_to(profile):
            raise SpeechPathError("profile path escapes its directory")
        if must_exist and not target.exists():
            raise SpeechPathError("required profile path does not exist")
        return target

    def relative(self, path: Path) -> str:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise SpeechPathError("cannot persist a path outside speech root")
        return resolved.relative_to(self.root).as_posix()

    def stage_import(self, source: Path, profile_id: str) -> tuple[Path, Path]:
        if not source.is_dir():
            raise SpeechPathError("profile import source must be a directory")
        staging = self.resolve(f"imports/{profile_id}.importing")
        destination = self.profile_root(profile_id)
        if staging.exists():
            shutil.rmtree(staging)
        if destination.exists():
            raise FileExistsError("voice profile already exists")
        shutil.copytree(source, staging)
        return staging, destination

    @staticmethod
    def commit_import(staging: Path, destination: Path) -> None:
        os.replace(staging, destination)
