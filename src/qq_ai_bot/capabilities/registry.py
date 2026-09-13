"""Small per-conversation descriptor registry."""

from __future__ import annotations

from qq_ai_bot.capabilities.models import CapabilityDescriptor


class CapabilityRegistry:
    def __init__(self, descriptors: tuple[CapabilityDescriptor, ...] = ()) -> None:
        self._descriptors: dict[str, CapabilityDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> None:
        if descriptor.model_name in self._descriptors:
            raise ValueError(f"duplicate model capability: {descriptor.model_name}")
        self._descriptors[descriptor.model_name] = descriptor

    def get(self, model_name: str) -> CapabilityDescriptor | None:
        return self._descriptors.get(model_name)

    def all(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._descriptors.values())
