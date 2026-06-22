from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .block import parse_block_config_entry
from .models import BlockConfig, BlockKindRegistry
from .parsers.markdown.parser import MarkdownItParser

BLOCK_CONFIG_FIELDS = frozenset({"isolated", "split", "max_tokens"})


def resolve_block_options(
    block_kinds: frozenset[str],
    overrides: Mapping[str, BlockConfig | Mapping[str, Any]] | None = None,
) -> dict[str, BlockConfig]:
    """Merge parser block kinds with caller-supplied block handling overrides."""
    resolved = dict.fromkeys(sorted(block_kinds), BlockConfig())
    if not overrides:
        return resolved

    for kind, value in overrides.items():
        normalized = kind.strip().lower()
        if isinstance(value, BlockConfig):
            resolved[normalized] = value
        elif isinstance(value, Mapping):
            resolved[normalized] = block_config_from_mapping(normalized, value)
        else:
            msg = (
                f"block_options[{kind!r}] must be BlockConfig or dict, "
                f"got {type(value).__name__}"
            )
            raise TypeError(msg)
    return resolved


def block_config_from_mapping(kind: str, config: Mapping[str, Any]) -> BlockConfig:
    """Parse and validate one mapping-style block config."""
    unknown = set(config) - BLOCK_CONFIG_FIELDS
    if unknown:
        fields = ", ".join(sorted(BLOCK_CONFIG_FIELDS))
        unknown_fields = ", ".join(sorted(unknown))
        raise ValueError(
            f"Unknown block config field(s) for {kind!r}: {unknown_fields}. "
            f"Valid fields: {fields}"
        )
    return BlockConfig(**dict(config))


def parse_block_config_mapping(
    raw: Mapping[str, Any] | None,
) -> dict[str, BlockConfig] | None:
    """Parse API-style block config objects without applying parser defaults."""
    if raw is None:
        return None

    resolved: dict[str, BlockConfig] = {}
    for kind, config in raw.items():
        if not isinstance(config, Mapping):
            raise TypeError(f"block_configs[{kind!r}] must be an object")
        resolved[kind] = block_config_from_mapping(kind, config)
    return resolved


def parse_block_config_json(raw: str) -> dict[str, BlockConfig] | None:
    """Parse a JSON object containing API-style block configs."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid block_configs JSON") from exc
    if not isinstance(parsed, Mapping):
        raise TypeError("block_configs must be a JSON object")
    return parse_block_config_mapping(parsed)


def parse_cli_block_configs(entries: list[str]) -> dict[str, BlockConfig]:
    """Parse CLI ``--block-config`` entries against the default Markdown registry."""
    registry: BlockKindRegistry = MarkdownItParser.default_registry()
    result: dict[str, BlockConfig] = dict(registry.default_handling())
    for entry in entries:
        kind, cfg = parse_block_config_entry(entry, registry)
        result[kind] = cfg
    return result
