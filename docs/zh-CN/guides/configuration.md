# 配置

[English](../../guides/configuration.md)

`Lumberjack` 接受具体组件，因此可通过使用同一个 tokenizer 构造 splitter 来配置内置拆分：

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

`block_options` 是类型安全的配置对象序列，重复 block kind 会被拒绝。Markdown 表格使用 `MarkdownTableConfig`，HTML 表格使用 `HTMLTableConfig`；两者都可重复表头。其他内置 kind 使用 `BlockConfig`，parser plugin 的自定义 kind 使用 `CustomBlockConfig`。

| 字段 | 效果 |
| --- | --- |
| `isolated` | 让 block 单独形成 draft，而不与相邻内容打包。 |
| `split` | 是否允许该 block 使用回退拆分。不可拆分的超长 block 可以超过预算。 |
| `max_tokens` | 覆盖该 block kind 的 splitter 预算。 |
| `repeat_header` | 每个表格拆分片段重复表头。 |

CLI 与 Web API 在边界接受 mapping 形式。Python API 有意不接受 `block_options` 字典；请传入类型安全对象，以便尽早发现无效名称和重复策略。
