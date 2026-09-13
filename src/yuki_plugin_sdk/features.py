"""Feature discovery independent of Yuki release-number guesses."""

from __future__ import annotations

from collections.abc import Iterable

from yuki_plugin_sdk.errors import FeatureUnavailableError


class FeatureRegistry:
    def __init__(self, features: Iterable[str] = ()) -> None:
        self._features = frozenset(features)

    def has(self, feature: str) -> bool:
        return feature in self._features

    def require(self, feature: str) -> None:
        if not self.has(feature):
            raise FeatureUnavailableError(f"required feature is unavailable: {feature}")

    def list(self) -> tuple[str, ...]:
        return tuple(sorted(self._features))
