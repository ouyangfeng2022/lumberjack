"""Shared block-kind parsing and validation helpers for CLI and web routes."""

from __future__ import annotations

from .models import BlockConfig, BlockKindRegistry


def parse_block_config_entry(
    entry: str, registry: BlockKindRegistry
) -> tuple[str, BlockConfig]:
    """Parse a ``KIND[:isolated][:nosplit][:TOKENS]`` string into ``(kind, BlockConfig)``.

    The colon-separated parts after the kind name are classified by content:

    - ``isolated`` → ``isolated=True``
    - ``nosplit`` → ``split=False``
    - positive integer → ``max_tokens``

    Raises :class:`ValueError` on unknown kind or bad tokens.
    """
    parts = entry.split(":")
    kind = parts[0].strip().lower()
    if not kind:
        raise ValueError(f"Empty block kind in: {entry!r}")
    registry.validate_kind(kind)

    isolated = False
    split = True
    max_tokens: int | None = None

    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        lower = part.lower()
        if lower == "isolated":
            isolated = True
        elif lower == "nosplit":
            split = False
        else:
            try:
                tokens = int(part)
            except ValueError:
                raise ValueError(
                    f"Invalid spec in: {entry!r} "
                    f"(expected 'isolated', 'nosplit', or integer, got {part!r})"
                ) from None
            if tokens <= 0:
                raise ValueError(f"Token count must be positive in: {entry!r}")
            max_tokens = tokens

    return kind, BlockConfig(isolated=isolated, split=split, max_tokens=max_tokens)
