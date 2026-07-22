"""Public block kinds and per-block splitting configuration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:

    class StrEnum(str, Enum):
        """Static model of :class:`enum.StrEnum` for the Python 3.10 target."""

        def __str__(self) -> str:
            return self.value
else:
    try:
        from enum import StrEnum
    except ImportError:  # pragma: no cover - Python 3.10 compatibility

        class StrEnum(str, Enum):
            def __str__(self) -> str:
                return self.value


class BlockKind(StrEnum):
    """Built-in block kinds emitted by lumberjack parsers."""

    PARAGRAPH = "paragraph"
    BLOCKQUOTE = "blockquote"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    HTML_TABLE = "html_table"
    CODE_BLOCK = "code_block"
    CODE_FENCE = "code_fence"
    HTML_BLOCK = "html_block"
    FRONT_MATTER = "front_matter"
    MATH_BLOCK = "math_block"
    MATH_BLOCK_EQNO = "math_block_eqno"


@dataclass(slots=True, frozen=True)
class BlockConfig:
    """Splitting behavior for one built-in block kind."""

    kind: BlockKind
    isolated: bool = False
    split: bool = True
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BlockKind):
            raise TypeError("BlockConfig.kind must be a BlockKind")
        if self.kind in {BlockKind.TABLE, BlockKind.HTML_TABLE}:
            raise ValueError(
                "table kinds require MarkdownTableConfig or HTMLTableConfig"
            )
        _validate_common_config(self)


@dataclass(slots=True, frozen=True)
class MarkdownTableConfig:
    """Splitting behavior for Markdown pipe tables."""

    isolated: bool = False
    split: bool = True
    max_tokens: int | None = None
    repeat_header: bool = True

    def __post_init__(self) -> None:
        _validate_common_config(self)
        if not isinstance(self.repeat_header, bool):
            raise TypeError("repeat_header must be a boolean")

    @property
    def kind(self) -> BlockKind:
        return BlockKind.TABLE


@dataclass(slots=True, frozen=True)
class HTMLTableConfig:
    """Splitting behavior for HTML tables."""

    isolated: bool = False
    split: bool = True
    max_tokens: int | None = None
    repeat_header: bool = True

    def __post_init__(self) -> None:
        _validate_common_config(self)
        if not isinstance(self.repeat_header, bool):
            raise TypeError("repeat_header must be a boolean")

    @property
    def kind(self) -> BlockKind:
        return BlockKind.HTML_TABLE


@dataclass(slots=True, frozen=True)
class CustomBlockConfig:
    """Splitting behavior for a parser plugin's custom block kind."""

    kind: str
    isolated: bool = False
    split: bool = True
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str):
            raise TypeError("custom block kind must be a string")
        normalized = self.kind.strip().lower()
        if not normalized:
            raise ValueError("custom block kind cannot be empty")
        if normalized in BlockKind._value2member_map_:
            raise ValueError(
                f"{self.kind!r} is a built-in block kind; use BlockConfig instead"
            )
        object.__setattr__(self, "kind", normalized)
        _validate_common_config(self)


BlockOption: TypeAlias = (
    BlockConfig | MarkdownTableConfig | HTMLTableConfig | CustomBlockConfig
)


def _validate_common_config(config: BlockOption) -> None:
    if not isinstance(config.isolated, bool):
        raise TypeError("isolated must be a boolean")
    if not isinstance(config.split, bool):
        raise TypeError("split must be a boolean")
    if config.max_tokens is not None and (
        not isinstance(config.max_tokens, int)
        or isinstance(config.max_tokens, bool)
        or config.max_tokens <= 0
    ):
        raise ValueError("max_tokens must be positive integer or None")


def normalize_block_options(
    options: Iterable[BlockOption] | None,
) -> dict[str, BlockOption]:
    """Validate block configs and index them by normalized kind."""
    if options is None:
        return {}
    if isinstance(options, dict):
        raise TypeError("block_options must be a sequence of block config objects")

    normalized: dict[str, BlockOption] = {}
    for config in options:
        if not isinstance(
            config,
            BlockConfig | MarkdownTableConfig | HTMLTableConfig | CustomBlockConfig,
        ):
            raise TypeError(
                "block_options entries must be BlockConfig, MarkdownTableConfig, "
                "HTMLTableConfig, or CustomBlockConfig"
            )
        kind = str(config.kind)
        if kind in normalized:
            raise ValueError(f"duplicate block config for kind: {kind!r}")
        if config.max_tokens is not None and config.max_tokens <= 0:
            raise ValueError(
                f"block_options[{kind!r}].max_tokens must be positive, "
                f"got {config.max_tokens}"
            )
        normalized[kind] = config
    return normalized


def default_block_config(kind: str | BlockKind) -> BlockOption:
    """Return the default config for a built-in or custom block kind."""
    normalized = str(kind).strip().lower()
    if normalized == BlockKind.TABLE:
        return MarkdownTableConfig()
    if normalized == BlockKind.HTML_TABLE:
        return HTMLTableConfig()
    try:
        return BlockConfig(BlockKind(normalized))
    except ValueError:
        return CustomBlockConfig(normalized)


__all__ = [
    "BlockConfig",
    "BlockKind",
    "CustomBlockConfig",
    "HTMLTableConfig",
    "MarkdownTableConfig",
]
