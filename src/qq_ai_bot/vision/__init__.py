"""Provider-neutral visual analysis package."""

from qq_ai_bot.vision.base import VisionConfigurationError, VisionError, VisionProvider
from qq_ai_bot.vision.fake import FakeVisionProvider
from qq_ai_bot.vision.models import (
    DownloadedMedia,
    MediaReference,
    MediaSource,
    PreparedFrame,
    PreparedVisualInput,
    VisionAnalysisMode,
    VisionAnalysisOptions,
    VisualCharacterCandidate,
    VisualItemObservation,
    VisualObservation,
)
from qq_ai_bot.vision.qwen import QwenVisionProvider

__all__ = [
    "DownloadedMedia",
    "FakeVisionProvider",
    "MediaReference",
    "MediaSource",
    "PreparedFrame",
    "PreparedVisualInput",
    "QwenVisionProvider",
    "VisionAnalysisMode",
    "VisionAnalysisOptions",
    "VisionConfigurationError",
    "VisionError",
    "VisionProvider",
    "VisualCharacterCandidate",
    "VisualItemObservation",
    "VisualObservation",
]
