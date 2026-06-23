from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .block import parse_block_config_entry
from .models import BaseParams, BlockKindRegistry, TableBlockParams
from .parsers.markdown.parser import MarkdownItParser

BASE_PARAM_FIELDS = frozenset({"isolated", "split", "max_tokens"})
TABLE_PARAM_FIELDS = frozenset({"repeat_header"})
TABLE_PARAM_KINDS = frozenset({"table", "html_table"})


def resolve_block_options(
    block_kinds: frozenset[str],
    overrides: Mapping[str, BaseParams | Mapping[str, Any]] | None = None,
) -> dict[str, BaseParams]:
    """Merge parser block kinds with caller-supplied block handling overrides."""
    registry = BlockKindRegistry(block_kinds)
    resolved = registry.default_handling()
    if not overrides:
        return resolved

    for kind, value in overrides.items():
        normalized = kind.strip().lower()
        if isinstance(value, BaseParams):
            resolved[normalized] = value
        elif isinstance(value, Mapping):
            resolved[normalized] = block_params_from_mapping(normalized, value)
        else:
            msg = (
                f"block_options[{kind!r}] must be BaseParams or dict, "
                f"got {type(value).__name__}"
            )
            raise TypeError(msg)
    return resolved


def block_params_from_mapping(kind: str, config: Mapping[str, Any]) -> BaseParams:
    """Parse and validate one mapping-style block params object."""
    fields = BASE_PARAM_FIELDS | (
        TABLE_PARAM_FIELDS if kind.strip().lower() in TABLE_PARAM_KINDS else frozenset()
    )
    unknown = set(config) - fields
    if unknown:
        valid_fields = ", ".join(sorted(fields))
        unknown_fields = ", ".join(sorted(unknown))
        raise ValueError(
            f"Unknown block params field(s) for {kind!r}: {unknown_fields}. "
            f"Valid fields: {valid_fields}"
        )

    normalized = kind.strip().lower()
    base = {key: config[key] for key in BASE_PARAM_FIELDS if key in config}
    if normalized in TABLE_PARAM_KINDS:
        repeat_header = config.get("repeat_header", True)
        if not isinstance(repeat_header, bool):
            raise TypeError(f"block_configs[{kind!r}].repeat_header must be a boolean")
        return TableBlockParams(**base, repeat_header=repeat_header)
    return BaseParams(**base)


def parse_block_config_mapping(
    raw: Mapping[str, Any] | None,
) -> dict[str, BaseParams] | None:
    """Parse API-style block params objects without applying parser defaults."""
    if raw is None:
        return None

    resolved: dict[str, BaseParams] = {}
    for kind, config in raw.items():
        if not isinstance(config, Mapping):
            raise TypeError(f"block_configs[{kind!r}] must be an object")
        resolved[kind] = block_params_from_mapping(kind, config)
    return resolved


def parse_block_config_json(raw: str) -> dict[str, BaseParams] | None:
    """Parse a JSON object containing API-style block params."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid block_configs JSON") from exc
    if not isinstance(parsed, Mapping):
        raise TypeError("block_configs must be a JSON object")
    return parse_block_config_mapping(parsed)


def parse_cli_block_configs(
    entries: list[str],
    *,
    json_config: str = "",
) -> dict[str, BaseParams]:
    """Parse CLI ``--block-config`` entries against the default Markdown registry."""
    registry: BlockKindRegistry = MarkdownItParser.default_registry()
    result: dict[str, BaseParams] = dict(registry.default_handling())
    for entry in entries:
        kind, params = parse_block_config_entry(entry, registry)
        result[kind] = params
    if json_config and json_config.strip():
        json_overrides = parse_block_config_json(json_config)
        if json_overrides:
            result.update(json_overrides)
    return result
