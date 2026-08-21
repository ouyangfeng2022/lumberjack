"""CLI and Web adapters for public block configuration objects."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from lumberjack.block import (
    BlockConfig,
    BlockKind,
    BlockOption,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)

BASE_FIELDS = frozenset({"isolated", "split", "max_tokens"})
TABLE_FIELDS = frozenset({"repeat_header"})


def block_config_from_mapping(kind: str, config: Mapping[str, Any]) -> BlockOption:
    """Convert one external mapping into a typed public block config."""
    normalized = kind.strip().lower()
    is_table = normalized in {BlockKind.TABLE, BlockKind.HTML_TABLE}
    valid_fields = BASE_FIELDS | (TABLE_FIELDS if is_table else frozenset())
    unknown = set(config) - valid_fields
    if unknown:
        names = ", ".join(sorted(unknown))
        valid = ", ".join(sorted(valid_fields))
        raise ValueError(
            f"Unknown block config field(s) for {kind!r}: {names}. Valid fields: {valid}"
        )
    base = {name: config[name] for name in BASE_FIELDS if name in config}
    if normalized == BlockKind.TABLE:
        return MarkdownTableConfig(
            **base, repeat_header=config.get("repeat_header", True)
        )
    if normalized == BlockKind.HTML_TABLE:
        return HTMLTableConfig(**base, repeat_header=config.get("repeat_header", True))
    try:
        return BlockConfig(BlockKind(normalized), **base)
    except ValueError:
        return CustomBlockConfig(normalized, **base)


def parse_block_config_mapping(
    raw: Mapping[str, Any] | None,
) -> list[BlockOption] | None:
    if raw is None:
        return None
    result: list[BlockOption] = []
    for kind, config in raw.items():
        if not isinstance(config, Mapping):
            raise TypeError(f"block_configs[{kind!r}] must be an object")
        result.append(block_config_from_mapping(kind, config))
    return result


def parse_block_config_json(raw: str) -> list[BlockOption] | None:
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid block_configs JSON") from exc
    if not isinstance(parsed, Mapping):
        raise TypeError("block_configs must be a JSON object")
    return parse_block_config_mapping(parsed)
