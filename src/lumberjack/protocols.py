from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .models import Bundle, Log, Tree


class ScalerProtocol(Protocol):
    """Measure text units used by sawyers and mills."""

    def encode(self, text: str, *, cache=False) -> tuple[int, ...]: ...

    def scale(self, text: str, *, cache=False) -> int: ...


class FellerProtocol(Protocol):
    """Fell a raw tree into the shared structured log."""

    block_kinds: frozenset[str]

    def fell(self, tree: Tree) -> Log: ...


class SawyerProtocol(Protocol):
    """Saw a structured log into unfinished bundles."""

    @property
    def scaler(self) -> ScalerProtocol: ...

    def saw(self, log: Log) -> list[Bundle]: ...


class SeasonerProtocol(Protocol):
    """Stabilize rendered bundle text before planing."""

    def season(self, text: str) -> str: ...


class PlanerProtocol(Protocol):
    """Normalize or simplify seasoned text before final chunk creation."""

    def plane(self, text: str) -> str: ...
