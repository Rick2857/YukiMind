"""Common contract for deferred user-visible reply effects."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReplyEffect(Protocol):
    """A path-free effect request prepared after the model turn.

    Emoji images and synthesized speech both implement this contract. Concrete
    services resolve their assets and create outbound OneBot messages.
    """

    @property
    def kind(self) -> str: ...

    @property
    def source(self) -> str: ...
