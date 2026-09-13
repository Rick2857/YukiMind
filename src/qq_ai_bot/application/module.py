"""Explicit application module builder contract."""

from __future__ import annotations

from typing import Protocol


class ApplicationModule[BundleT](Protocol):
    """Build one immutable bundle from constructor-injected dependencies."""

    def build(self) -> BundleT: ...
