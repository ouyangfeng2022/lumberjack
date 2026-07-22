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


def _parse_cli_entry(entry: str, block_kinds: frozenset[str]) -> BlockOption:
    parts = [part.strip() for part in entry.split(":")]
    kind = parts[0].lower() if parts else ""
    if not kind:
        raise ValueError("block config kind cannot be empty")
    if kind not in block_kinds:
        valid = ", ".join(sorted(block_kinds))
        raise ValueError(f"Unknown block kind: {kind!r} (valid: {valid})")

    config: dict[str, object] = {}
    for token in parts[1:]:
        lowered = token.lower()
        if not token:
            continue
        if lowered == "isolated":
            config["isolated"] = True
        elif lowered == "nosplit":
            config["split"] = False
        else:
            try:
                config["max_tokens"] = int(token)
            except ValueError as exc:
                raise ValueError(f"Unknown block config token: {token!r}") from exc
    return block_config_from_mapping(kind, config)


def parse_cli_block_configs(
    entries: list[str],
    *,
    block_kinds: frozenset[str],
    json_config: str = "",
) -> list[BlockOption]:
    """Parse CLI config, with JSON entries overriding short-form entries."""
    indexed = {
        str(config.kind): config
        for config in (_parse_cli_entry(entry, block_kinds) for entry in entries)
    }
    json_options = parse_block_config_json(json_config)
    if json_options:
        indexed.update((str(config.kind), config) for config in json_options)
    return list(indexed.values())
