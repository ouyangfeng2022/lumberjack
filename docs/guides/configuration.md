# Configuration

[中文](../zh-CN/guides/configuration.md)

`Lumberjack` accepts concrete components, so configure built-in splitting by constructing a splitter with its tokenizer:

```python
from lumberjack import Lumberjack
from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.splitter import SiblingSplitter
from lumberjack.tokenizer import ApproxByteTokenizer

tokenizer = ApproxByteTokenizer()
splitter = SiblingSplitter(
    tokenizer,
    max_tokens=800,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    heading_sensitive=True,
    block_options=(
        MarkdownTableConfig(max_tokens=500, repeat_header=True),
        BlockConfig(BlockKind.CODE_FENCE, split=False),
    ),
)
jack = Lumberjack(tokenizer=tokenizer, splitter=splitter)
```

`block_options` is a sequence of typed configuration objects. Duplicate block kinds are rejected. Use `MarkdownTableConfig` for Markdown tables and `HTMLTableConfig` for HTML tables; both can repeat headers. `BlockConfig` covers the other built-in kinds, and `CustomBlockConfig` covers a parser plugin's custom kind.

| Field | Effect |
| --- | --- |
| `isolated` | Keeps the block in its own draft rather than packing it with neighbours. |
| `split` | Allows or prevents fallback splitting for the block. A non-splittable oversized block may exceed the budget. |
| `max_tokens` | Overrides the splitter budget for that block kind. |
| `repeat_header` | Repeats the table header for every generated table piece. |

CLI and Web API inputs use mapping forms at their boundary. The Python API deliberately does not accept a dict for `block_options`; pass typed objects so invalid names and duplicate policies are found early.
